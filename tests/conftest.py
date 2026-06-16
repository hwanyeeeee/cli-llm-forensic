import base64, hashlib, json
from pathlib import Path
import pytest

# .env 본문 (CLFXTEST 001~004) — A 붙여넣기 / B read 양쪽이 공유
ENV_BODY = (
    "STRIPE_SECRET_KEY=sk_live_CLFXTEST001FAKEabcdefghijklmn0123\n"
    "AWS_ACCESS_KEY_ID=AKIACLFXTEST00000002\n"
    "AWS_SECRET_ACCESS_KEY=CLFXTEST003FAKEsecretKeyAbcdefghij0123456\n"
    "DB_PASSWORD=CLFXTEST004_db_p@ssw0rd\n"
)
CONFIG_BODY = (
    'GITHUB_TOKEN = "ghp_CLFXTEST005FAKEabcdefghijklmno012345"\n'
    'OPENAI_API_KEY = "sk-CLFXTEST006FAKEabcdefghijklmnopqrstuvwxyzABCDEFG"\n'
)
IDRSA_BODY = ("-----BEGIN OPENSSH PRIVATE KEY-----\n"
              "CLFXTEST007FAKEdonotuseprivatekeymaterialforresearchonly\n"
              "-----END OPENSSH PRIVATE KEY-----\n")
NPMRC_BODY = "//registry.npmjs.org/:_authToken=npm_CLFXTEST008FAKEabcdefghijklmno012345\n"
APP_BODY = "def add(a,b): return a+b\n"   # 노이즈 (시크릿 아님)
PNG_1x1_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
               "nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=")  # 1x1 PNG


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_history(pastes):
    """pastes: list of dicts. 각 항목 -> history.jsonl 한 줄(dict) 반환.
    dict keys: display(str), items(list of paste item dict).
    paste item: {"content": str}  또는  {"contentHash": str}.
    """
    rows = []
    for p in pastes:
        pc = {}
        for i, it in enumerate(p["items"], start=1):
            pc[str(i)] = {"type": "text", **it}
        rows.append({"display": p["display"], "pastedContents": pc,
                     "project": p.get("project", "clfx-victim"),
                     "timestamp": p.get("ts", "2026-06-11T01:00:00Z")})
    return rows


def make_transcript(records):
    """records: list of high-level dicts -> projects/*.jsonl 레코드(dict) 리스트.
    지원 kind:
      {"kind":"prompt", "text":..}                               -> type:user (사용자 프롬프트)
      {"kind":"image"}                                           -> type:user (이미지 붙여넣기)
      {"kind":"read", "path":.., "content":..}                   -> toolUseResult.file
      {"kind":"bash", "cmd":..}                                  -> assistant tool_use Bash
      {"kind":"write", "path":..}                                -> assistant tool_use Write
      {"kind":"response", "text":..}                             -> type:assistant
      {"kind":"permission-mode", "mode":"bypassPermissions"}     -> type:permission-mode
      {"kind":"agent-name", "name":.., "sidechain":bool}         -> type:agent-name
      {"kind":"file-history-snapshot"}                           -> type:file-history-snapshot
      {"kind":"thinking", "text":..}                             -> type:thinking
    공통: ts, session 부여.
    """
    out = []
    for r in records:
        ts = r.get("ts", "2026-06-11T02:00:00Z"); sess = r.get("session", "sess")
        k = r["kind"]
        if k == "prompt":
            out.append({"type":"user","sessionId":sess,"timestamp":ts,
                        "message":{"role":"user","content":[{"type":"text","text":r["text"]}]}})
        elif k == "image":
            out.append({"type":"user","sessionId":sess,"timestamp":ts,
                        "message":{"role":"user","content":[
                            {"type":"text","text":"[Image #1]"},
                            {"type":"image","source":{"type":"base64","media_type":"image/png","data":PNG_1x1_B64}}]}})
        elif k == "read":
            out.append({"type":"user","sessionId":sess,"timestamp":ts,
                        "toolUseResult":{"file":{"filePath":r["path"],"content":r["content"]}},
                        "message":{"role":"user","content":[{"type":"tool_result","content":r["content"]}]}})
        elif k == "bash":
            out.append({"type":"assistant","sessionId":sess,"timestamp":ts,
                        "message":{"role":"assistant","content":[
                            {"type":"tool_use","name":"Bash","input":{"command":r["cmd"]}}]}})
        elif k == "write":
            out.append({"type":"assistant","sessionId":sess,"timestamp":ts,
                        "message":{"role":"assistant","content":[
                            {"type":"tool_use","name":"Write","input":{"file_path":r["path"]}}]}})
        elif k == "response":
            out.append({"type":"assistant","sessionId":sess,"timestamp":ts,
                        "message":{"role":"assistant","content":[{"type":"text","text":r["text"]}]}})
        elif k == "permission-mode":
            out.append({"type":"permission-mode","sessionId":sess,"timestamp":ts,"permissionMode":r["mode"]})
        elif k == "agent-name":
            out.append({"type":"agent-name","sessionId":sess,"timestamp":ts,
                        "agentName":r["name"],"isSidechain":r.get("sidechain",True)})
        elif k == "file-history-snapshot":
            out.append({"type":"file-history-snapshot","sessionId":sess,"timestamp":ts,"snapshot":{}})
        elif k == "thinking":
            out.append({"type":"thinking","sessionId":sess,"timestamp":ts,"thinking":r["text"]})
        else:
            raise ValueError(f"unknown kind {k}")
    return out


def write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in records), encoding="utf-8")


@pytest.fixture
def golden_root():
    """커밋된 골든 픽스처 루트 (tests/fixtures/dot-claude)."""
    return Path(__file__).parent / "fixtures" / "dot-claude"


@pytest.fixture
def built_root(tmp_path):
    """빌더로 즉석 생성한 ~/.claude 유사 루트. (A: 붙여넣기 / B: 자율 read)"""
    root = tmp_path / "dot-claude"
    # A 시나리오: 사용자가 .env 본문 붙여넣음 (contentHash → paste-cache)
    h = content_hash(ENV_BODY)
    write_jsonl(root / "history.jsonl", make_history([
        {"display": "[Pasted text #1 +4 lines] 이 설정 봐줘", "items": [{"contentHash": h}]},
    ]))
    (root / "paste-cache").mkdir(parents=True, exist_ok=True)
    (root / "paste-cache" / f"{h}.txt").write_text(ENV_BODY, encoding="utf-8")
    # B 시나리오: bypass 모드 + 에이전트가 .env/config.py/id_rsa/.npmrc read
    write_jsonl(root / "projects" / "-clfx-victim" / "sess.jsonl", make_transcript([
        {"kind":"permission-mode","mode":"bypassPermissions"},
        {"kind":"prompt","text":"Audit this repo for hardcoded secrets."},
        {"kind":"read","path":"/home/u/clfx-victim/.env","content":ENV_BODY},
        {"kind":"read","path":"/home/u/clfx-victim/config.py","content":CONFIG_BODY},
        {"kind":"read","path":"/home/u/clfx-victim/keys/id_rsa","content":IDRSA_BODY},
        {"kind":"read","path":"/home/u/clfx-victim/.npmrc","content":NPMRC_BODY},
        {"kind":"read","path":"/home/u/clfx-victim/app.py","content":APP_BODY},  # 노이즈
        {"kind":"response","text":"Found secrets in 4 files."},
    ]))
    return root

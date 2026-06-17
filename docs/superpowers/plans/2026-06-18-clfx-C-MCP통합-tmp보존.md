# C단계: MCP 통합 + tmp 보존기간(retention) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 흩어진 MCP 설정(`.mcp.json` + 글로벌 `~/.claude.json` mcpServers)과 transcript의 실제 MCP 툴 호출(`mcp__*`)을 통합 집계하고, tmp 파일의 보존기간(retention) 메타를 read-only로 보고한다 — 교수님 피드백 ⑧ "통합 1차".

**Architecture:** 증거=결정적(파서가 `mcp__` 호출을 `action="mcp"` Event로 발행 → 엔진 단일 진실원천). 신규 `clfx/analyze/mcp.py`가 설정 파일을 read-only로 스캔(env/url 토큰 마스킹)하고 엔진 이벤트의 실사용을 집계해 "설정 vs 실사용"을 대조한다. tmp 보존기간은 B단계 `clfx/analyze/artifacts.py`의 `_walk_tmp`를 재사용한다. Prefetch 파싱은 스펙 §결론(line 97)대로 보류(상관만, 이번 범위 아님).

**Tech Stack:** Python 3.12 stdlib only(`json`/`os`/`time`), 기존 모듈 패턴(`clfx/analyze/*`, `clfx/web/api.py`+`server.py`, `clfx/web/static/*`), pytest TDD.

---

## 절대 불변식 (모든 Task에 적용)

- **READ-ONLY FS**: `.mcp.json`·`~/.claude.json`은 `open(path,"r")`+`json.load`만. tmp는 `os.walk(followlinks=False)`+`os.stat`만. write/delete/rename 절대 금지.
- **완전성(무skip)**: `~/.claude.json`이 아는 **모든** project의 `.mcp.json`을 읽고, transcript의 **모든** `mcp__` 호출을 집계하고, tmp의 **모든** 정규파일 보존기간을 계산한다. cap/sample/top-N 금지. 읽기 실패 파일은 조용히 누락하지 말고 `errors[]`에 기록.
- **무손실**: 파서의 `mcp` 발행은 기존 이벤트를 **추가만** 한다(기존 `prompt/read/bash/write/paste/response` 발행 로직 불변). `test_scan_equivalent_to_sequential`(병렬=순차 동일성) 계속 green.
- **결정성**: 모든 출력 정렬(configs/usage/retention/errors). 같은 입력=같은 출력.
- **로컬 보안**: `.mcp.json`의 `env` 값(API키 등)은 전부 `‹secret›`로 마스킹, `url`/`args`는 `secrets.scan/mask` 적용. transcript `mcp` 이벤트 preview는 `enrich()`가 이미 모든 preview를 `scan`+`mask`하므로 자동 마스킹됨(별도 처리 불필요).

---

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `docs/event-schema.md` | Event 스키마 단일 진실원천 | action enum에 `mcp` 추가 |
| `clfx/event.py:56` | Event dataclass action 주석 | 주석에 `mcp` 추가 |
| `clfx/parser.py:151-174` | transcript tool_use 파싱 | `mcp__*` → `action="mcp"` 발행(현재 드롭됨) |
| `clfx/analyze/mcp.py` | **(신규)** MCP 설정 스캔(마스킹)·실사용 집계·대조 | 생성 |
| `clfx/analyze/artifacts.py` | B단계 아티팩트 계층 | `tmp_retention()` 추가(`_walk_tmp` 재사용) |
| `clfx/web/api.py` | 페이로드 빌더 | `mcp_payload()` 추가, `forensic_scan()`에 `retention` 추가 |
| `clfx/web/server.py` | HTTP 라우트 | `GET /api/mcp`, `ServerState.mcp`, `POST /api/scan` 통합 |
| `clfx/web/static/index.html` | 뷰 | `#mcp`·`#retention` 패널 |
| `clfx/web/static/app.js` | 뷰 로직 | `loadMcp()` + retention 렌더 |
| `clfx/web/static/app.css` | 스타일 | 패널·경고 강조 스타일 |
| `tests/test_mcp.py` | **(신규)** mcp.py 테스트 | 생성 |
| `tests/test_artifacts.py` | retention 테스트 추가 | 확장 |
| `tests/test_parser.py` | mcp 발행 테스트 추가 | 확장 |
| `tests/fixtures/mcp/` | **(신규)** mcp__ transcript + .mcp.json 픽스처 | 생성 |

---

## 데이터 계약

```
GET /api/mcp →
{
  "configs": [                                  # 설정된 MCP 서버(마스킹됨), 정렬: (scope, project, server)
    {"server": "playwright", "scope": "project", "project": "/mnt/c/projects/foo",
     "command": "npx", "args": ["-y","@playwright/mcp@latest"], "type": null, "url": null,
     "env_keys": [], "source_file": "/home/u/.claude.json"}
  ],
  "usage": [                                     # transcript 실호출 집계, 정렬: (server, tool)
    {"server": "playwright", "tool": "browser_click", "count": 12,
     "first_ts": "...Z", "last_ts": "...Z", "sessions": 3}
  ],
  "configured_unused": ["serverA"],              # 설정O 사용X (정렬)
  "used_unconfigured": ["serverB"],              # 사용O 설정X (유출/외부연결 신호, 정렬)
  "errors": [{"path": "...", "reason": "JSONDecodeError"}]   # 읽기 실패(완전성), 정렬: path
}

GET /api/artifacts → (B단계 계약 + retention 추가)
{ ...기존(scanned/missing/tmp_scanned/tmp_roots/errors/hashes/attribution),
  "retention": [                                 # tmp 파일 보존기간, 정렬: path
    {"path":"...","size":1234,"mtime":"...Z","atime":"...Z","age_days":12.5,"expires_in_days":17.5}
  ]
}
```

---

## Task 1: 스키마 — action enum에 `mcp` 추가

**Files:**
- Modify: `docs/event-schema.md:11`
- Modify: `clfx/event.py:56`

- [ ] **Step 1: event-schema.md의 action enum 갱신**

`docs/event-schema.md` 11번째 줄:
```
"prompt | read | bash | write | paste | response",   // 무슨 행동
```
을 다음으로 교체:
```
"prompt | read | bash | write | paste | response | mcp",   // 무슨 행동 (mcp = MCP 툴 호출)
```

- [ ] **Step 2: event.py 주석 갱신**

`clfx/event.py:56`:
```python
    action: str         # prompt | read | bash | write | paste | response
```
을 다음으로 교체:
```python
    action: str         # prompt | read | bash | write | paste | response | mcp
```

- [ ] **Step 3: 변경 확인**

Run: `grep -n "mcp" docs/event-schema.md clfx/event.py`
Expected: 두 파일 모두 enum/주석에 `mcp` 포함.

- [ ] **Step 4: Commit**

```bash
git add docs/event-schema.md clfx/event.py
git commit -m "schema: action enum에 mcp 추가 (MCP 툴 호출)"
```

---

## Task 2: 파서 — `mcp__*` tool_use를 `action="mcp"`로 발행

현재 `clfx/parser.py:162-164`는 Bash/Write 외 모든 tool_use를 드롭한다(`else: continue`). MCP 호출(`mcp__server__tool`)도 드롭된다. 이를 발행으로 바꾼다. preview는 입력 인자의 compact JSON(결정성 위해 `sort_keys=True`)이며, `enrich()`가 후속에서 secret을 마스킹한다.

**Files:**
- Modify: `clfx/parser.py:146-186`
- Create: `tests/fixtures/mcp/projects/mcp-session.jsonl`
- Test: `tests/test_parser.py`

- [ ] **Step 1: mcp__ transcript 픽스처 생성**

`tests/fixtures/mcp/projects/mcp-session.jsonl` (각 줄이 한 레코드, assistant가 mcp 툴 호출):
```jsonl
{"type":"assistant","timestamp":"2026-06-18T01:00:00.000Z","sessionId":"s-mcp","message":{"content":[{"type":"tool_use","name":"mcp__playwright__browser_click","input":{"selector":"#login","token":"sk-secret-abcdefghijklmnop"}}]}}
{"type":"assistant","timestamp":"2026-06-18T01:00:05.000Z","sessionId":"s-mcp","message":{"content":[{"type":"tool_use","name":"mcp__playwright__browser_click","input":{"selector":"#next"}}]}}
{"type":"assistant","timestamp":"2026-06-18T01:00:10.000Z","sessionId":"s-mcp","message":{"content":[{"type":"tool_use","name":"mcp__notion__search","input":{"query":"plan"}}]}}
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/test_parser.py` 끝에 추가:
```python
def test_mcp_tool_use_emits_mcp_action(tmp_path):
    from clfx.sources import ClaudeSource
    from clfx.parser import parse_source
    # 픽스처를 ClaudeSource로 파싱
    src = ClaudeSource("tests/fixtures/mcp")
    events = list(parse_source(src))
    mcp_evs = [e for e in events if e.action == "mcp"]
    assert len(mcp_evs) == 3                       # 모든 mcp__ 호출 발행(무skip)
    assert mcp_evs[0].actor == "agent"             # MCP 호출 주체=에이전트
    assert mcp_evs[0].target == "mcp__playwright__browser_click"
    # preview는 입력 인자 JSON(결정성: sort_keys) — 아직 마스킹 전(파서 단계)
    assert "selector" in mcp_evs[0].preview
```

참고: `parse_source`는 `clfx/parser.py`에 이미 존재하는 진입점이다. 시그니처가 다르면 `tests/test_parser.py`의 기존 테스트가 쓰는 호출 방식을 그대로 따라라(`grep -n "parse_source\|def parse" clfx/parser.py tests/test_parser.py`).

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_parser.py::test_mcp_tool_use_emits_mcp_action -v`
Expected: FAIL — `assert 0 == 3` (현재 mcp 호출이 드롭되어 mcp_evs 비어있음).

- [ ] **Step 4: 파서 구현**

`clfx/parser.py`의 assistant tool_use 블록(현재 151-174)을 다음으로 교체:
```python
                if ptype == "tool_use":
                    name = part.get("name")
                    inp = part.get("input") or {}
                    if not isinstance(inp, dict):
                        inp = {}
                    tu_preview = ""                       # 기본: 미리보기 없음(bash/write)
                    if name == "Bash":
                        action, target = "bash", inp.get("command") or ""
                    elif name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                        # NotebookEdit는 notebook_path 우선, 없으면 file_path
                        action = "write"
                        target = inp.get("notebook_path") or inp.get("file_path") or ""
                    elif name and name.startswith("mcp__"):
                        # MCP 툴 호출 → 외부 프로그램/서비스 흔적. target=풀네임, preview=입력 인자.
                        # 결정성: sort_keys. secret은 enrich()가 후속에 모든 preview를 scan+mask.
                        action, target = "mcp", name
                        try:
                            import json as _json
                            tu_preview = clip(_json.dumps(inp, ensure_ascii=False, sort_keys=True))
                        except (TypeError, ValueError):
                            tu_preview = clip(str(inp))
                    else:
                        # Read/Grep/Glob 등 → 미발행. 읽기는 toolUseResult read가 담당(중복 방지).
                        continue
                    yield Event(
                        ts=ts,
                        agent=agent,
                        session=sess,
                        actor="agent",
                        action=action,
                        target=target,
                        preview=tu_preview,
                        source=s,
                    )
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_parser.py::test_mcp_tool_use_emits_mcp_action -v`
Expected: PASS.

- [ ] **Step 6: 무손실(동일성) 회귀 + 전체 확인**

Run: `python -m pytest -q`
Expected: 전체 PASS(기존 229 + 신규 1). `test_scan_equivalent_to_sequential` 포함 green(파서는 추가 발행만 — 병렬/순차 동일성 유지). 기존 픽스처엔 `mcp__`가 없어 카운트 단언 영향 없음(`grep -rl mcp__ tests/fixtures` → mcp 픽스처만).

- [ ] **Step 7: Commit**

```bash
git add clfx/parser.py tests/test_parser.py tests/fixtures/mcp/projects/mcp-session.jsonl
git commit -m "feat(parser): mcp__ tool_use를 action=mcp Event로 발행 (외부 MCP 흔적)"
```

---

## Task 3: `clfx/analyze/mcp.py` — 설정 마스킹 헬퍼

MCP 설정의 `env` 값은 API키 등 민감정보 → 값 전부 `‹secret›`. `url`/`args`는 인라인 토큰 가능 → `secrets.scan/mask`. `command`(npx/node 등)는 비밀 아님 → 유지.

**Files:**
- Create: `clfx/analyze/mcp.py`
- Test: `tests/test_mcp.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_mcp.py` (신규):
```python
from clfx.analyze.mcp import _mask_config


def test_mask_config_masks_env_values_keeps_keys():
    cfg = {"command": "npx", "args": ["-y", "@playwright/mcp"],
           "env": {"API_KEY": "sk-supersecretvalue123456", "PORT": "8080"}}
    out = _mask_config(cfg)
    assert out["command"] == "npx"                     # 명령은 유지
    assert out["env"] == {"API_KEY": "‹secret›", "PORT": "‹secret›"}  # env 값 전부 마스킹, 키 보존
    assert "API_KEY" in out["env"]                     # 어떤 변수가 설정됐는지는 증거로 남김


def test_mask_config_masks_url_token():
    cfg = {"type": "http", "url": "https://mcp.example.com/sse?token=sk-abcdefghijklmnopqrst"}
    out = _mask_config(cfg)
    assert "sk-abcdefghijklmnopqrst" not in out["url"]  # url 내 토큰 마스킹
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_mcp.py -v`
Expected: FAIL — `ModuleNotFoundError: clfx.analyze.mcp`.

- [ ] **Step 3: 구현**

`clfx/analyze/mcp.py` (신규, 상단부):
```python
"""MCP 통합 — read-only 설정 스캔(마스킹) + transcript 실사용 집계 + 대조.

절대 불변식:
- READ-ONLY FS: open(path,"r")+json.load만.
- 완전성: ~/.claude.json이 아는 모든 project의 .mcp.json 읽기. 실패→errors[].
- 보안: env 값 전부 ‹secret›, url/args는 secrets.scan/mask. command는 유지.
- 결정성: 모든 출력 정렬.
"""

import json
import os

from clfx.analyze.secrets import mask, scan
from clfx.event import ts_key


def _mask_str(s):
    """문자열 내 secret 패턴 마스킹(없으면 원본)."""
    if not isinstance(s, str):
        return s
    f = scan(s)
    return mask(s, f) if f else s


def _mask_config(cfg):
    """MCP 서버 설정 dict → 마스킹 사본. env 값 전부 ‹secret›(키 보존), url/args는 scan/mask."""
    out = dict(cfg)
    env = out.get("env")
    if isinstance(env, dict):
        out["env"] = {k: "‹secret›" for k in env}      # 값은 민감 → 전부 마스킹, 키는 증거로 보존
    if isinstance(out.get("url"), str):
        out["url"] = _mask_str(out["url"])
    if isinstance(out.get("args"), list):
        out["args"] = [_mask_str(a) for a in out["args"]]
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_mcp.py -v`
Expected: PASS (2건).

- [ ] **Step 5: Commit**

```bash
git add clfx/analyze/mcp.py tests/test_mcp.py
git commit -m "feat(mcp): MCP 설정 마스킹 헬퍼 (_mask_config — env/url/args)"
```

---

## Task 4: `parse_mcp_config` — 단일 `.mcp.json` 읽기(마스킹)

**Files:**
- Modify: `clfx/analyze/mcp.py`
- Create: `tests/fixtures/mcp/proj-a/.mcp.json`
- Test: `tests/test_mcp.py`

- [ ] **Step 1: .mcp.json 픽스처 생성**

`tests/fixtures/mcp/proj-a/.mcp.json`:
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--headless"]
    },
    "secret-server": {
      "command": "node",
      "args": ["server.js"],
      "env": {"TOKEN": "sk-shouldbemaskednow1234567"}
    }
  }
}
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/test_mcp.py`에 추가:
```python
from clfx.analyze.mcp import parse_mcp_config


def test_parse_mcp_config_returns_masked_servers():
    servers = parse_mcp_config("tests/fixtures/mcp/proj-a/.mcp.json")
    assert set(servers.keys()) == {"playwright", "secret-server"}   # 모든 서버(무skip)
    assert servers["playwright"]["command"] == "npx"
    assert servers["secret-server"]["env"] == {"TOKEN": "‹secret›"} # env 값 마스킹
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_mcp.py::test_parse_mcp_config_returns_masked_servers -v`
Expected: FAIL — `AttributeError`/`ImportError` (`parse_mcp_config` 미정의).

- [ ] **Step 4: 구현**

`clfx/analyze/mcp.py`에 추가:
```python
def parse_mcp_config(path):
    """단일 .mcp.json 또는 mcpServers 보유 JSON을 read-only로 읽어 {server: 마스킹설정}.
    읽기/파싱 실패는 raise(상위 find_mcp_configs가 errors로 수집)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    servers = data.get("mcpServers") or {}
    out = {}
    for name, cfg in servers.items():
        if isinstance(cfg, dict):
            out[name] = _mask_config(cfg)
    return out
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_mcp.py::test_parse_mcp_config_returns_masked_servers -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add clfx/analyze/mcp.py tests/test_mcp.py tests/fixtures/mcp/proj-a/.mcp.json
git commit -m "feat(mcp): parse_mcp_config — 단일 .mcp.json read-only 읽기(마스킹)"
```

---

## Task 5: `find_mcp_configs` — 글로벌+프로젝트별 전수 스캔(read-only, errors)

`~/.claude.json`은 `.claude` 루트의 형제(`<root>/../.claude.json`). 그 안의 top-level `mcpServers`(글로벌)와 `projects` 키(= Claude가 아는 모든 프로젝트 경로) 각각의 `<proj>/.mcp.json` 및 인라인 `projects[proj].mcpServers`를 전부 읽는다. 경로변환은 B단계 `artifacts.resolve_candidates`(WSL↔Windows) 재사용. 읽기 실패 → `errors[]`(완전성).

**Files:**
- Modify: `clfx/analyze/mcp.py`
- Create: `tests/fixtures/mcp/.claude.json`, `tests/fixtures/mcp/.claude/` (빈 디렉터리 표식)
- Test: `tests/test_mcp.py`

- [ ] **Step 1: 글로벌 .claude.json 픽스처 생성**

`tests/fixtures/mcp/.claude.json` (루트 형제 위치 — `tests/fixtures/mcp/.claude`가 root, 그 형제):
```json
{
  "mcpServers": {
    "global-server": {"command": "node", "args": ["g.js"]}
  },
  "projects": {
    "PROJ_A_ABS": {}
  }
}
```
참고: `PROJ_A_ABS`는 Step 2 테스트에서 `tests/fixtures/mcp/proj-a`의 **절대경로**로 치환해 임시 .claude.json을 쓴다(픽스처 절대경로 고정 불가). 아래 테스트가 tmp_path에 .claude.json을 만들어 처리한다.

- [ ] **Step 2: 실패 테스트 작성**

`tests/test_mcp.py`에 추가:
```python
import json as _json
import os
from clfx.analyze.mcp import find_mcp_configs


def test_find_mcp_configs_collects_global_and_project(tmp_path):
    # 가짜 .claude 루트 + 형제 .claude.json 구성
    root = tmp_path / ".claude"
    root.mkdir()
    proj = tmp_path / "proj-a"
    proj.mkdir()
    (proj / ".mcp.json").write_text(_json.dumps({
        "mcpServers": {"playwright": {"command": "npx", "args": ["-y", "@playwright/mcp"]}}
    }), encoding="utf-8")
    (tmp_path / ".claude.json").write_text(_json.dumps({
        "mcpServers": {"global-server": {"command": "node", "args": ["g.js"]}},
        "projects": {str(proj): {}}
    }), encoding="utf-8")

    out = find_mcp_configs([str(root)])
    servers = {c["server"] for c in out["configs"]}
    assert servers == {"global-server", "playwright"}      # 글로벌 + 프로젝트 .mcp.json 둘 다(무skip)
    scopes = {c["server"]: c["scope"] for c in out["configs"]}
    assert scopes["global-server"] == "global"
    assert scopes["playwright"] == "project"
    assert out["errors"] == []                              # 정상 → 에러 없음


def test_find_mcp_configs_records_unreadable_in_errors(tmp_path):
    root = tmp_path / ".claude"
    root.mkdir()
    proj = tmp_path / "proj-bad"
    proj.mkdir()
    (proj / ".mcp.json").write_text("{ this is not valid json", encoding="utf-8")  # 파싱 실패
    (tmp_path / ".claude.json").write_text(_json.dumps({"projects": {str(proj): {}}}), encoding="utf-8")

    out = find_mcp_configs([str(root)])
    assert any(proj.name in e["path"] for e in out["errors"])   # 읽기 실패 파일이 errors에 기록(완전성)
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_mcp.py -k find_mcp_configs -v`
Expected: FAIL — `find_mcp_configs` 미정의.

- [ ] **Step 4: 구현**

`clfx/analyze/mcp.py`에 추가:
```python
def _config_rows(servers, scope, project, source_file):
    """{server: 마스킹설정} → 정규화된 행 리스트."""
    rows = []
    for name, cfg in servers.items():
        rows.append({
            "server": name,
            "scope": scope,                 # "global" | "project"
            "project": project,             # 프로젝트 경로(글로벌이면 None)
            "command": cfg.get("command"),
            "args": cfg.get("args") if isinstance(cfg.get("args"), list) else [],
            "type": cfg.get("type"),
            "url": cfg.get("url"),
            "env_keys": sorted(cfg["env"].keys()) if isinstance(cfg.get("env"), dict) else [],
            "source_file": source_file,
        })
    return rows


def find_mcp_configs(roots):
    """각 .claude 루트의 형제 ~/.claude.json + 그 projects의 .mcp.json 전수 read-only 스캔.
    반환 {"configs":[...정렬...], "errors":[...정렬...]}. 완전성: 모든 설정 읽기, 실패→errors."""
    from clfx.analyze.artifacts import resolve_candidates

    configs = []
    errors = []
    seen = set()                            # (source_file, scope, project, server) 중복제거(결정성)

    def _add(servers, scope, project, source_file):
        for row in _config_rows(servers, scope, project, source_file):
            key = (source_file, scope, project, row["server"])
            if key in seen:
                continue
            seen.add(key)
            configs.append(row)

    for root in roots or []:
        claude_json = os.path.join(os.path.dirname(str(root)), ".claude.json")
        if not os.path.isfile(claude_json):
            continue
        try:
            with open(claude_json, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:                                  # noqa: BLE001 - 완전성: 어떤 실패도 errors로
            errors.append({"path": claude_json, "reason": type(e).__name__})
            continue
        # 글로벌 mcpServers
        gserv = data.get("mcpServers") or {}
        _add({k: _mask_config(v) for k, v in gserv.items() if isinstance(v, dict)},
             "global", None, claude_json)
        # 프로젝트별
        for proj, pdata in (data.get("projects") or {}).items():
            # 인라인 projects[proj].mcpServers
            if isinstance(pdata, dict):
                pserv = pdata.get("mcpServers") or {}
                _add({k: _mask_config(v) for k, v in pserv.items() if isinstance(v, dict)},
                     "project", proj, claude_json)
            # <proj>/.mcp.json (경로변환 후 존재하는 첫 후보)
            for cand_dir in resolve_candidates(proj, root):
                mcp_path = os.path.join(cand_dir, ".mcp.json")
                if not os.path.isfile(mcp_path):
                    continue
                try:
                    servers = parse_mcp_config(mcp_path)
                except Exception as e:                          # noqa: BLE001
                    errors.append({"path": mcp_path, "reason": type(e).__name__})
                    break
                _add(servers, "project", proj, mcp_path)
                break                                           # 첫 존재 후보만(동일 프로젝트 1파일)

    configs.sort(key=lambda c: (c["scope"], c["project"] or "", c["server"]))
    errors.sort(key=lambda e: e["path"])
    return {"configs": configs, "errors": errors}
```

참고: `resolve_candidates(proj, root)`는 B단계 `artifacts.py`에 있다. 디렉터리 경로 문자열도 파일과 동일하게 OS형식만 변환하므로(`/mnt/c`↔`C:\`, `/home`↔`\\wsl.localhost`) 그대로 재사용 가능.

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_mcp.py -k find_mcp_configs -v`
Expected: PASS (2건).

- [ ] **Step 6: Commit**

```bash
git add clfx/analyze/mcp.py tests/test_mcp.py
git commit -m "feat(mcp): find_mcp_configs — 글로벌+프로젝트 .mcp.json 전수 스캔(read-only·errors)"
```

---

## Task 6: `mcp_usage_from_events` + `mcp_summary` — 실사용 집계·대조

**Files:**
- Modify: `clfx/analyze/mcp.py`
- Test: `tests/test_mcp.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_mcp.py`에 추가:
```python
from clfx.analyze.mcp import mcp_usage_from_events, mcp_summary
from clfx.event import Event, Source


def _ev(target, ts, session="s1"):
    return Event(ts=ts, agent="claude", session=session, actor="agent",
                 action="mcp", target=target, preview="", source=Source(file="f.jsonl", line=1))


def test_mcp_usage_aggregates_by_server_tool():
    evs = [
        _ev("mcp__playwright__browser_click", "2026-06-18T01:00:00Z"),
        _ev("mcp__playwright__browser_click", "2026-06-18T01:00:05Z"),
        _ev("mcp__notion__search", "2026-06-18T01:00:10Z", session="s2"),
    ]
    rows = mcp_usage_from_events(evs)
    assert rows == [
        {"server": "notion", "tool": "search", "count": 1,
         "first_ts": "2026-06-18T01:00:10Z", "last_ts": "2026-06-18T01:00:10Z", "sessions": 1},
        {"server": "playwright", "tool": "browser_click", "count": 2,
         "first_ts": "2026-06-18T01:00:00Z", "last_ts": "2026-06-18T01:00:05Z", "sessions": 1},
    ]   # 정렬: (server, tool)


def test_mcp_summary_reconciles_configured_vs_used(tmp_path):
    root = tmp_path / ".claude"
    root.mkdir()
    (tmp_path / ".claude.json").write_text(
        '{"mcpServers": {"playwright": {"command": "npx"}, "unused-srv": {"command": "node"}}}',
        encoding="utf-8")
    evs = [_ev("mcp__playwright__browser_click", "2026-06-18T01:00:00Z"),
           _ev("mcp__rogue__exfil", "2026-06-18T01:00:01Z")]
    out = mcp_summary([str(root)], evs)
    assert out["configured_unused"] == ["unused-srv"]   # 설정O 사용X
    assert out["used_unconfigured"] == ["rogue"]        # 사용O 설정X (외부연결 신호)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_mcp.py -k "usage or summary" -v`
Expected: FAIL — 함수 미정의.

- [ ] **Step 3: 구현**

`clfx/analyze/mcp.py`에 추가:
```python
def _split_target(target):
    """mcp__<server>__<tool> → (server, tool). 형식 어긋나면 (target, '')."""
    parts = (target or "").split("__")
    server = parts[1] if len(parts) >= 2 else (target or "")
    tool = parts[2] if len(parts) >= 3 else ""
    return server, tool


def mcp_usage_from_events(events):
    """action=='mcp' 이벤트를 (server, tool)별 집계. 정렬: (server, tool). 결정적."""
    agg = {}
    for e in events or []:
        if getattr(e, "action", None) != "mcp":
            continue
        server, tool = _split_target(e.target)
        a = agg.setdefault((server, tool), {
            "server": server, "tool": tool, "count": 0,
            "first_ts": None, "last_ts": None, "sessions": set(),
        })
        a["count"] += 1
        a["sessions"].add(e.session)
        if a["first_ts"] is None or ts_key(e.ts) < ts_key(a["first_ts"]):
            a["first_ts"] = e.ts
        if a["last_ts"] is None or ts_key(e.ts) > ts_key(a["last_ts"]):
            a["last_ts"] = e.ts
    rows = [{
        "server": a["server"], "tool": a["tool"], "count": a["count"],
        "first_ts": a["first_ts"], "last_ts": a["last_ts"], "sessions": len(a["sessions"]),
    } for a in agg.values()]
    rows.sort(key=lambda r: (r["server"], r["tool"]))
    return rows


def mcp_summary(roots, events):
    """설정 스캔 + 실사용 집계 + 대조. /api/mcp 단일 진입점."""
    cfg = find_mcp_configs(roots)
    configs, errors = cfg["configs"], cfg["errors"]
    usage = mcp_usage_from_events(events)
    configured = {c["server"] for c in configs}
    used = {u["server"] for u in usage}
    return {
        "configs": configs,
        "usage": usage,
        "configured_unused": sorted(configured - used),
        "used_unconfigured": sorted(used - configured),
        "errors": errors,
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_mcp.py -v`
Expected: 전체 PASS.

- [ ] **Step 5: Commit**

```bash
git add clfx/analyze/mcp.py tests/test_mcp.py
git commit -m "feat(mcp): mcp_usage_from_events + mcp_summary (설정 vs 실사용 대조)"
```

---

## Task 7: `artifacts.tmp_retention` — tmp 보존기간(`_walk_tmp` 재사용)

Claude tmp 보존 ≈ 30일(`docs/실측-temp-원본보존-원리.md`). B단계 `_walk_tmp`로 tmp 전수 → 각 파일 mtime/atime/age/만료잔여. read-only stat. `now_epoch` 주입으로 테스트 결정성 확보(나이 계산은 "현재시각" 의존이므로).

**Files:**
- Modify: `clfx/analyze/artifacts.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_artifacts.py`에 추가:
```python
import os
from clfx.analyze.artifacts import tmp_retention


def test_tmp_retention_reports_age_and_expiry(tmp_path):
    f = tmp_path / "leak.txt"
    f.write_text("secret payload", encoding="utf-8")
    ten_days_ago = f.stat().st_mtime           # 실제 mtime
    now = ten_days_ago + 10 * 86400            # 10일 후를 '현재'로 주입(결정성)
    out = tmp_retention([str(tmp_path)], now_epoch=now)
    rows = out["retention"]
    assert len(rows) == 1                       # 모든 tmp 정규파일(무skip)
    r = rows[0]
    assert r["path"] == str(f)
    assert abs(r["age_days"] - 10.0) < 0.01     # 나이 ≈ 10일
    assert abs(r["expires_in_days"] - 20.0) < 0.01  # 30 - 10 = 20일 잔여
    assert out["errors"] == []


def test_tmp_retention_expired_clamps_to_zero(tmp_path):
    f = tmp_path / "old.txt"
    f.write_text("x", encoding="utf-8")
    now = f.stat().st_mtime + 40 * 86400        # 40일 경과(>30 보존)
    out = tmp_retention([str(tmp_path)], now_epoch=now)
    assert out["retention"][0]["expires_in_days"] == 0   # 만료 → 0 클램프
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_artifacts.py -k tmp_retention -v`
Expected: FAIL — `tmp_retention` 미정의.

- [ ] **Step 3: 구현**

`clfx/analyze/artifacts.py`에 추가(`_walk_tmp` 정의 아래, `hash_clusters` 위 어디든):
```python
RETENTION_DAYS = 30        # Claude tmp 보존기간 실측치(docs/실측-temp-원본보존-원리.md)


def tmp_retention(tmp_dirs, now_epoch=None):
    """tmp 전수 → 각 정규파일 보존기간 메타. read-only stat. _walk_tmp 재사용.
    now_epoch: 나이 계산 기준 현재시각(테스트 주입용; None이면 time.time()).
    반환 {"retention":[...정렬: path...], "errors":[...]}."""
    import time
    if now_epoch is None:
        now_epoch = time.time()
    files, errors = _walk_tmp(tmp_dirs)
    rows = []
    for p in files:
        try:
            st = os.stat(p)
        except OSError as e:
            errors.append({"path": p, "reason": type(e).__name__})   # 완전성: 조용한 누락 금지
            continue
        age_days = (now_epoch - st.st_mtime) / 86400.0
        expires = RETENTION_DAYS - age_days
        rows.append({
            "path": p,
            "size": st.st_size,
            "mtime": _iso(st.st_mtime),
            "atime": _iso(st.st_atime),
            "age_days": round(age_days, 2),
            "expires_in_days": round(expires, 2) if expires > 0 else 0,
        })
    rows.sort(key=lambda r: r["path"])
    errors.sort(key=lambda e: e["path"])
    return {"retention": rows, "errors": errors}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_artifacts.py -k tmp_retention -v`
Expected: PASS (2건).

- [ ] **Step 5: Commit**

```bash
git add clfx/analyze/artifacts.py tests/test_artifacts.py
git commit -m "feat(artifacts): tmp_retention — tmp 보존기간 메타(read-only, _walk_tmp 재사용)"
```

---

## Task 8: API — `mcp_payload` + `forensic_scan`에 retention 추가

**Files:**
- Modify: `clfx/web/api.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_web_api.py`에 추가:
```python
def test_mcp_payload_has_contract_keys():
    from clfx.web.api import scan_to_engine, mcp_payload
    eng = scan_to_engine(["tests/fixtures/mcp"])
    out = mcp_payload(eng, ["tests/fixtures/mcp"])
    for k in ("configs", "usage", "configured_unused", "used_unconfigured", "errors"):
        assert k in out
    # 픽스처 transcript의 mcp__ 호출이 usage로 잡힘
    servers = {u["server"] for u in out["usage"]}
    assert "playwright" in servers


def test_forensic_scan_includes_retention():
    from clfx.web.api import forensic_scan
    out = forensic_scan([], roots=[], tmp_dirs=[])   # tmp_dirs=[] → 실제 머신 tmp 스캔 안 함(결정성)
    assert "retention" in out
    assert out["retention"] == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_web_api.py -k "mcp_payload or retention" -v`
Expected: FAIL — `mcp_payload` 미정의 / `retention` 키 없음.

- [ ] **Step 3: 구현**

`clfx/web/api.py`의 `forensic_scan` 함수를 다음으로 교체(retention 통합 + tmp_dirs 1회 계산):
```python
def forensic_scan(events_with_root, roots=None, tmp_dirs=None):
    """아티팩트 포렌식 단일 진입점 — hash_clusters(①복제/유출) + attribution_join(④주체왜곡)
    + tmp_retention(C: 보존기간) 합본. read-only FS만. 반환 키:
    scanned,missing,tmp_scanned,tmp_roots,errors,hashes,attribution,retention."""
    from clfx.analyze import artifacts
    if roots is None:
        roots = sorted({root for _e, root in (events_with_root or [])})
    if tmp_dirs is None:
        tmp_dirs = artifacts.tmp_roots(roots)
    out = artifacts.hash_clusters(events_with_root, roots=roots, tmp_dirs=tmp_dirs)
    out["attribution"] = artifacts.attribution_join(events_with_root)
    ret = artifacts.tmp_retention(tmp_dirs)
    out["retention"] = ret["retention"]
    out["errors"] = sorted(out["errors"] + ret["errors"], key=lambda e: e["path"])  # 보존 스캔 실패도 병합
    return out


def mcp_payload(engine, roots):
    """MCP 통합 페이로드 — 설정 스캔 + 엔진 이벤트 실사용 대조. /api/mcp 단일 진입점."""
    from clfx.analyze import mcp as mcpmod
    return mcpmod.mcp_summary(roots, engine.events)
```

참고: tmp를 2번 walk한다(hash_clusters 해시용 + tmp_retention stat용). 둘 다 read-only·완전(무skip)이며 해시 I/O가 지배적이라 walk 중복은 미미. 공유가 필요하면 후속 최적화(완전성에는 무영향).

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_web_api.py -k "mcp_payload or retention" -v`
Expected: PASS.

- [ ] **Step 5: 전체 회귀 확인**

Run: `python -m pytest -q`
Expected: 전체 PASS. 기존 `forensic_scan` 테스트가 새 `retention` 키로 깨지지 않는지 확인(키 추가만, 기존 키 불변).

- [ ] **Step 6: Commit**

```bash
git add clfx/web/api.py tests/test_web_api.py
git commit -m "feat(api): mcp_payload + forensic_scan에 retention 통합"
```

---

## Task 9: 서버 — `GET /api/mcp` + 스캔 통합

**Files:**
- Modify: `clfx/web/server.py`
- Test: `tests/test_web_server.py` (없으면 기존 서버 테스트 파일명 확인: `grep -rln "make_handler\|ServerState" tests/`)

- [ ] **Step 1: 실패 테스트 작성**

기존 서버 테스트 패턴을 따라(예: `tests/test_web_server.py` 또는 `tests/test_web_scan.py`) 추가. 기존 테스트가 `make_handler(state)`로 핸들러를 만들고 HTTP를 흉내내는 방식을 그대로 따라라:
```python
def test_api_mcp_returns_contract():
    from clfx.web.server import ServerState
    state = ServerState()
    assert state.mcp == {"configs": [], "usage": [], "configured_unused": [],
                         "used_unconfigured": [], "errors": []}   # 기본 빈 계약
```
(기존 서버 테스트가 실제 HTTP GET을 때리는 헬퍼를 쓰면, `GET /api/mcp`가 `state.mcp`를 JSON으로 돌려주는지 그 헬퍼로 검증하라.)

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/ -k "api_mcp" -v`
Expected: FAIL — `ServerState`에 `mcp` 속성 없음.

- [ ] **Step 3: ServerState에 mcp 기본값 추가**

`clfx/web/server.py`의 `ServerState.__init__`에서 `self.artifacts = {...}` 다음 줄에 추가:
```python
        # MCP 통합 결과(POST /api/scan서 mcp_payload로 갱신, GET /api/mcp가 읽음).
        self.mcp = {"configs": [], "usage": [], "configured_unused": [],
                    "used_unconfigured": [], "errors": []}
```

- [ ] **Step 4: import + GET 라우트 추가**

`clfx/web/server.py` 상단 import에 `mcp_payload` 추가:
```python
from clfx.web.api import (stats_payload, events_payload, query_payload, keywords_payload,
                          sources_payload, scan_to_engine, forensic_scan, mcp_payload)
```
(기존 import 줄에 `mcp_payload`만 덧붙여라 — 정확한 줄은 `grep -n "from clfx.web.api import" clfx/web/server.py`로 확인.)

GET 라우트(`/api/artifacts` 처리 블록 바로 아래)에 추가:
```python
            if u.path == "/api/mcp":
                try:
                    self._json(state.mcp)
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
```

- [ ] **Step 5: POST /api/scan에 mcp 계산 추가**

`POST /api/scan`에서 `state.artifacts = forensic_scan(...)` 블록 다음에 추가:
```python
                    try:                                     # FS/설정 실패해도 스캔 응답은 성공(빈 계약 유지)
                        state.mcp = mcp_payload(eng, roots)
                    except Exception:
                        state.mcp = {"configs": [], "usage": [], "configured_unused": [],
                                     "used_unconfigured": [], "errors": []}
```

- [ ] **Step 6: 테스트 통과 + JS·전체 확인**

Run: `python -m pytest -q && python -c "import json; print('ok')"`
Expected: 전체 PASS.

- [ ] **Step 7: Commit**

```bash
git add clfx/web/server.py tests/
git commit -m "feat(server): GET /api/mcp + POST /api/scan서 mcp 통합 계산"
```

---

## Task 10: UI — MCP 패널 + tmp 보존기간 패널

증거는 엔진/API가 책임지므로 UI는 fetch+렌더만. `used_unconfigured`(설정 없이 사용된 서버)와 만료임박 tmp는 경고색으로 강조.

**Files:**
- Modify: `clfx/web/static/index.html`
- Modify: `clfx/web/static/app.js`
- Modify: `clfx/web/static/app.css`

- [ ] **Step 1: index.html에 패널 추가**

기존 `#leaks`/`#attrib` 패널(B단계) 근처에 추가:
```html
    <section class="panel" id="mcp-panel">
      <h2>MCP 연결 흔적</h2>
      <div id="mcp" class="mcp"><span class="muted">스캔 후 표시</span></div>
    </section>
    <section class="panel" id="retention-panel">
      <h2>tmp 보존기간</h2>
      <div id="retention" class="retention"><span class="muted">스캔 후 표시</span></div>
    </section>
```

- [ ] **Step 2: app.js에 loadMcp + retention 렌더 추가**

`app.js`에 함수 추가(기존 `jget` 헬퍼 사용 — 정확한 이름은 `grep -n "function jget\|const jget\|async function load" app.js`):
```javascript
async function loadMcp() {
  const box = document.getElementById('mcp');
  if (!box) return;
  try {
    const d = await jget('/api/mcp');
    let html = '';
    if (d.used_unconfigured && d.used_unconfigured.length) {
      html += '<div class="warn">⚠ 설정 없이 사용된 서버: ' +
              d.used_unconfigured.map(esc).join(', ') + '</div>';
    }
    html += '<div class="sub">설정된 서버 ' + (d.configs ? d.configs.length : 0) + '개</div>';
    html += (d.configs || []).map(c =>
      '<div class="row"><b>' + esc(c.server) + '</b> <span class="muted">(' +
      esc(c.scope) + ')</span> ' + esc(c.command || '') +
      (c.env_keys && c.env_keys.length ? ' <span class="muted">env: ' + c.env_keys.map(esc).join(',') + '</span>' : '') +
      '</div>').join('');
    html += '<div class="sub">실호출 ' + (d.usage ? d.usage.length : 0) + '종</div>';
    html += (d.usage || []).map(u =>
      '<div class="row">' + esc(u.server) + '__' + esc(u.tool) +
      ' <span class="muted">×' + u.count + '</span></div>').join('');
    if (d.configured_unused && d.configured_unused.length) {
      html += '<div class="sub muted">설정O 미사용: ' + d.configured_unused.map(esc).join(', ') + '</div>';
    }
    box.innerHTML = html || '<span class="muted">MCP 흔적 없음</span>';
  } catch (e) {
    box.innerHTML = '<span class="muted">불러오기 실패</span>';
  }
}

function renderRetention(rows) {
  const box = document.getElementById('retention');
  if (!box) return;
  if (!rows || !rows.length) { box.innerHTML = '<span class="muted">tmp 잔존 없음</span>'; return; }
  box.innerHTML = rows.map(r => {
    const soon = r.expires_in_days > 0 && r.expires_in_days <= 7;
    return '<div class="row' + (soon ? ' warn' : '') + '">' + esc(r.path) +
      ' <span class="muted">나이 ' + r.age_days + 'd · 만료 ' +
      (r.expires_in_days > 0 ? r.expires_in_days + 'd 후' : '경과') + '</span></div>';
  }).join('');
}
```
참고: `esc`(HTML 이스케이프)·`jget`은 기존 app.js에 있다. 없으면 동일 파일의 기존 렌더 함수가 쓰는 이스케이프 헬퍼를 그대로 써라.

- [ ] **Step 3: loadArtifacts에 retention 연결 + loadMcp 호출**

기존 `loadArtifacts()`(B단계, `/api/artifacts` fetch)에서 받은 데이터에 `renderRetention(d.retention)` 호출을 추가하고, 스캔 완료 후 집계 로드 시퀀스(예: `loadAggregates`)에 `loadMcp()`를 추가하라. 정확한 위치는 `grep -n "loadArtifacts\|loadAggregates\|/api/artifacts" app.js`.
```javascript
// loadArtifacts 내부, d 수신 후:
    renderRetention(d.retention);
// 집계 로드 시퀀스에:
    loadMcp();
```

- [ ] **Step 4: app.css에 스타일 추가**

```css
.mcp .row, .retention .row { padding: 2px 0; font-size: 12px; border-bottom: 1px solid var(--line, #eee); }
.mcp .sub, .retention .sub { margin-top: 6px; font-weight: 600; font-size: 11px; opacity: .8; }
.warn { color: #b00020; font-weight: 600; }
.retention .row.warn { color: #b00020; }
```

- [ ] **Step 5: JS 문법 + 전체 확인**

Run: `node --check clfx/web/static/app.js && python -m pytest -q`
Expected: `node` 무출력(성공), pytest 전체 PASS.

- [ ] **Step 6: Commit**

```bash
git add clfx/web/static/index.html clfx/web/static/app.js clfx/web/static/app.css
git commit -m "feat(ui): MCP 연결흔적 + tmp 보존기간 패널"
```

---

## 최종 검증 (모든 Task 후)

- [ ] `python -m pytest -q` — 전체 green(기존 229 + 신규 ~13).
- [ ] `node --check clfx/web/static/app.js` — 성공.
- [ ] `grep -nE "open\([^)]*['\"][wax]|os\.remove|os\.unlink|shutil\.(rm|move|copy)|\.write\(" clfx/analyze/mcp.py` — read-only 위반 0건.
- [ ] `test_scan_equivalent_to_sequential` 통과 — 파서 mcp 추가가 무손실(병렬=순차).
- [ ] 스모크: `clfx serve` 후 스캔 → `GET /api/mcp` 200 + 계약 키, `GET /api/artifacts`에 `retention` 키. `.mcp.json` env 값이 `‹secret›`로 마스킹됐는지 응답 확인(로컬 보안).

---

## Self-Review

**1. Spec coverage** (피드백확장 spec ⑧):
- "흩어진 .mcp.json + 글로벌 + transcript MCP 호출 통합 1차" → Task 4(.mcp.json)·5(글로벌+프로젝트 전수)·2+6(transcript 호출). ✓
- "GET /api/mcp" (spec line 82) → Task 9. ✓
- "Prefetch 상관(보조)" / "Prefetch 파싱 보류"(line 97) → 범위 제외 명시. ✓
- "tmp retention" → Task 7. ✓
- secret 마스킹 유지 → Task 3(_mask_config) + enrich 자동 마스킹(Task 2 preview). ✓

**2. Placeholder scan**: 모든 코드 스텝에 실코드. "적절히 처리" 류 없음. errors 수집은 구체 코드로 명시. ✓

**3. Type consistency**:
- `find_mcp_configs` → `{"configs":[...], "errors":[...]}` (Task 5 정의, Task 6 `mcp_summary`가 `cfg["configs"]`/`cfg["errors"]`로 소비). ✓
- config row 키(server/scope/project/command/args/type/url/env_keys/source_file) — Task 5 정의, Task 10 UI가 server/scope/command/env_keys 소비. ✓
- usage row 키(server/tool/count/first_ts/last_ts/sessions) — Task 6 정의, Task 8 테스트·Task 10 UI 일치. ✓
- `tmp_retention` → `{"retention":[...], "errors":[...]}` (Task 7), `forensic_scan`이 `ret["retention"]`/`ret["errors"]` 소비(Task 8). ✓
- `mcp_payload(engine, roots)` (Task 8) ↔ server 호출 `mcp_payload(eng, roots)` (Task 9). ✓
- `ServerState.mcp` 기본값 5키 == `mcp_summary` 반환 5키. ✓

이상 없음.

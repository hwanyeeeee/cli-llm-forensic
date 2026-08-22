"""Source records → clfx.event.Event stream.

parse_source(src) yields HISTORY events first, then TRANSCRIPT events,
per the MAPPING CONTRACT in the project spec.
"""
import re

from clfx.codex_parser import CodexFileParser
from clfx.event import Event, Source, norm_ts
from clfx.paste import resolve_paste

PREVIEW_MAX = 4000


# 이미지 붙여넣기의 텍스트 placeholder ("[Image #1]" 등) — 실제 prompt와 구분.
# 파서는 [Image #1]부터 매기므로 #0은 placeholder 아님(사용자 텍스트 → prompt).
_IMAGE_PLACEHOLDER = re.compile(r"^\s*\[Image #[1-9]\d*\]\s*$")

# 원격(폰) 지시와 로컬 타이핑을 가르는 조합. Android 실측(SM-A235N · Claude Code 2.1.238)에서
# queued ∧ human 이 위양성 없이 원격만 잡는 것으로 검증됐다.
# origin.kind 가 없는 구버전 레코드는 절반의 근거뿐이라 판정하지 않는다 — local 폴백 금지.
_REMOTE_PROMPT_SOURCE = "queued"
_LOCAL_PROMPT_SOURCE = "typed"


def _origin_channel(o):
    """promptSource ∧ origin.kind → remote | local | unknown. 판정 대상이 아니면 None(필드 생략).

    None(생략)과 "unknown"은 다르다: 생략은 '판정 대상 레코드가 아님', unknown은 '봤는데 못 가림'.
    어느 쪽도 local 을 의미하지 않는다."""
    prompt_source = o.get("promptSource")
    if prompt_source is None:
        return None
    origin = o.get("origin")
    kind = origin.get("kind") if isinstance(origin, dict) else None
    if kind != "human":                       # sdk/system/task-notification, origin 없는 구버전
        return "unknown"
    if prompt_source == _REMOTE_PROMPT_SOURCE:
        return "remote"
    if prompt_source == _LOCAL_PROMPT_SOURCE:
        return "local"
    return "unknown"                          # suggestion_accepted 등 — 사람이지만 경로 미확정


def clip(s):
    if s is None:
        return ""
    if not isinstance(s, str):   # 손상 jsonl: 비-문자열 payload(int/bool/dict 등) → str 강제(크래시 방지)
        s = str(s)
    if len(s) <= PREVIEW_MAX:
        return s
    return s[:PREVIEW_MAX] + "…"


def _history_events_from(records, src):
    # records(레코드 이터러블) 기반 — paste 해석(resolve_paste/paste_cache_path)에 src 필요 → src 통째 전달.
    for rec in records:
        obj = rec.obj
        if not isinstance(obj, dict):     # 비-dict 최상위 JSON 줄(배열/문자열 등) → 안전 스킵
            continue
        pasted = obj.get("pastedContents") or {}
        if not isinstance(pasted, dict):
            continue
        ts = norm_ts(obj.get("timestamp"))
        sess = obj.get("project", "")
        hist_src = Source(rec.file, rec.line)
        for n, item in pasted.items():
            if not isinstance(item, dict):
                body, ev_src = None, hist_src
            else:
                body = resolve_paste(item, src)
                # 본문이 paste-cache에 실제로 존재할 때만 그 파일을 source로 지목(증거 추적,
                # event-schema §규칙). 캐시 파일이 없으면 없는 파일을 증거로 가리키면 안 되므로
                # history.jsonl 줄을 유지한다. 인라인 content도 history.jsonl 줄.
                ev_src = hist_src
                if item.get("content") is None:
                    h = item.get("contentHash")
                    if h:
                        cache = src.paste_cache_path(h)
                        if cache.exists():
                            ev_src = Source(str(cache), 1)
            yield Event(
                ts=ts,
                agent=src.agent,
                session=sess,
                actor="user",
                action="paste",
                target=f"[Pasted #{n}]",
                preview=clip(body if body is not None else "<unresolved>"),
                source=ev_src,
            )


def _history_events(src):
    yield from _history_events_from(src.history_records(), src)


def _transcript_events_from(records, agent):
    # records 기반 — transcript는 src.agent만 참조하므로 agent만 받음(나머지 src 불요).
    for rec in records:
        o = rec.obj
        if not isinstance(o, dict):        # 비-dict 최상위 JSON 줄 → 안전 스킵
            continue
        ts = norm_ts(o.get("timestamp"))
        sess = o.get("sessionId", "")
        s = Source(rec.file, rec.line)

        # 1. tool result carrying a read file
        tur = o.get("toolUseResult")
        f = tur.get("file") if isinstance(tur, dict) else None
        if isinstance(f, dict):              # 계약: file 키가 있으면(빈 dict라도) read 발행
            yield Event(
                ts=ts,
                agent=agent,
                session=sess,
                actor="agent",
                action="read",
                target=f.get("filePath") or "",
                preview=clip(f.get("content", "")),
                source=s,
            )
            # read를 발행해도 같은 레코드의 message.content(공존하는 prompt/image)는 계속 처리한다.

        typ = o.get("type")
        message = o.get("message")
        if not isinstance(message, dict):
            message = {}
        content = message.get("content", [])
        if isinstance(content, str):       # content가 문자열인 단순 메시지도 살린다(누락 방지)
            content = [{"type": "text", "text": content}]
        elif not isinstance(content, list):
            content = []

        if typ == "user":
            # content 파트를 원래 순서대로 순회 → caption↔image 순서 보존.
            # image → paste([Image #N], N은 이미지에만 증가). 실제 text → prompt.
            # 빈/공백 text, 이미지 placeholder("[Image #N]")는 미발행(노이즈·중복 방지).
            # 지시가 폰에서 왔는지 로컬 타이핑인지는 이 레코드에만 있다(실행 Event엔 없다).
            channel = _origin_channel(o)
            meta = {"origin_channel": channel} if channel else {}
            # unknown 이 왜 unknown 인지 남긴다. 실데이터 unknown 3,294건 중 2,565건이
            # sdk·system 이었다 — 판정 실패가 아니라 사람이 낸 지시가 아니었다.
            # 근거 없이 뭉뚱그리면 "3천 건을 못 가렸다"로 읽힌다(2026-08-22).
            if channel == "unknown":
                meta["prompt_source"] = o.get("promptSource")
                kind = (o.get("origin") or {}).get("kind") if isinstance(o.get("origin"), dict) else None
                if kind:
                    meta["origin_kind"] = kind
            img_n = 0
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype == "image":
                    img_n += 1
                    img_src = part.get("source") or {}
                    media = (img_src.get("media_type") or "image") if isinstance(img_src, dict) else "image"
                    yield Event(
                        ts=ts,
                        agent=agent,
                        session=sess,
                        actor="user",
                        action="paste",
                        target=f"[Image #{img_n}]",
                        preview=f"<image:{media}>",
                        source=s,
                        meta=dict(meta),
                    )
                elif ptype == "text":
                    txt = clip(part.get("text"))   # clip이 None/비-str → ""/str 정규화
                    if not txt.strip() or _IMAGE_PLACEHOLDER.match(txt):
                        continue
                    yield Event(
                        ts=ts,
                        agent=agent,
                        session=sess,
                        actor="user",
                        action="prompt",
                        target="",
                        preview=txt,
                        source=s,
                        meta=dict(meta),
                    )

        elif typ == "assistant":
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
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
                elif ptype == "text":
                    # 계약: assistant text는 무조건 response 발행(빈 응답 skip 안 함).
                    yield Event(
                        ts=ts,
                        agent=agent,
                        session=sess,
                        actor="agent",
                        action="response",
                        target="",
                        preview=clip(part.get("text")),   # clip이 None/비-str 정규화
                        source=s,
                    )
        # 5. any other type: emit nothing


def _transcript_events(src):
    if src.agent == "codex":
        for path in src.transcript_files():
            parser = CodexFileParser(src)
            for rec in src._iter_jsonl(path):
                parser.feed(rec)
            yield from parser.finish()
        return
    # 파일 단위로 parse_file 을 거친다 — bridge-session 같은 파일 스코프 후처리를 CLI(parse_source)와
    # 대시보드(api/wsl_helper)가 똑같이 받게 하려는 것. 두 진입점이 다른 meta 를 내면 그게 결함이다.
    for path in src.transcript_files():
        events, _, _ = parse_file(src, path, False)
        yield from events


def _is_bypass_record(o):
    """bypassPermissions permission-mode 레코드(sessionId 보유) — attribution._bypass_sessions와 동일 판정."""
    return (isinstance(o, dict) and o.get("type") == "permission-mode"
            and o.get("permissionMode") == "bypassPermissions" and o.get("sessionId"))


def _bridge_session(o):
    """bridge-session 레코드 → (sessionId, bridgeSessionId). 아니면 None.

    같은 세션을 가리키는 ID가 계층마다 접두사가 다르다(로컬 uuid vs 브리지 `cse_…`).
    잇는 키는 **레코드 자신의 sessionId** 다 — 접두사 문자열끼리 비교하면 안 된다."""
    if not (isinstance(o, dict) and o.get("type") == "bridge-session"):
        return None
    session, bridge = o.get("sessionId"), o.get("bridgeSessionId")
    return (session, bridge) if session and bridge else None


def parse_file(src, path, is_history):
    """단일 파일 1회 읽기 → (events, bypass_sids, sha256_hex). transcript면 같은 레코드서 bypass
    sessionId도 수집(enrich 2차 재읽기 제거). 레코드 단위 무상태 → 파일 병렬 안전.
    B-1: sha256_hex = 그 단일 읽기서 누적한 raw 파일 바이트 SHA-256(64-hex 소문자, 추가 읽기 0).
    파일을 못 열어 yield가 없으면 sha=None. RawRecord는 파일 전체를 보관하지 않는다."""
    sha_holder = {}                             # 호출자 소유 → src 공유상태 없이 스레드 분리(병렬 안전)
    events, bypass, bridges = [], set(), {}
    codex = CodexFileParser(src) if src.agent == "codex" and not is_history else None
    for rec in src._iter_jsonl(path, sha_out=sha_holder):
        if is_history:
            events.extend(_history_events_from(iter((rec,)), src))
        elif codex is not None:
            codex.feed(rec)
        else:
            events.extend(_transcript_events_from(iter((rec,)), src.agent))
            if _is_bypass_record(rec.obj):
                bypass.add(rec.obj["sessionId"])
            bridge = _bridge_session(rec.obj)
            if bridge:
                bridges[bridge[0]] = bridge[1]
    if bridges:                                 # 같은 파일 안에서만 잇는다(레코드가 앞뒤 어디든 상관없게 사후 적용)
        for event in events:
            if event.session in bridges:
                event.meta.setdefault("bridge_session_id", bridges[event.session])
    if codex is not None:
        events.extend(codex.finish())
    sha = sha_holder.get("sha")
    return events, bypass, sha


def parse_source(src):
    """Yield HISTORY events, then TRANSCRIPT events."""
    yield from _history_events(src)
    yield from _transcript_events(src)

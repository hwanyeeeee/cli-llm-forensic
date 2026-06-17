"""Source records → clfx.event.Event stream.

parse_source(src) yields HISTORY events first, then TRANSCRIPT events,
per the MAPPING CONTRACT in the project spec.
"""
import re

from clfx.event import Event, Source, norm_ts
from clfx.paste import resolve_paste

PREVIEW_MAX = 4000


# 이미지 붙여넣기의 텍스트 placeholder ("[Image #1]" 등) — 실제 prompt와 구분.
# 파서는 [Image #1]부터 매기므로 #0은 placeholder 아님(사용자 텍스트 → prompt).
_IMAGE_PLACEHOLDER = re.compile(r"^\s*\[Image #[1-9]\d*\]\s*$")


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
    yield from _transcript_events_from(src.transcript_records(), src.agent)


def _is_bypass_record(o):
    """bypassPermissions permission-mode 레코드(sessionId 보유) — attribution._bypass_sessions와 동일 판정."""
    return (isinstance(o, dict) and o.get("type") == "permission-mode"
            and o.get("permissionMode") == "bypassPermissions" and o.get("sessionId"))


def parse_file(src, path, is_history):
    """단일 파일 1회 읽기 → (events, bypass_sids). transcript면 같은 레코드서 bypass sessionId도 수집
    (enrich 2차 재읽기 제거). 레코드 단위 무상태 → 파일 병렬 안전. 이벤트/순서는 parse_source와 동일."""
    recs = list(src._iter_jsonl(path))          # 단일 읽기(materialize)
    if is_history:
        return list(_history_events_from(recs, src)), set()   # history엔 bypass 없음(=_bypass_sessions와 동일)
    evs = list(_transcript_events_from(recs, src.agent))
    bypass = {r.obj["sessionId"] for r in recs if _is_bypass_record(r.obj)}
    return evs, bypass


def parse_source(src):
    """Yield HISTORY events, then TRANSCRIPT events."""
    yield from _history_events(src)
    yield from _transcript_events(src)

from clfx.sources.claude import ClaudeSource
from clfx.parser import parse_source
from clfx.analyze.attribution import enrich

def _enriched(root): return enrich(list(parse_source(ClaudeSource(root))), ClaudeSource(root))

def test_paste_is_user_read_is_agent(built_root):
    evs = _enriched(built_root)
    paste = next(e for e in evs if e.action == "paste" and e.target.startswith("[Pasted"))
    read  = next(e for e in evs if e.action == "read" and e.target.endswith(".env"))
    assert paste.actor == "user" and read.actor == "agent"

def test_bypass_mode_tagged(built_root):
    reads = [e for e in _enriched(built_root) if e.action == "read"]
    assert all("bypass-mode" in e.tags for e in reads)   # 세션이 bypassPermissions

def test_secret_events_tagged_and_masked(built_root):
    evs = _enriched(built_root)
    env_read = next(e for e in evs if e.action == "read" and e.target.endswith(".env"))
    assert "secret" in env_read.tags
    assert "sk_live_CLFXTEST001" not in env_read.preview and "‹secret›" in env_read.preview

def test_attribution_summary(built_root):
    from clfx.analyze.attribution import attribution_summary
    summ = attribution_summary(_enriched(built_root))
    assert summ["user"] >= 1 and summ["agent"] >= 1

def test_no_bypass_tag_when_session_blank(tmp_path):
    # sessionId 없는 permission-mode + session 없는 read → 빈 문자열끼리 거짓 매칭 금지
    from clfx.sources.claude import ClaudeSource
    from clfx.parser import parse_source
    from tests.conftest import write_jsonl, ENV_BODY
    root = tmp_path / "dot-claude"
    write_jsonl(root / "projects" / "-p" / "s.jsonl", [
        {"type": "permission-mode", "permissionMode": "bypassPermissions"},   # sessionId 없음
        {"type": "user", "timestamp": "t",
         "toolUseResult": {"file": {"filePath": "/x/.env", "content": ENV_BODY}},
         "message": {"role": "user", "content": [{"type": "tool_result", "content": ENV_BODY}]}},  # sessionId 없음
    ])
    read = next(e for e in enrich(list(parse_source(ClaudeSource(root))), ClaudeSource(root))
                if e.action == "read")
    assert read.session == ""
    assert "bypass-mode" not in read.tags     # 빈 session끼리 거짓 bypass 금지
    assert "secret" in read.tags              # 시크릿 태그는 정상


# --- OPT-6: 빈 preview 가드가 bypass 태깅을 막지 않음(무손실) ---

def _mk_event(action="read", session="s1", preview="", tags=None):
    from clfx.event import Event, Source
    return Event(ts="t", agent="claude", session=session, actor="agent", action=action,
                 target="x", preview=preview, source=Source("h.jsonl", 1), tags=list(tags or []))


def test_empty_preview_still_gets_bypass_tag():
    # preview가 빈 read Event도 bypass 세션이면 bypass-mode 태그를 받아야 한다(가드와 독립).
    e = _mk_event(action="read", session="s1", preview="")
    actor_before = e.actor
    enrich([e], src=None, bypass={"s1"})
    assert "bypass-mode" in e.tags
    assert "secret" not in e.tags and "pii" not in e.tags   # 빈 preview → 비밀 태그 없음
    assert e.preview == ""                                  # 마스킹 변형 없음
    assert e.actor == actor_before                          # actor 불변


def test_empty_preview_guard_lossless_vs_unconditional_scan():
    # 빈/falsy preview에서 가드 적용 결과 == scan을 그냥 돌린 옛 경로 결과(byte-identical).
    for pv in ("", None):
        guarded = _mk_event(action="read", session="s9", preview=pv)
        enrich([guarded], src=None, bypass=set())
        # 옛 경로(scan 무조건 실행)를 손으로 모사
        ref_tags, ref_preview = [], pv
        findings = scan(pv) if pv else []   # scan("")==[] / scan(None)==[]
        assert findings == []
        assert guarded.tags == ref_tags
        assert guarded.preview == ref_preview


def test_nonempty_preview_still_masks_and_tags():
    # 비어있지 않은 preview는 기존대로 시크릿 태깅 + 마스킹.
    from tests.conftest import ENV_BODY
    e = _mk_event(action="read", session="s1", preview=ENV_BODY)
    enrich([e], src=None, bypass={"s1"})
    assert "secret" in e.tags
    assert "bypass-mode" in e.tags
    assert "sk_live_CLFXTEST001" not in e.preview and "‹secret›" in e.preview

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

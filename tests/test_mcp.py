import json as _json
import os

from clfx.analyze.mcp import (
    _mask_config,
    parse_mcp_config,
    find_mcp_configs,
    mcp_usage_from_events,
    mcp_summary,
)
from clfx.event import Event, Source


# --- Task 3: _mask_config ---------------------------------------------------

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


# --- F3: 키이름 기준 강제 마스킹(저엔트로피 토큰도 마스킹) ---------------------

def test_mask_config_masks_low_entropy_tokens_by_keyname():
    cfg = {"url": "https://h/sse?token=plainsecret123&x=ok",
           "args": ["--token", "plainsecret123", "--api-key=abc123",
                    "--header", "Authorization: Bearer plainsecret123"],
           "command": "node"}
    out = _mask_config(cfg)
    blob = repr(out)
    assert "plainsecret123" not in blob and "abc123" not in blob   # 저엔트로피 토큰 전부 마스킹
    assert "x=ok" in out["url"]                                    # 비밀 아닌 값 보존
    assert out["command"] == "node"                               # command 유지


# --- Task 4: parse_mcp_config -----------------------------------------------

def test_parse_mcp_config_returns_masked_servers():
    servers = parse_mcp_config("tests/fixtures/mcp/proj-a/.mcp.json")
    assert set(servers.keys()) == {"playwright", "secret-server"}   # 모든 서버(무skip)
    assert servers["playwright"]["command"] == "npx"
    assert servers["secret-server"]["env"] == {"TOKEN": "‹secret›"} # env 값 마스킹


# --- Task 5: find_mcp_configs -----------------------------------------------

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


# --- Task 6: mcp_usage_from_events + mcp_summary ----------------------------

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


# --- #5: 설정탐지 확장 (커넥터·플러그인·enabledMcpjsonServers) -----------------

def test_find_mcp_configs_reads_extra_sources(tmp_path):
    root = tmp_path / ".claude"
    root.mkdir()
    proj = tmp_path / "proj-x"
    proj.mkdir()
    (tmp_path / ".claude.json").write_text(_json.dumps({
        "claudeAiMcpEverConnected": ["claude_ai_Notion"],
        "pluginUsage": {"claude-mem@mp": 1},
        "projects": {str(proj): {"enabledMcpjsonServers": ["pyghidra"]}},
    }), encoding="utf-8")

    out = find_mcp_configs([str(root)])
    by_server = {c["server"]: c for c in out["configs"]}
    # claude.ai 커넥터 → scope="connector"
    assert "claude_ai_Notion" in by_server
    assert by_server["claude_ai_Notion"]["scope"] == "connector"
    # enabledMcpjsonServers → scope="project"
    assert "pyghidra" in by_server
    assert by_server["pyghidra"]["scope"] == "project"
    assert by_server["pyghidra"]["project"] == str(proj)
    # 플러그인 prefix 수집 (정렬)
    assert out["plugin_prefixes"] == ["plugin_claude-mem"]


def test_mcp_summary_recognizes_extra_config_sources(tmp_path):
    root = tmp_path / ".claude"
    root.mkdir()
    proj = tmp_path / "proj-x"
    proj.mkdir()
    (tmp_path / ".claude.json").write_text(_json.dumps({
        "claudeAiMcpEverConnected": ["claude_ai_Notion"],
        "pluginUsage": {"claude-mem@mp": 1},
        "projects": {str(proj): {"enabledMcpjsonServers": ["pyghidra"]}},
    }), encoding="utf-8")
    evs = [
        _ev("mcp__claude_ai_Notion__fetch", "2026-06-18T01:00:00Z"),
        _ev("mcp__plugin_claude-mem_mcp-search__q", "2026-06-18T01:00:01Z"),
        _ev("mcp__pyghidra__decompile", "2026-06-18T01:00:02Z"),
        _ev("mcp__rogue__x", "2026-06-18T01:00:03Z"),
    ]
    out = mcp_summary([str(root)], evs)
    # 셋 다 설정출처 인식 → 진짜 미설정만 남음
    assert out["used_unconfigured"] == ["rogue"]
    assert out["plugin_prefixes"] == ["plugin_claude-mem"]


# --- [B2]: 이름 정규화 매칭 (커넥터 표기 vs usage명 표기차 흡수) ----------------

def test_mcp_summary_normalizes_connector_name_vs_usage(tmp_path):
    # 커넥터는 'claude.ai Notion'(공백·점), usage는 'claude_ai_Notion'(밑줄·대문자) — 표기 불일치.
    root = tmp_path / ".claude"
    root.mkdir()
    (tmp_path / ".claude.json").write_text(_json.dumps({
        "claudeAiMcpEverConnected": ["claude.ai Notion"],
    }), encoding="utf-8")
    evs = [
        _ev("mcp__claude_ai_Notion__fetch", "2026-06-18T01:00:00Z"),
        _ev("mcp__rogue__x", "2026-06-18T01:00:01Z"),
    ]
    out = mcp_summary([str(root)], evs)
    # 정규화 매칭 → 커넥터로 인식되어 used_unconfigured에서 빠짐
    assert "claude_ai_Notion" not in out["used_unconfigured"]
    # 진짜 미설정만 남음 (표시는 원본 usage명)
    assert out["used_unconfigured"] == ["rogue"]
    # configured_unused도 정규화 매칭 → 사용됨으로 인식되어 비어 있음 (표시는 원본 커넥터명)
    assert "claude.ai Notion" not in out["configured_unused"]
    assert out["configured_unused"] == []

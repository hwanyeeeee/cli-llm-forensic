"""23단계: 원격제어 마커 3종 + enrollment + 뷰어 노출.

이 파일이 지키는 계약은 하나다 — **마커는 "설정된 적 있음"까지만 말한다.**
그래서 테스트 대부분이 "이렇게는 말하면 안 된다"를 단언한다.
"""
import json

import pytest

from clfx.codex_sqlite import enrollment_marker
from clfx.event import Event, Source
from clfx.query.engine import QueryEngine
from clfx.sources import remote_control_markers, source_for
from clfx.sources.claude import ClaudeSource
from clfx.sources.codex import CodexSource
from clfx.sources.markers import marker, summarize
from clfx.web.api import remote_control_payload


def _claude_root(tmp_path, flags=None, sessions=None):
    """~/.claude 레이아웃. .claude.json 은 .claude/ **옆**이라 부모에 쓴다."""
    root = tmp_path / ".claude"
    (root / "projects").mkdir(parents=True)
    if flags is not None:
        (tmp_path / ".claude.json").write_text(json.dumps(flags), encoding="utf-8")
    if sessions is not None:
        directory = root / "sessions"
        directory.mkdir()
        for name, obj in sessions.items():
            directory.joinpath(name).write_text(json.dumps(obj), encoding="utf-8")
    return root


def _by_kind(markers):
    return {row["kind"]: row for row in markers}


# --- signal 규칙: 관측 부재에 기본값을 주지 않는다 ---------------------------

def test_missing_file_is_unknown_not_none(tmp_path):
    """파일이 없으면 '음성'이 아니라 '판정 불가'다. none 은 '봤는데 음성'을 뜻한다."""
    row = _by_kind(remote_control_markers(ClaudeSource(_claude_root(tmp_path))))
    assert row["claude_remote_control_flags"]["status"] == "missing"
    assert row["claude_remote_control_flags"]["signal"] == "unknown"


def test_marker_forces_unknown_when_not_observed():
    """호출자가 실수로 configured 를 넘겨도 status 가 observed 가 아니면 unknown 으로 내린다."""
    row = marker("k", "claude", "/x", "unreadable", "configured", "n")
    assert row["signal"] == "unknown"


def test_volatile_marker_cannot_be_none():
    """휘발성 증거의 부재는 음성 근거가 아니다 — 코드가 막는다."""
    with pytest.raises(ValueError, match="휘발성"):
        marker("k", "claude", "/x", "observed", "none", "n", volatile=True)


def test_flags_all_false_is_none_not_unknown(tmp_path):
    """비휘발성 파일을 읽었고 키도 다 있는데 값이 음성 → 그건 실제 음성 관측이다."""
    root = _claude_root(tmp_path, flags={"hasUsedRemoteControl": False,
                                         "remoteDialogSeen": False,
                                         "remoteControlUpsellSeenCount": 0})
    row = _by_kind(remote_control_markers(ClaudeSource(root)))["claude_remote_control_flags"]
    assert row["signal"] == "none" and row["absent_keys"] == []


def test_flags_present_but_no_keys_is_unknown(tmp_path):
    """파일은 읽혔지만 이 축을 말해주는 키가 하나도 없다 → 판정 불가(구버전 CLI)."""
    root = _claude_root(tmp_path, flags={"numStartups": 3})
    row = _by_kind(remote_control_markers(ClaudeSource(root)))["claude_remote_control_flags"]
    assert row["signal"] == "unknown" and row["values"] == {}
    assert row["absent_keys"] == ["hasUsedRemoteControl", "remoteDialogSeen",
                                  "remoteControlUpsellSeenCount"]


def test_absent_key_is_not_flattened_into_false(tmp_path):
    """없는 키를 values 에 false 로 채우면 구버전과 '꺼 둠'이 구분되지 않는다."""
    root = _claude_root(tmp_path, flags={"hasUsedRemoteControl": True})
    row = _by_kind(remote_control_markers(ClaudeSource(root)))["claude_remote_control_flags"]
    assert row["values"] == {"hasUsedRemoteControl": True}
    assert row["absent_keys"] == ["remoteDialogSeen", "remoteControlUpsellSeenCount"]


def test_corrupt_json_is_unreadable_not_missing(tmp_path):
    """손상 JSON 을 빈 dict 로 뭉개면 '파일이 없다'와 구분이 사라진다."""
    root = _claude_root(tmp_path)
    (tmp_path / ".claude.json").write_text("{not json", encoding="utf-8")
    row = _by_kind(remote_control_markers(ClaudeSource(root)))["claude_remote_control_flags"]
    assert row["status"] == "unreadable" and row["signal"] == "unknown"


# --- bridgeSessionId: 휘발성 증거 -------------------------------------------

def test_bridge_absent_reports_unknown_with_volatile_flag(tmp_path):
    """브리지가 하나도 없어도 '미사용'이라 말하지 않는다 — volatile 로 그 이유를 남긴다."""
    root = _claude_root(tmp_path, sessions={
        "1.json": {"pid": 1, "sessionId": "a"},
        "2.json": {"pid": 2, "sessionId": "b", "bridgeSessionId": None},
    })
    row = _by_kind(remote_control_markers(ClaudeSource(root)))["claude_bridge_sessions"]
    assert row["signal"] == "unknown" and row["volatile"] is True
    assert "정상종료" in row["note"]
    # 키 없음(384건 유형)과 명시적 null 은 다른 관측이다 — 따로 센다.
    assert row["values"]["no_bridge_key"] == 1 and row["values"]["explicit_null"] == 1
    assert row["values"]["with_bridge"] == 0


def test_bridge_present_reports_join_keys(tmp_path):
    """실데이터처럼 한 세션의 pid 파일이 여럿 남는다 — 세션 수가 아니라 파일 수임을 구분해 센다."""
    root = _claude_root(tmp_path, sessions={
        "10.json": {"pid": 10, "sessionId": "s1", "bridgeSessionId": "session_A"},
        "11.json": {"pid": 11, "sessionId": "s1", "bridgeSessionId": "session_A"},
        "12.json": {"pid": 12, "sessionId": "s2", "bridgeSessionId": "session_B"},
    })
    row = _by_kind(remote_control_markers(ClaudeSource(root)))["claude_bridge_sessions"]
    assert row["signal"] == "configured"
    assert row["values"]["with_bridge"] == 3 and row["values"]["distinct_bridge_ids"] == 2
    assert [s["bridge_session_id"] for s in row["sessions"]] == [
        "session_A", "session_A", "session_B"]


def test_bridge_marker_does_not_leak_cwd(tmp_path):
    """세션 파일엔 cwd 가 있다. 마커는 조인 키만 싣는다 — 무관한 경로를 payload 로 흘리지 않는다."""
    root = _claude_root(tmp_path, sessions={
        "1.json": {"pid": 1, "sessionId": "s", "bridgeSessionId": "b",
                   "cwd": "/home/secret/project"},
    })
    row = _by_kind(remote_control_markers(ClaudeSource(root)))["claude_bridge_sessions"]
    assert set(row["sessions"][0]) == {"pid", "session_id", "bridge_session_id"}
    assert "secret" not in json.dumps(row, ensure_ascii=False)


def test_missing_sessions_dir_is_unknown(tmp_path):
    root = _claude_root(tmp_path)
    row = _by_kind(remote_control_markers(ClaudeSource(root)))["claude_bridge_sessions"]
    assert row["status"] == "missing" and row["signal"] == "unknown"


# --- Codex 호스트 스위치 -----------------------------------------------------

def test_codex_setting_true_is_configured(tmp_path):
    root = tmp_path / ".codex"
    (root / "app-server-daemon").mkdir(parents=True)
    (root / "app-server-daemon" / "settings.json").write_text(
        json.dumps({"remoteControlEnabled": True}), encoding="utf-8")
    row = _by_kind(remote_control_markers(CodexSource(root)))["codex_remote_control_setting"]
    assert row["signal"] == "configured"
    assert "채널이 실제로 연결" in row["note"]     # true ≠ 살아 있음을 문구가 못 박는다


def test_codex_setting_missing_is_unknown(tmp_path):
    root = tmp_path / ".codex"
    root.mkdir()
    row = _by_kind(remote_control_markers(CodexSource(root)))["codex_remote_control_setting"]
    assert row["status"] == "missing" and row["signal"] == "unknown"


# --- enrollment: 0행 ≠ 미사용 ------------------------------------------------

def test_empty_enrollments_is_unknown_not_none():
    """enroll 이 MFA 로 거부돼도 0행이다 — 0행을 '음성'으로 부르면 없는 사실을 만든다."""
    row = enrollment_marker({"databases": [{"path": "/db/state_5.sqlite", "role": "state"}],
                             "remote_control_enrollments": []})
    assert row["signal"] == "unknown"
    assert "0행은 미사용이 아니다" in row["note"]


def test_enrollments_present_lists_environment_only():
    row = enrollment_marker({
        "databases": [{"path": "/db/state_5.sqlite", "role": "state"}],
        "remote_control_enrollments": [{"environment_id": "env-1", "server_name": "box",
                                        "websocket_url": "wss://secret/tok",
                                        "account_id": "acct-9"}]})
    assert row["signal"] == "configured" and row["values"]["enrollments"] == 1
    # 자격증명·URL 은 안 싣는다 — 조사자가 알아야 하는 건 '어느 환경에 등록됐나'다.
    dumped = json.dumps(row, ensure_ascii=False)
    assert "wss://secret" not in dumped and "acct-9" not in dumped
    assert row["enrollments"][0]["environment_id"] == "env-1"


def test_enrollment_drops_empty_strings_but_keeps_false():
    """빈 문자열은 관측이 아니라 빈 칸이다(실데이터 app_server_client_name=""). 0/False 는 값이다."""
    row = enrollment_marker({
        "databases": [{"path": "/db/state_5.sqlite", "role": "state"}],
        "remote_control_enrollments": [{"environment_id": "env-1",
                                        "app_server_client_name": "",
                                        "remote_control_enabled": 0}]})
    listed = row["enrollments"][0]
    assert "app_server_client_name" not in listed
    assert listed["remote_control_enabled"] == 0


def test_no_state_db_is_missing_not_silent():
    """DB 를 못 찾았을 때 마커를 아예 안 내면 '등록 없음'과 '안 봤음'이 구분되지 않는다."""
    row = enrollment_marker({"databases": []})
    assert row["status"] == "missing" and row["signal"] == "unknown"


# --- 요약: 종합 boolean 을 만들지 않는다 -------------------------------------

def test_summary_claim_never_says_unused():
    empty = summarize([])
    assert empty["claim"] == "not_observed"           # "not_used" 라는 값은 없다
    assert empty["counts"] == {"configured": 0, "none": 0, "unknown": 0}
    hot = summarize([marker("k", "claude", "/x", "observed", "configured", "n")])
    assert hot["claim"] == "configured_before"        # "used" 가 아니다


def test_summary_caveats_carry_the_three_traps():
    caveats = " ".join(summarize([])["caveats"])
    assert "0행은 미사용이 아니다" in caveats
    assert "채널이 살아 있다는 뜻은 아니다" in caveats
    assert "정상종료 시 삭제된다" in caveats


# --- 뷰어 payload: 이벤트 축 ------------------------------------------------

def _ev(meta=None):
    return Event(ts="2026-08-22T00:00:00Z", agent="claude", session="s", actor="user",
                 action="prompt", target="", preview="", source=Source("f", 1),
                 meta=meta or {})


def test_payload_separates_absent_from_unknown():
    """필드 부재(not_observed)와 unknown 은 다른 칸이다. 둘 다 local 이 아니다."""
    engine = QueryEngine([_ev({"origin_channel": "remote"}), _ev({"origin_channel": "local"}),
                          _ev({"origin_channel": "unknown"}), _ev()])
    engine.remote_markers = []
    channels = remote_control_payload(engine)["events"]["origin_channel"]
    assert channels == {"remote": 1, "local": 1, "unknown": 1, "not_observed": 1}


def test_payload_does_not_swallow_unexpected_channel():
    """파서가 낯선 값을 내면 not_observed 로 흡수하지 않는다 — 회귀를 조용히 숨기지 않으려고."""
    engine = QueryEngine([_ev({"origin_channel": "bogus"})])
    engine.remote_markers = []
    channels = remote_control_payload(engine)["events"]["origin_channel"]
    assert channels["bogus"] == 1 and channels["not_observed"] == 0


def test_payload_counts_os_and_bridge():
    engine = QueryEngine([_ev({"origin_channel": "remote", "origin_os": "ios"}),
                          _ev({"bridge_session_id": "session_A"}),
                          _ev({"bridge_session_id": "session_A"})])
    engine.remote_markers = []
    events = remote_control_payload(engine)["events"]
    assert events["origin_os"] == {"ios": 1}
    assert events["bridge_session_events"] == 2
    assert events["bridge_session_ids"] == ["session_A"]


def test_payload_survives_engine_without_markers():
    """스캔 전 엔진에도 /api/remote-control 이 500 을 내면 안 된다."""
    payload = remote_control_payload(QueryEngine([]))
    assert payload["claim"] == "not_observed" and payload["events"]["total"] == 0


# --- 스캔 통합 --------------------------------------------------------------

def test_scan_attaches_markers_for_both_agents(tmp_path):
    from clfx.web.api import scan_to_engine
    claude = _claude_root(tmp_path / "c", flags={"hasUsedRemoteControl": True})
    codex = tmp_path / "x" / ".codex"
    (codex / "sessions").mkdir(parents=True)
    (codex / "app-server-daemon").mkdir()
    (codex / "app-server-daemon" / "settings.json").write_text(
        json.dumps({"remoteControlEnabled": False}), encoding="utf-8")
    engine = scan_to_engine([str(claude), str(codex)])
    kinds = _by_kind(engine.remote_markers)
    assert set(kinds) == {"claude_remote_control_flags", "claude_bridge_sessions",
                          "codex_remote_control_setting", "codex_remote_control_enrollments"}
    assert kinds["claude_remote_control_flags"]["signal"] == "configured"
    assert kinds["codex_remote_control_setting"]["signal"] == "none"
    # sqlite 가 없어도 enrollment 마커는 나온다(침묵 금지).
    assert kinds["codex_remote_control_enrollments"]["signal"] == "unknown"


def test_markers_are_not_events(tmp_path):
    """마커를 Event 로 만들면 같은 사실이 타임라인에 한 줄 더 늘어 과계수가 난다."""
    from clfx.web.api import scan_to_engine
    root = _claude_root(tmp_path, flags={"hasUsedRemoteControl": True},
                        sessions={"1.json": {"pid": 1, "sessionId": "s",
                                             "bridgeSessionId": "b"}})
    engine = scan_to_engine([str(root)])
    assert engine.remote_markers                       # 마커는 있고
    assert engine.timeline() == []                     # 이벤트는 늘지 않는다


def test_markers_read_only(tmp_path):
    """read-only 불변식: 마커 판독도 write/delete 를 발행하지 않는다."""
    from clfx import roio
    root = _claude_root(tmp_path, flags={"hasUsedRemoteControl": True},
                        sessions={"1.json": {"pid": 1, "sessionId": "s"}})
    roio.reset_audit()
    remote_control_markers(ClaudeSource(root))
    assert roio.modes_seen() == ["rb"]                 # 읽기 모드만
    assert roio.write_delete_rename_ops() == 0
    paths = {row["path"] for row in roio.audit_records()}
    assert str(tmp_path / ".claude.json") in paths     # 감사 원장에 실제로 남는다


# --- 위임(WSL) 경로: 경로 재작성 --------------------------------------------

def test_delegate_rewrites_marker_paths():
    """마커 file 도 UNC 로 바꿔야 한다 — 안 그러면 Windows 조사자가 못 여는 경로가 실린다."""
    from clfx import wsl_delegate
    posix, target = "/home/u/.claude", r"\\wsl.localhost\Ubuntu\home\u\.claude"
    row = {"kind": "k", "file": "/home/u/.claude/sessions", "status": "observed"}
    rewritten = wsl_delegate.rewrite_prefix(row["file"], posix, target)
    assert rewritten == r"\\wsl.localhost\Ubuntu\home\u\.claude\sessions"
    # .claude.json 은 루트 **옆**이지만 문자열 프리픽스는 그대로 걸린다(형제 파일도 재작성됨).
    assert (wsl_delegate.rewrite_prefix("/home/u/.claude.json", posix, target)
            == r"\\wsl.localhost\Ubuntu\home\u\.claude.json")


# --- 실데이터(있으면) --------------------------------------------------------

@pytest.mark.parametrize("root,agent", [("~/.claude", "claude"), ("~/.codex", "codex")])
def test_real_home_markers_are_well_formed(root, agent):
    from pathlib import Path
    resolved = Path(root).expanduser()
    if not resolved.is_dir():
        pytest.skip(f"실데이터 없음: {resolved} — 이 환경에서는 마커를 검증하지 못한다")
    markers = remote_control_markers(source_for(str(resolved)))
    assert markers, f"{agent} 마커가 하나도 안 나왔다"
    for row in markers:
        assert row["signal"] in ("configured", "none", "unknown")
        assert row["agent"] == agent and row["note"]
        assert not (row["volatile"] and row["signal"] == "none")


def test_real_state_db_enrollments_are_zero_or_listed():
    """실데이터 state DB: 행이 0이면 unknown, 있으면 configured. 어느 쪽도 '미사용'이 아니다."""
    from pathlib import Path
    from clfx.codex_sqlite import collect_sqlite_support
    codex = Path("~/.codex").expanduser()
    if not codex.is_dir():
        pytest.skip(f"실데이터 없음: {codex}")
    source = source_for(str(codex))
    support = collect_sqlite_support(source.sqlite_root, source.jsonl_files())
    row = enrollment_marker(support)
    assert row["signal"] in ("configured", "unknown")   # none 은 이 마커에서 불가능하다

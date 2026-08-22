"""13단계 — origin_channel: 원격(폰) 지시와 로컬 실행을 한 타임라인에서 가른다.

근거: Android SM-A235N 실측(관측 63건 · Claude Code 2.1.238 · Codex 0.149.0).
로컬 아티팩트만 다룬다 — 폰 단말 파싱은 이 저장소 범위 밖.

도메인은 `remote | local | unknown` 셋뿐이고, **판별 못 하면 unknown 이지 local 이 아니다.**
필드가 아예 없는 것과 unknown 은 다르다:
  - 필드 없음 = 판정 대상 레코드가 아니다(관측 부재)
  - unknown   = 봤는데 못 가렸다
어느 쪽도 local 을 뜻하지 않는다. 그걸 이 파일이 고정한다.
"""
import json
import sqlite3

import pytest

from clfx.codex_sqlite import augment_events, collect_sqlite_support
from clfx.parser import parse_file, parse_source
from clfx.sources import source_for

REMOTE_CLIENT = "codex_chatgpt_android_remote"
LOCAL_CLIENT = "codex-tui"
THREAD_REMOTE = "01a024ca-f712-7361-a240-19e61c9b81ba"
THREAD_LOCAL = "01a023c7-939e-7053-b4ba-de882ee45c3d"
THREAD_MIXED = "01a024c5-33ce-74f1-9dc1-d8a084a4980d"
THREAD_UNLOGGED = "01a02500-0000-7000-8000-000000000000"


# --------------------------------------------------------------- Claude
def _claude_root(tmp_path, rows, session="9153b51b-6fa0-499c-9c66-b483d89064aa"):
    root = tmp_path / ".claude"
    path = root / "projects" / "acme-demo" / f"{session}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")
    return root, path


def _prompt(text, session, prompt_source=None, origin=..., ts="2026-08-21T23:00:00Z"):
    row = {"type": "user", "sessionId": session, "timestamp": ts,
           "message": {"content": [{"type": "text", "text": text}]}}
    if prompt_source is not None:
        row["promptSource"] = prompt_source
    if origin is not ...:
        row["origin"] = origin
    return row


def _assistant_bash(session, command, ts="2026-08-21T23:00:05Z"):
    return {"type": "assistant", "sessionId": session, "timestamp": ts,
            "message": {"content": [{"type": "tool_use", "name": "Bash",
                                     "input": {"command": command}}]}}


SESSION = "9153b51b-6fa0-499c-9c66-b483d89064aa"


def test_claude_channel_rules(tmp_path):
    """queued ∧ human = remote, typed ∧ human = local. 나머지는 전부 unknown."""
    rows = [
        _prompt("폰에서 보냄", SESSION, "queued", {"kind": "human"}),
        _prompt("여기서 침", SESSION, "typed", {"kind": "human"}),
        _prompt("origin 없는 구버전 queued", SESSION, "queued"),
        _prompt("origin 없는 구버전 typed", SESSION, "typed"),
        _prompt("sdk 호출", SESSION, "sdk"),
        _prompt("시스템 주입", SESSION, "system", {"kind": "task-notification"}),
        _prompt("자동완성 수락", SESSION, "suggestion_accepted", {"kind": "human"}),
    ]
    root, _ = _claude_root(tmp_path, rows)
    events = [e for e in parse_source(source_for(str(root))) if e.action == "prompt"]

    assert [e.meta.get("origin_channel") for e in events] == [
        "remote", "local", "unknown", "unknown", "unknown", "unknown", "unknown"]


def test_claude_execution_events_carry_no_channel(tmp_path):
    """지시의 출처는 프롬프트 레코드에만 있다. 실행 Event 에 채널을 찍으면 추측이다."""
    rows = [_prompt("폰에서 보냄", SESSION, "queued", {"kind": "human"}),
            _assistant_bash(SESSION, "rm -rf /srv/acme-demo/cache")]
    root, _ = _claude_root(tmp_path, rows)
    events = list(parse_source(source_for(str(root))))

    prompt = next(e for e in events if e.action == "prompt")
    bash = next(e for e in events if e.action == "bash")
    assert prompt.meta["origin_channel"] == "remote"
    assert "origin_channel" not in bash.meta          # 없음 — local 이 아니다


def test_claude_bridge_session_joins_on_session_id_not_prefix(tmp_path):
    """같은 세션을 가리키는 ID 가 계층마다 접두사가 다르다(uuid vs `cse_…`).
    잇는 키는 레코드의 sessionId 다 — 접두사 문자열 비교로 이으면 다른 세션이 섞인다."""
    other = "ecada9f2-3071-4b8c-ab8b-8c03e1cf5672"
    rows = [
        {"type": "bridge-session", "sessionId": SESSION,
         "bridgeSessionId": "cse_01K8SpeHNF2716oLDtNLNUY3", "lastSequenceNum": 0},
        _prompt("폰에서 보냄", SESSION, "queued", {"kind": "human"}),
        _prompt("다른 세션 레코드", other, "typed", {"kind": "human"}),
    ]
    root, _ = _claude_root(tmp_path, rows)
    events = [e for e in parse_source(source_for(str(root))) if e.action == "prompt"]

    mine = next(e for e in events if e.session == SESSION)
    theirs = next(e for e in events if e.session == other)
    assert mine.meta["bridge_session_id"] == "cse_01K8SpeHNF2716oLDtNLNUY3"
    assert "bridge_session_id" not in theirs.meta     # 같은 파일에 있어도 세션이 다르면 안 붙는다


def test_claude_bridge_id_alone_is_not_a_remote_verdict(tmp_path):
    """브리지 세션이 열려 있다는 건 '원격으로 닿을 수 있다'까지다. 그 턴이 폰에서 왔다는 뜻이 아니다."""
    rows = [
        {"type": "bridge-session", "sessionId": SESSION,
         "bridgeSessionId": "cse_01K8SpeHNF2716oLDtNLNUY3"},
        _prompt("여기서 침", SESSION, "typed", {"kind": "human"}),
    ]
    root, _ = _claude_root(tmp_path, rows)
    event = next(e for e in parse_source(source_for(str(root))) if e.action == "prompt")

    assert event.meta["bridge_session_id"] == "cse_01K8SpeHNF2716oLDtNLNUY3"
    assert event.meta["origin_channel"] == "local"


def test_claude_entry_points_agree(tmp_path):
    """parse_source(CLI)와 parse_file(대시보드·위임)이 같은 meta 를 내야 한다.
    진입점마다 meta 가 다르면 같은 증거로 다른 보고서가 나온다."""
    rows = [
        {"type": "bridge-session", "sessionId": SESSION,
         "bridgeSessionId": "cse_01K8SpeHNF2716oLDtNLNUY3"},
        _prompt("폰에서 보냄", SESSION, "queued", {"kind": "human"}),
        _assistant_bash(SESSION, "ls"),
    ]
    root, path = _claude_root(tmp_path, rows)
    src = source_for(str(root))

    streamed = [e.to_dict() for e in parse_source(src)]
    per_file, _, _ = parse_file(source_for(str(root)), path, False)
    assert streamed == [e.to_dict() for e in per_file]


# --------------------------------------------------------------- Codex
def _log_span(connection_id, client_name, method="model/list", extra=""):
    """실측 tracing span 텍스트 형식 그대로."""
    return (f'app_server.request{{otel.kind="server" otel.name="{method}" '
            f'rpc.system="jsonrpc" rpc.method="{method}" rpc.transport="unix_socket" '
            f'app_server.connection_id={connection_id} app_server.api_version="v2" '
            f'app_server.client_name="{client_name}" app_server.client_version="dev"}}: {extra}')


def _codex_root(tmp_path, log_bodies, threads, enrollment=True):
    root = tmp_path / ".codex"
    sessions = root / "sessions" / "2026" / "08" / "21"
    sessions.mkdir(parents=True)
    for thread_id in threads:
        path = sessions / f"rollout-2026-08-21T23-47-56-{thread_id}.jsonl"
        rows = [
            {"timestamp": "2026-08-21T23:47:56Z", "type": "session_meta", "ordinal": 1,
             "payload": {"id": thread_id, "cli_version": "0.149.0",
                         "originator": "codex-tui"}},
            {"timestamp": "2026-08-21T23:48:00Z", "type": "event_msg", "ordinal": 2,
             "payload": {"type": "item_completed", "turn_id": "turn-1",
                         "thread_id": thread_id, "item": {
                             "type": "AgentMessage", "id": f"msg-{thread_id[:8]}",
                             "text": "synthetic"}}},
        ]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    logs = sqlite3.connect(root / "logs_2.sqlite")
    logs.execute("CREATE TABLE _sqlx_migrations(version INTEGER PRIMARY KEY)")
    logs.execute("INSERT INTO _sqlx_migrations VALUES (2)")
    logs.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL,"
                 " level TEXT, target TEXT, feedback_log_body TEXT)")
    for body in log_bodies:
        logs.execute("INSERT INTO logs(ts, level, target, feedback_log_body) VALUES (1,'INFO','t',?)",
                     (body,))
    logs.commit()
    logs.close()

    state = sqlite3.connect(root / "state_5.sqlite")
    state.execute("CREATE TABLE _sqlx_migrations(version INTEGER PRIMARY KEY)")
    state.execute("INSERT INTO _sqlx_migrations VALUES (46)")
    state.execute("CREATE TABLE threads(id TEXT PRIMARY KEY, rollout_path TEXT, cwd TEXT,"
                  " git_branch TEXT, git_sha TEXT, model TEXT, approval_mode TEXT,"
                  " sandbox_policy TEXT)")
    state.execute("""CREATE TABLE remote_control_enrollments (
                         websocket_url TEXT NOT NULL, account_id TEXT NOT NULL,
                         app_server_client_name TEXT NOT NULL, server_id TEXT NOT NULL,
                         environment_id TEXT NOT NULL, server_name TEXT NOT NULL,
                         updated_at INTEGER NOT NULL, remote_control_enabled INTEGER)""")
    if enrollment:
        state.execute("INSERT INTO remote_control_enrollments VALUES (?,?,?,?,?,?,?,?)", (
            "wss://chatgpt.com/backend-api/wham/remote/control/server", "acct-synthetic",
            "", "srv_e_synthetic", "env_e_synthetic", "Hwansktop", 1787322332, None))
    state.commit()
    state.close()
    return root


def _channels(root):
    src = source_for(str(root))
    events = list(parse_source(src))
    support = collect_sqlite_support(src.sqlite_root, src.jsonl_files())
    augment_events(events, support)
    return events, support


@pytest.fixture(scope="module")
def codex_case(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("codex-origin")
    bodies = []
    # connection 0: codex-tui 의 plugin/list 노이즈를 잔뜩 — 최근 표본만 보면 이게 다수다.
    bodies += [_log_span(0, LOCAL_CLIENT, "plugin/list") for _ in range(40)]
    bodies += [_log_span(0, LOCAL_CLIENT, "config/read") for _ in range(20)]
    # connection 4: 폰. 소수지만 연결 단위로 묶으면 노이즈에 안 묻힌다.
    bodies += [_log_span(4, REMOTE_CLIENT, "thread/resume") for _ in range(3)]
    bodies.append(_log_span(4, REMOTE_CLIENT, "thread/resume",
                            f"resumed thread_id={THREAD_REMOTE}"))
    bodies.append("app-server request: turn/start connection_id=ConnectionId(4) request_id=Integer(106)")
    # connection 5: 로컬 TUI 가 몬 스레드
    bodies.append(_log_span(5, LOCAL_CLIENT, "turn/start", f"thread_id={THREAD_LOCAL}"))
    bodies.append("app-server request: turn/start connection_id=ConnectionId(5) request_id=Integer(5)")
    # 양쪽에서 다 보이는 스레드 — 로컬에서 시작해 폰에서 resume 한 실측 케이스
    bodies.append(_log_span(5, LOCAL_CLIENT, "turn/start", f"thread_id={THREAD_MIXED}"))
    bodies.append(_log_span(4, REMOTE_CLIENT, "thread/resume", f"thread_id={THREAD_MIXED}"))

    root = _codex_root(tmp_path, bodies,
                       [THREAD_REMOTE, THREAD_LOCAL, THREAD_MIXED, THREAD_UNLOGGED])
    return _channels(root)


def test_codex_connection_join_survives_tui_noise(codex_case):
    """panel0 주의 #1: 최근 RPC 표본만 보면 codex-tui plugin/list 60행에 원격 4행이 묻힌다.
    연결(connection_id) 단위로 묶으면 안 묻힌다."""
    _, support = codex_case
    connections = support["remote_channel"]["connections"]

    assert connections["0"]["channel"] == "local"
    assert connections["4"] == {"client_names": [REMOTE_CLIENT], "channel": "remote",
                                "os": "android", "started_turns": True}
    assert support["remote_channel"]["turn_connections"] == ["4", "5"]


def test_codex_thread_channels(codex_case):
    _, support = codex_case
    threads = support["remote_channel"]["threads"]

    assert threads[THREAD_REMOTE]["channel"] == "remote"
    assert threads[THREAD_LOCAL]["channel"] == "local"
    assert threads[THREAD_MIXED]["channel"] == "unknown"          # 양쪽 관측 → 턴 단위로 못 가린다
    assert threads[THREAD_MIXED]["seen"] == ["local", "remote"]   # unknown 인 이유는 남긴다
    assert THREAD_UNLOGGED not in threads                         # 로그에 없으면 항목 자체가 없다


def test_codex_events_get_channel_and_absence_is_not_local(codex_case):
    events, _ = codex_case
    by_thread = {e.meta.get("thread_id"): e for e in events if e.meta.get("thread_id")}

    assert by_thread[THREAD_REMOTE].meta["origin_channel"] == "remote"
    assert by_thread[THREAD_LOCAL].meta["origin_channel"] == "local"
    assert by_thread[THREAD_MIXED].meta["origin_channel"] == "unknown"
    assert by_thread[THREAD_MIXED].meta["origin_channels_seen"] == ["local", "remote"]
    # 로그에 안 보이는 스레드는 필드가 아예 없다 — local 로 떨어뜨리지 않는다
    assert "origin_channel" not in by_thread[THREAD_UNLOGGED].meta


def test_codex_enrollment_attaches_only_where_remote_was_observed(codex_case):
    """등록 행은 '어느 환경에 등록됐나'까지만 말한다(VR-023: 행이 있어도 채널은 죽어 있을 수 있음).
    그래서 원격이 관측된 스레드에만 붙인다."""
    events, support = codex_case
    by_thread = {e.meta.get("thread_id"): e for e in events if e.meta.get("thread_id")}

    assert support["remote_control_enrollments"][0]["environment_id"] == "env_e_synthetic"
    assert by_thread[THREAD_REMOTE].meta["environment_id"] == "env_e_synthetic"
    assert by_thread[THREAD_REMOTE].meta["server_name"] == "Hwansktop"
    assert "environment_id" not in by_thread[THREAD_LOCAL].meta
    assert "environment_id" not in by_thread[THREAD_UNLOGGED].meta
    # 양쪽 관측이면 채널은 unknown 이지만 원격 관여 자체는 사실이므로 환경은 남긴다
    assert by_thread[THREAD_MIXED].meta["environment_id"] == "env_e_synthetic"


def test_codex_without_logs_yields_no_channel(tmp_path):
    """logs_2 가 없으면 아무 스레드도 판별되지 않는다 — 조용히 local 이 되면 안 된다."""
    root = _codex_root(tmp_path, [], [THREAD_LOCAL], enrollment=False)
    (root / "logs_2.sqlite").unlink()
    events, support = _channels(root)

    assert support["remote_channel"]["threads"] == {}
    assert all("origin_channel" not in e.meta for e in events)


def test_no_local_verdict_without_positive_evidence(codex_case, tmp_path):
    """이 단계 전체의 불변식: local 은 근거가 있을 때만 나온다."""
    codex_events, _ = codex_case
    rows = [_prompt("origin 없는 구버전 queued", SESSION, "queued"),
            _prompt("sdk", SESSION, "sdk")]
    root, _ = _claude_root(tmp_path, rows)
    claude_events = list(parse_source(source_for(str(root))))

    for event in claude_events:
        assert event.meta.get("origin_channel") != "local"
    locals_ = [e for e in codex_events if e.meta.get("origin_channel") == "local"]
    assert {e.meta["thread_id"] for e in locals_} == {THREAD_LOCAL}


# ------------------------------------------------------- origin_os (Codex 전용)
# client_name 문자열에 조작 단말의 OS 가 박혀 있다. 로컬 로그만으로 "폰에서 지시했다"를
# 넘어 "어느 OS 단말에서 지시했다"까지 간다 — Claude 에는 없는 축이다.
IOS_CLIENT = "codex_chatgpt_ios_remote"
UNKNOWN_REMOTE_CLIENT = "codex_chatgpt_watchos_remote"      # 아직 없는 플랫폼(가상)
THREAD_IOS = "01a02601-0000-7000-8000-000000000001"
THREAD_TWO_DEVICE = "01a02601-0000-7000-8000-000000000002"
THREAD_ODD_REMOTE = "01a02601-0000-7000-8000-000000000003"


@pytest.fixture(scope="module")
def codex_os_case(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("codex-origin-os")
    bodies = [
        _log_span(7, IOS_CLIENT, "thread/resume", f"thread_id={THREAD_IOS}"),
        _log_span(5, LOCAL_CLIENT, "turn/start", f"thread_id={THREAD_LOCAL}"),
        # 같은 스레드를 아이폰과 갤럭시에서 각각 이어받은 경우
        _log_span(7, IOS_CLIENT, "thread/resume", f"thread_id={THREAD_TWO_DEVICE}"),
        _log_span(4, REMOTE_CLIENT, "thread/resume", f"thread_id={THREAD_TWO_DEVICE}"),
        # 원격은 맞는데 접미가 낯선 클라이언트
        _log_span(9, UNKNOWN_REMOTE_CLIENT, "thread/resume", f"thread_id={THREAD_ODD_REMOTE}"),
    ]
    root = _codex_root(tmp_path, bodies,
                       [THREAD_IOS, THREAD_LOCAL, THREAD_TWO_DEVICE, THREAD_ODD_REMOTE])
    return _channels(root)


def _meta_by_thread(events):
    return {event.meta.get("thread_id") or str(event.session): event.meta for event in events}


def test_codex_client_name_names_the_operator_os(codex_os_case):
    """logs_2 의 client_name 하나로 조작 단말 OS 까지 특정된다."""
    _, support = codex_os_case
    connections = support["remote_channel"]["connections"]

    assert connections["7"]["os"] == "ios"
    assert connections["4"]["os"] == "android"


def test_local_client_claims_no_os(codex_os_case):
    """`codex-tui` 는 '로컬'을 말할 뿐 OS 를 말하지 않는다.

    locality 는 origin_channel 이 이미 담는다. 여기서 겹쳐 실으면 두 축이 서로를 오염시킨다."""
    events, support = codex_os_case
    assert support["remote_channel"]["connections"]["5"]["os"] is None

    local = _meta_by_thread(events)[THREAD_LOCAL]
    assert local["origin_channel"] == "local"
    assert "origin_os" not in local


def test_remote_thread_carries_origin_os(codex_os_case):
    events, _ = codex_os_case
    remote = _meta_by_thread(events)[THREAD_IOS]

    assert remote["origin_channel"] == "remote"
    assert remote["origin_os"] == "ios"


def test_two_devices_on_one_thread_is_unknown_with_evidence(codex_os_case):
    """아이폰과 갤럭시가 같은 스레드를 이어받으면 어느 턴이 어느 단말인지 단정할 수 없다.

    그래도 관측 자체는 버리지 않는다 — unknown 의 근거를 사후에 감사해야 한다."""
    events, _ = codex_os_case
    both = _meta_by_thread(events)[THREAD_TWO_DEVICE]

    assert both["origin_channel"] == "remote"      # 채널은 확정된다 — 둘 다 원격이니까
    assert both["origin_os"] == "unknown"
    assert both["origin_os_seen"] == ["android", "ios"]


def test_unrecognized_remote_client_is_unknown_not_local(codex_os_case):
    """새 플랫폼이 나와 접미가 낯설어도 조용히 로컬로 떨어지면 안 된다.

    actor 가 unknown 을 user 로 흘리지 않는 것과 같은 규칙이다."""
    events, support = codex_os_case
    assert support["remote_channel"]["connections"]["9"]["os"] == "unknown"

    odd = _meta_by_thread(events)[THREAD_ODD_REMOTE]
    assert odd["origin_channel"] == "remote"
    assert odd["origin_os"] == "unknown"
    assert "origin_os_seen" not in odd             # 관측이 하나뿐이면 근거 목록은 안 단다


def test_mixed_channel_thread_does_not_assert_a_device(codex_case):
    """채널이 unknown 인 이벤트에 OS 를 단정하면 없는 사실을 만든다.

    로컬 TUI 로 시작해 폰에서 resume 한 스레드가 실측에 있다. 그 스레드의 이벤트는
    로컬 턴일 수도 있어서 "안드로이드에서 왔다"고 말할 수 없다. 관측은 candidates 로 남긴다.
    실데이터에서 이 경로로 16건이 잘못 단정될 뻔했다(2026-08-22)."""
    events, _ = codex_case
    mixed = _meta_by_thread(events)[THREAD_MIXED]

    assert mixed["origin_channel"] == "unknown"
    assert "origin_os" not in mixed
    assert mixed["origin_os_candidates"] == ["android"]

import json

from clfx.parser import parse_file
from clfx.sources import CodexSource


def _parse_rows(tmp_path, rows, name="actor"):
    root = tmp_path / ".codex"
    path = root / "sessions" / "2026" / "08" / "21" / f"rollout-{name}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    src = CodexSource(root)
    events, _, _ = parse_file(src, path, False)
    return events


def _meta(session="synthetic-actor", **extra):
    payload = {"id": session, "cli_version": "0.147.0", "originator": "codex-tui"}
    payload.update(extra)
    return {"timestamp": "2026-08-21T05:00:00Z", "type": "session_meta",
            "ordinal": 1, "payload": payload}


def _turn(turn_id, approval="on-request", sandbox="workspace-write", reviewer="user"):
    return {"timestamp": "2026-08-21T05:00:01Z", "type": "turn_context",
            "payload": {"turn_id": turn_id, "approval_policy": approval,
                        "sandbox_policy": {"type": sandbox},
                        "approvals_reviewer": reviewer}}


def _command(number, item_id, command, source, turn_id, exit_code=0, status="completed"):
    return {"timestamp": f"2026-08-21T05:00:{number:02d}Z", "type": "event_msg",
            "ordinal": number, "payload": {"type": "item_completed",
            "turn_id": turn_id, "thread_id": "thread-main",
            "item": {"type": "CommandExecution", "id": item_id,
                     "command": ["/bin/bash", "-lc", command], "cwd": "file:///case",
                     "source": source, "status": status,
                     "aggregated_output": "synthetic output", "exit_code": exit_code}}}


def test_command_actor_uses_user_shell_then_model_link_else_unknown(tmp_path):
    rows = [
        _meta(),
        _turn("turn-actor"),
        {"timestamp": "2026-08-21T05:00:02Z", "type": "response_item", "ordinal": 2,
         "payload": {"type": "function_call", "name": "exec_command",
                     "arguments": json.dumps({"cmd": "printf agent"}),
                     "call_id": "command-agent",
                     "internal_chat_message_metadata_passthrough": {"turn_id": "turn-actor"}}},
        _command(3, "command-agent", "printf agent", "unified_exec_startup", "turn-actor"),
        _command(4, "command-user", "printf user", "user_shell", "turn-actor"),
        _command(5, "command-unknown", "printf unknown", "unified_exec_startup", "turn-actor"),
    ]

    commands = [event for event in _parse_rows(tmp_path, rows) if event.action == "bash"]

    assert [(event.meta["id"], event.actor) for event in commands] == [
        ("command-agent", "agent"), ("command-user", "user"),
        ("command-unknown", "unknown")]
    for event in commands:
        assert event.meta["turn_id"] == "turn-actor"
        assert event.meta["thread_id"] == "thread-main"
        assert event.meta["approval_policy"] == "on-request"
        assert event.meta["sandbox_policy"] == {"type": "workspace-write"}
        assert event.meta["approvals_reviewer"] == "user"
        assert "approved_by_user" not in event.meta


def test_turn_policy_is_scoped_by_turn_id(tmp_path):
    rows = [
        _meta("synthetic-turns"),
        _turn("turn-a", "on-request", "workspace-write", "user"),
        _command(2, "command-a", "pwd", "user_shell", "turn-a"),
        _turn("turn-b", "never", "read-only", "policy"),
        _command(3, "command-b", "pwd", "user_shell", "turn-b"),
    ]

    events = [event for event in _parse_rows(tmp_path, rows, "turns")
              if event.action == "bash"]

    assert [(event.meta["turn_id"], event.meta["approval_policy"],
             event.meta["sandbox_policy"], event.meta["approvals_reviewer"])
            for event in events] == [
        ("turn-a", "on-request", {"type": "workspace-write"}, "user"),
        ("turn-b", "never", {"type": "read-only"}, "policy"),
    ]


def test_subagent_session_meta_is_attached_without_new_actor_value(tmp_path):
    rows = [
        _meta("synthetic-subagent", thread_source="subagent",
              parent_thread_id="parent-top", agent_nickname="synthetic-nickname",
              source={"subagent": {"thread_spawn": {
                  "parent_thread_id": "parent-nested", "depth": 1,
                  "agent_path": "synthetic/path", "agent_nickname": "nested-nickname"}}}),
        _turn("turn-subagent"),
        {"timestamp": "2026-08-21T05:10:02Z", "type": "event_msg", "ordinal": 2,
         "payload": {"type": "item_completed", "turn_id": "turn-subagent",
                     "thread_id": "thread-child", "item": {
                         "type": "AgentMessage", "id": "agent-message",
                         "text": "subagent response"}}},
        {"timestamp": "2026-08-21T05:10:03Z", "type": "event_msg", "ordinal": 3,
         "payload": {"type": "item_completed", "turn_id": "turn-subagent",
                     "thread_id": "thread-child", "item": {
                         "type": "UserMessage", "id": "parent-message",
                         "content": [{"type": "text", "text": "delegated input"}]}}},
        _command(4, "subagent-command", "pwd", "unified_exec_startup", "turn-subagent"),
    ]

    events = _parse_rows(tmp_path, rows, "subagent")
    event = events[0]

    assert {item.actor for item in events} == {"agent"}
    assert event.meta["agent_kind"] == "subagent"
    assert event.meta["parent_thread_id"] == "parent-nested"
    assert event.meta["depth"] == 1
    assert event.meta["agent_path"] == "synthetic/path"
    assert event.meta["agent_nickname"] == "nested-nickname"
    assert all(item.actor != "subagent" for item in events)


def test_transcript_only_write_confidence_never_claims_high(tmp_path):
    rows = [
        _meta("synthetic-confidence"),
        _turn("turn-file"),
        {"timestamp": "2026-08-21T05:20:02Z", "type": "event_msg", "ordinal": 2,
         "payload": {"type": "item_completed", "turn_id": "turn-file",
                     "thread_id": "thread-main", "item": {
                         "type": "FileChange", "id": "file-change", "status": "completed",
                         "changes": {"/case/item.txt": {"type": "add", "content": "x"}}}}},
        _turn("turn-command"),
        _command(3, "command-write", "printf x > /case/shell.txt",
                 "unified_exec_startup", "turn-command", exit_code=0),
        _turn("turn-low"),
        _command(4, "command-low", "cat /case/maybe.txt",
                 "unified_exec_startup", "turn-low", exit_code=1, status="failed"),
        _turn("turn-unknown"),
        _command(5, "command-unknown", "pwd",
                 "unified_exec_startup", "turn-unknown", exit_code=0),
        _turn("turn-patch-end"),
        {"timestamp": "2026-08-21T05:20:06Z", "type": "event_msg",
         "payload": {"type": "patch_apply_end", "call_id": "patch-end-ok",
                     "status": "completed", "changes": {
                         "/case/end.txt": {"type": "add", "content": "x"}}}},
        _turn("turn-patch-failed"),
        {"timestamp": "2026-08-21T05:20:07Z", "type": "event_msg",
         "payload": {"type": "patch_apply_end", "call_id": "patch-end-failed",
                     "status": "failed", "changes": {
                         "/case/failed.txt": {"type": "add", "content": "x"}}}},
        _turn("turn-patch-empty"),
        {"timestamp": "2026-08-21T05:20:08Z", "type": "response_item",
         "payload": {"type": "custom_tool_call", "call_id": "patch-empty",
                     "name": "apply_patch", "status": "completed",
                     "input": "*** Begin Patch\n*** End Patch"}},
    ]

    events = _parse_rows(tmp_path, rows, "confidence")
    by_id = {event.meta["id"]: event for event in events}

    assert by_id["file-change"].meta["confidence"] == "medium"
    assert by_id["command-write"].meta["confidence"] == "low"
    assert by_id["command-write"].meta["write_target"] == "/case/shell.txt"
    assert by_id["command-low"].meta["confidence"] == "low"
    assert "confidence" not in by_id["command-unknown"].meta
    assert by_id["patch-end-ok"].meta["record_type"] == "patch_apply_end"
    assert by_id["patch-end-ok"].meta["confidence"] == "medium"
    assert by_id["patch-end-failed"].meta["record_type"] == "patch_apply_end"
    assert by_id["patch-end-failed"].meta["confidence"] == "low"
    assert by_id["patch-empty"].meta["record_type"] == "apply_patch"
    assert by_id["patch-empty"].meta["confidence"] == "low"
    assert all(event.meta.get("confidence") != "high" for event in events)


def test_image_view_keeps_read_action_and_image_media(tmp_path):
    rows = [
        _meta("synthetic-image"),
        _turn("turn-image"),
        {"timestamp": "2026-08-21T05:30:02Z", "type": "event_msg", "ordinal": 2,
         "payload": {"type": "item_completed", "turn_id": "turn-image",
                     "thread_id": "thread-main", "item": {
                         "type": "ImageView", "id": "image-view", "path": "/case/image.png"}}},
    ]

    event = _parse_rows(tmp_path, rows, "image")[0]

    assert event.action == "read" and event.actor == "agent"
    assert event.meta["media"] == "image"

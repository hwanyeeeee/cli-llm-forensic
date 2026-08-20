import json
from pathlib import Path

import pytest

from clfx.event import Event
from clfx.parser import parse_file, parse_source
from clfx.sources import CodexSource, source_warnings


FIXTURES = Path(__file__).parent / "fixtures"


def _parse_fixture(name):
    src = CodexSource(FIXTURES / name)
    path = src.jsonl_files()[0]
    events, bypass, sha = parse_file(src, path, False)
    assert bypass == set()
    assert sha and len(sha) == 64
    return src, path, events


def test_legacy_rollout_pairs_calls_and_preserves_unmatched_status():
    src, path, events = _parse_fixture("codex-legacy")
    actions = [event.action for event in events]
    assert actions == ["prompt", "paste", "bash", "bash", "bash", "write",
                       "response", "mcp", "search"]
    assert all(event.agent == "codex" and event.session == "synthetic-legacy"
               for event in events)
    assert all("duplicate model input" not in event.preview for event in events)

    completed = next(event for event in events if event.meta.get("id") == "call-1")
    assert completed.target == "printf synthetic"
    assert completed.preview == "synthetic output"
    assert completed.meta["status"] == "completed"
    assert completed.meta["exit_code"] == 0
    unmatched = next(event for event in events if event.meta.get("id") == "call-missing")
    assert unmatched.meta["status"] == "unknown"
    custom_exec = next(event for event in events if event.meta.get("id") == "custom-exec")
    assert custom_exec.meta["function_name"] == "exec"
    assert custom_exec.meta["record_type"] == "orchestration"
    patch = next(event for event in events if event.meta.get("id") == "custom-patch")
    assert patch.target == "/case/new.txt"
    assert "*** Add File: /case/new.txt" in patch.preview
    assert patch.meta["output"] == "Done"
    mcp = next(event for event in events if event.action == "mcp")
    assert mcp.target == "mcp__synthetic__lookup"
    assert "fixture" in mcp.preview

    warning = next(w for w in source_warnings(src)
                   if w["kind"] == "unsupported_schema" and w["name"] == "future_event")
    assert warning == {"kind": "unsupported_schema", "file": str(path), "line": 16,
                       "layer": "event_msg", "name": "future_event",
                       "keyset": ["mystery", "type"], "count": 2}


def test_item_rollout_parses_all_pascal_types_and_merges_duplicate_view():
    src, path, events = _parse_fixture("codex-item")
    assert [event.action for event in events] == [
        "bash", "prompt", "paste", "response", "write", "write", "search",
        "spawn", "spawn", "read",
    ]
    assert sum(event.action == "bash" for event in events) == 1
    assert len(src.orchestration_records) == 1
    assert src.orchestration_records[0]["id"] == "custom-item-exec"
    assert all("duplicate item model input" not in event.preview for event in events)

    command = next(event for event in events if event.meta.get("id") == "cmd-1")
    assert command.target.endswith("printf synthetic'")
    assert command.meta == {"id": "cmd-1", "status": "completed", "ordinal": 7,
                            "cwd": "/case/synthetic dir", "exit_code": 0,
                            "function_name": "exec_command",
                            "record_type": "command_execution",
                            "command_text": "printf synthetic", "confidence": "unknown"}
    assert command.preview == "synthetic output"
    assert {event.target for event in events if event.action == "write"} == {
        "/case/new.txt", "/case/old.txt"}
    assert any(event.action == "paste" and event.target == "/case/input image.png"
               for event in events)
    assert [event.preview for event in events if event.action == "prompt"] == ["inspect"]
    assert any(event.action == "search" and event.target == "item synthetic query"
               for event in events)
    assert any(event.action == "spawn" and event.target == "synthetic-agent"
               for event in events)

    warnings = [w for w in source_warnings(src) if w["kind"] == "unsupported_schema"]
    assert {(w["layer"], w["name"]) for w in warnings} == {
        ("extension.kind", "future.extension"),
        ("item", "FutureItem"),
        ("envelope", "future_envelope"),
    }
    assert all(w["file"] == str(path) and w["line"] > 0 and w["keyset"]
               and w["count"] == 1 for w in warnings)


def test_cli_version_mismatch_warns_but_does_not_gate_item_event(tmp_path):
    root = tmp_path / ".codex"
    path = root / "sessions" / "2026" / "08" / "21" / "rollout-mismatch.jsonl"
    path.parent.mkdir(parents=True)
    rows = [
        {"timestamp": "2026-08-21T02:00:00Z", "type": "session_meta", "ordinal": 1,
         "payload": {"id": "synthetic-mismatch", "cli_version": "0.146.0",
                     "originator": "codex-tui"}},
        {"timestamp": "2026-08-21T02:00:01Z", "type": "event_msg", "ordinal": 2,
         "payload": {"type": "item_completed", "item": {
             "type": "AgentMessage", "id": "agent-mismatch", "text": "still parsed"}}},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    src = CodexSource(root)

    events, _, _ = parse_file(src, path, False)

    assert [(event.action, event.preview) for event in events] == [("response", "still parsed")]
    mismatch = [w for w in source_warnings(src) if w["kind"] == "capability_mismatch"]
    assert mismatch == [{"kind": "capability_mismatch", "file": str(path), "line": 1,
                         "cli_version": "0.146.0", "expected": "legacy",
                         "capabilities": ["item", "ordinal"],
                         "originator": "codex-tui"}]


@pytest.mark.parametrize("originator", ["codex_exec", "codex_exec_automation"])
def test_codex_exec_originator_accepts_legacy_at_0147(tmp_path, originator):
    root = tmp_path / ".codex"
    path = root / "sessions" / "2026" / "08" / "21" / f"rollout-{originator}.jsonl"
    path.parent.mkdir(parents=True)
    rows = [
        {"timestamp": "2026-08-21T02:10:00Z", "type": "session_meta",
         "payload": {"id": f"synthetic-{originator}", "cli_version": "0.147.0",
                     "originator": originator}},
        {"timestamp": "2026-08-21T02:10:01Z", "type": "event_msg",
         "payload": {"type": "user_message", "message": "headless synthetic"}},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    src = CodexSource(root)

    events, _, _ = parse_file(src, path, False)

    assert [(event.action, event.preview) for event in events] == [
        ("prompt", "headless synthetic")]
    assert not [warning for warning in source_warnings(src)
                if warning["kind"] == "capability_mismatch"]


def test_known_event_lifecycle_is_quiet_and_subagent_activity_emits_spawn(tmp_path):
    root = tmp_path / ".codex"
    path = root / "sessions" / "2026" / "08" / "21" / "rollout-events.jsonl"
    path.parent.mkdir(parents=True)
    rows = [
        {"timestamp": "2026-08-21T02:20:00Z", "type": "session_meta",
         "payload": {"id": "synthetic-events", "cli_version": "0.146.0"}},
        *({"timestamp": "2026-08-21T02:20:01Z", "type": "event_msg",
           "payload": {"type": kind, "value": "synthetic"}}
          for kind in ("task_complete", "thread_settings_applied", "turn_aborted",
                       "context_compacted")),
        {"timestamp": "2026-08-21T02:20:02Z", "type": "event_msg",
         "payload": {"type": "sub_agent_activity", "event_id": "event-1",
                     "agent_thread_id": "thread-child", "agent_path": "synthetic-agent",
                     "kind": "started", "occurred_at_ms": 1770000000000}},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    src = CodexSource(root)

    events, _, _ = parse_file(src, path, False)

    assert [(event.action, event.target, event.preview) for event in events] == [
        ("spawn", "thread-child", "started")]
    assert events[0].meta["event_id"] == "event-1"
    assert events[0].meta["occurred_at_ms"] == 1770000000000
    assert not [warning for warning in source_warnings(src)
                if warning["kind"] == "unsupported_schema"]


def test_event_meta_is_optional_and_roundtrips():
    _, _, events = _parse_fixture("codex-item")
    event = next(event for event in events if event.meta)
    assert Event.from_dict(event.to_dict()) == event
    assert "meta" in event.to_dict()
    plain = Event("t", "codex", "s", "agent", "response", "", "x", event.source)
    assert "meta" not in plain.to_dict()


def test_item_capability_links_ctc_exec_without_second_bash_event(tmp_path):
    root = tmp_path / ".codex"
    path = root / "sessions" / "2026" / "08" / "21" / "rollout-orchestration.jsonl"
    path.parent.mkdir(parents=True)
    rows = [
        {"timestamp": "2026-08-21T03:00:00Z", "type": "session_meta", "ordinal": 1,
         "payload": {"id": "synthetic-orchestration", "cli_version": "0.147.0"}},
        {"timestamp": "2026-08-21T03:00:01Z", "type": "response_item", "ordinal": 2,
         "payload": {"type": "custom_tool_call", "id": "ctc-view",
                     "call_id": "orchestration-1", "name": "exec",
                     "input": "await tools.exec_command({cmd: 'printf child'})"}},
        {"timestamp": "2026-08-21T03:00:02Z", "type": "event_msg", "ordinal": 3,
         "payload": {"type": "item_completed", "item": {
             "type": "CommandExecution", "id": "command-1",
             "command": ["/bin/bash", "-lc", "printf child"], "cwd": "file:///case",
             "status": "completed", "aggregated_output": "child", "exit_code": 0}}},
        {"timestamp": "2026-08-21T03:00:03Z", "type": "response_item", "ordinal": 4,
         "payload": {"type": "custom_tool_call_output", "id": "ctc-output-view",
                     "call_id": "orchestration-1",
                     "output": [{"type": "output_text", "text": "orchestration done"}]}},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    src = CodexSource(root)

    events, _, _ = parse_file(src, path, False)

    assert [event.action for event in events] == ["bash"]
    command = events[0]
    assert command.meta["id"] == "command-1"
    orchestration = command.meta["orchestration"]
    assert orchestration["id"] == "orchestration-1"
    assert orchestration["source"] == {"file": str(path), "line": 2}
    assert orchestration["children"] == ["command-1"]
    assert orchestration["status"] == "completed"
    assert orchestration["output"] == "orchestration done"
    assert src.orchestration_records == [orchestration]


def test_known_function_calls_map_to_events_or_known_no_event(tmp_path):
    root = tmp_path / ".codex"
    path = root / "sessions" / "2026" / "08" / "21" / "rollout-functions.jsonl"
    path.parent.mkdir(parents=True)
    event_args = {
        "write_stdin": {"session_id": 7, "chars": "synthetic stdin"},
        "view_image": {"path": "/case/image.png"},
        "spawn_agent": {"message": "synthetic task"},
        "send_message": {"agent_id": "agent-1", "message": "synthetic message"},
        "wait_agent": {"targets": ["agent-1"]},
        "close_agent": {"target": "agent-1"},
        "interrupt_agent": {"target": "agent-1"},
        "list_agents": {},
        "followup_task": {"target": "agent-1"},
        "list_mcp_resources": {"server": "synthetic"},
    }
    no_event = ["wait", "update_plan", "create_goal", "update_goal", "get_goal",
                "smart_unfold", "smart_search", "smart_outline"]
    rows = [{"timestamp": "2026-08-21T04:00:00Z", "type": "session_meta",
             "payload": {"id": "synthetic-functions", "cli_version": "0.146.0"}}]
    for number, (name, arguments) in enumerate(event_args.items(), start=1):
        rows.append({"timestamp": f"2026-08-21T04:00:{number:02d}Z", "type": "response_item",
                     "payload": {"type": "function_call", "name": name,
                                 "arguments": json.dumps(arguments),
                                 "call_id": f"event-{number}"}})
    for number, name in enumerate(no_event, start=20):
        rows.append({"timestamp": f"2026-08-21T04:00:{number:02d}Z", "type": "response_item",
                     "payload": {"type": "function_call", "name": name,
                                 "arguments": "{}", "call_id": f"known-{number}"}})
    rows.append({"timestamp": "2026-08-21T04:00:40Z", "type": "response_item",
                 "payload": {"type": "function_call", "name": "future_tool",
                             "arguments": "{}", "call_id": "unknown-1"}})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    src = CodexSource(root)

    events, _, _ = parse_file(src, path, False)

    assert [event.action for event in events] == [
        "bash", "read", "spawn", "spawn", "spawn", "spawn", "spawn", "spawn",
        "spawn", "mcp"]
    stdin = events[0]
    assert stdin.target == "session:7" and stdin.preview == "synthetic stdin"
    assert stdin.meta["function_name"] == "write_stdin"
    image = events[1]
    assert image.target == "/case/image.png" and image.meta["media"] == "image"
    warnings = [warning for warning in source_warnings(src)
                if warning["kind"] == "unsupported_schema"]
    assert [(warning["layer"], warning["name"]) for warning in warnings] == [
        ("function_call.name", "future_tool")]


def test_parse_source_isolates_call_ids_and_sessions_per_rollout(tmp_path):
    root = tmp_path / ".codex"
    for day, session, command in (("20", "session-a", "printf a"),
                                  ("21", "session-b", "printf b")):
        path = root / "sessions" / "2026" / "08" / day / f"rollout-{session}.jsonl"
        path.parent.mkdir(parents=True)
        rows = [
            {"timestamp": f"2026-08-{day}T00:00:00Z", "type": "session_meta",
             "payload": {"id": session, "cli_version": "0.146.0"}},
            {"timestamp": f"2026-08-{day}T00:00:01Z", "type": "response_item",
             "payload": {"type": "function_call", "name": "exec_command",
                         "arguments": json.dumps({"cmd": command}), "call_id": "same-call"}},
            {"timestamp": f"2026-08-{day}T00:00:02Z", "type": "response_item",
             "payload": {"type": "function_call_output", "call_id": "same-call",
                         "output": command}},
        ]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    events = list(parse_source(CodexSource(root)))

    assert [(event.session, event.target) for event in events] == [
        ("session-a", "printf a"), ("session-b", "printf b")]

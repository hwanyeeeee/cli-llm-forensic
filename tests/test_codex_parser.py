import json
from pathlib import Path

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
        "spawn", "spawn", "read", "bash",
    ]
    assert sum(event.action == "bash" for event in events) == 2
    assert all("duplicate item model input" not in event.preview for event in events)

    command = next(event for event in events if event.meta.get("id") == "cmd-1")
    assert command.target.endswith("printf synthetic'")
    assert command.meta == {"id": "cmd-1", "status": "completed", "ordinal": 7,
                            "cwd": "/case/synthetic dir", "exit_code": 0}
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
         "payload": {"id": "synthetic-mismatch", "cli_version": "0.146.0"}},
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
                         "capabilities": ["item", "ordinal"]}]


def test_event_meta_is_optional_and_roundtrips():
    _, _, events = _parse_fixture("codex-item")
    event = next(event for event in events if event.meta)
    assert Event.from_dict(event.to_dict()) == event
    assert "meta" in event.to_dict()
    plain = Event("t", "codex", "s", "agent", "response", "", "x", event.source)
    assert "meta" not in plain.to_dict()


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

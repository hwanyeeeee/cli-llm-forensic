from pathlib import Path

from clfx.parser import parse_file
from clfx.sources import CodexSource, source_warnings


FIXTURES = Path(__file__).parent / "fixtures"


def _records_and_events(name):
    source = CodexSource(FIXTURES / name)
    path = source.jsonl_files()[0]
    records = list(source._iter_jsonl(path))
    events, _, _ = parse_file(source, path, False)
    return source, records, events


def test_item_tui_capability_golden():
    source, records, events = _records_and_events("codex-item")
    assert all("ordinal" in record.obj for record in records)
    item_types = {record.obj["payload"]["item"]["type"] for record in records
                  if record.obj.get("type") == "event_msg"
                  and record.obj.get("payload", {}).get("type") == "item_completed"}
    assert {"CommandExecution", "FileChange", "UserMessage", "AgentMessage",
            "Extension", "SubAgentActivity", "CollabAgentToolCall", "ImageView"} <= item_types
    assert {event.action for event in events} >= {"prompt", "bash", "write", "search", "spawn"}
    assert not source_warnings(source)


def test_legacy_capability_golden():
    source, records, events = _records_and_events("codex-legacy")
    assert not any("ordinal" in record.obj for record in records)
    event_kinds = {record.obj.get("payload", {}).get("type") for record in records
                   if record.obj.get("type") == "event_msg"}
    response_kinds = {record.obj.get("payload", {}).get("type") for record in records
                      if record.obj.get("type") == "response_item"}
    assert {"user_message", "agent_message"} <= event_kinds
    assert {"function_call", "function_call_output", "custom_tool_call"} <= response_kinds
    assert {event.action for event in events} >= {"prompt", "response", "bash", "write"}
    assert not source_warnings(source)


def test_codex_exec_0147_legacy_capability_golden():
    source, records, events = _records_and_events("codex-exec")
    session = records[0].obj["payload"]
    assert session["cli_version"] == "0.147.0" and session["originator"] == "codex_exec"
    assert [event.action for event in events] == ["prompt", "response", "bash", "bash"]
    assert not [warning for warning in source_warnings(source)
                if warning["kind"] == "capability_mismatch"]


def test_unknown_structure_capability_golden():
    source, _records, events = _records_and_events("codex-unknown")
    assert events == []
    warnings = source_warnings(source)
    assert warnings == [{
        "kind": "unsupported_schema", "file": str(source.jsonl_files()[0]), "line": 2,
        "layer": "event_msg", "name": "future_event",
        "keyset": ["synthetic_key", "type"], "count": 1}]

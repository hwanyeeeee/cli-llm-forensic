import json
from clfx.cli import main

def test_parse_writes_events_jsonl(built_root, tmp_path, capsys):
    out = tmp_path / "events.jsonl"
    rc = main(["parse", str(built_root), "-o", str(out)])
    assert rc == 0 and out.exists()
    evs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    actions = {e["action"] for e in evs}
    assert {"paste","read","prompt"} <= actions
    assert all("source" in e and e["source"]["line"] >= 1 for e in evs)

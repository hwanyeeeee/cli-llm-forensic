import json
from clfx.cli import main

def test_analyze_enriches_events(built_root, tmp_path):
    ev = tmp_path/"events.jsonl"; an = tmp_path/"analyzed.jsonl"
    assert main(["parse", str(built_root), "-o", str(ev)]) == 0
    assert main(["analyze", str(ev), "--root", str(built_root), "-o", str(an)]) == 0
    rows = [json.loads(l) for l in an.read_text(encoding="utf-8").splitlines() if l.strip()]
    env_read = next(r for r in rows if r["action"]=="read" and r["target"].endswith(".env"))
    assert "secret" in env_read["tags"] and "bypass-mode" in env_read["tags"]
    assert "‹secret›" in env_read["preview"]

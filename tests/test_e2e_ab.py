import json
from clfx.cli import main

def test_ab_reconstruction_end_to_end(built_root, tmp_path, capsys):
    ev = tmp_path/"events.jsonl"; an = tmp_path/"analyzed.jsonl"
    assert main(["parse", str(built_root), "-o", str(ev)]) == 0
    assert main(["analyze", str(ev), "--root", str(built_root), "-o", str(an)]) == 0
    rows = [json.loads(l) for l in an.read_text(encoding="utf-8").splitlines() if l.strip()]

    # A: 사용자 붙여넣기 → actor:user, action:paste, 본문에 시크릿.
    # 골든은 contentHash 경로 → source 는 본문이 실재하는 paste-cache/<hash>.txt (증거 추적).
    a = [r for r in rows if r["action"]=="paste" and r["target"].startswith("[Pasted")]
    assert a and all(r["actor"]=="user" for r in a)
    assert any("secret" in r["tags"] for r in a)
    assert all(r["source"]["file"].endswith(".txt") and "paste-cache" in r["source"]["file"] for r in a)

    # B: 에이전트 자율 read → actor:agent, bypass-mode, source=transcript jsonl
    b = [r for r in rows if r["action"]=="read"]
    assert b and all(r["actor"]=="agent" for r in b)
    assert all("bypass-mode" in r["tags"] for r in b)
    assert all(r["source"]["file"].endswith(".jsonl") and r["source"]["line"]>=1 for r in b)

    # 질의로 주체 규명 — B는 agent 가 .env 를 읽음
    assert main(["query", str(an), "누가 .env 읽었어?"]) == 0
    out = capsys.readouterr().out
    assert "agent/read" in out and ".env" in out

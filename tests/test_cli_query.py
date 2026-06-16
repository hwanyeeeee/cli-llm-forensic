import json
from clfx.cli import main

def _prep(built_root, tmp_path):
    ev = tmp_path/"events.jsonl"; an = tmp_path/"analyzed.jsonl"
    main(["parse", str(built_root), "-o", str(ev)])
    main(["analyze", str(ev), "--root", str(built_root), "-o", str(an)])
    return an

def test_query_who_read_env(built_root, tmp_path, capsys):
    an = _prep(built_root, tmp_path)
    rc = main(["query", str(an), "누가 .env 읽었어?"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "agent" in out and ".env" in out
    assert ".jsonl:" in out         # source 인용 출력

def test_query_who_read_env_with_particle(built_root, tmp_path, capsys):
    # 한국어 조사 포함 쿼리도 .env read 규명 (데모 핵심경로)
    an = _prep(built_root, tmp_path)
    assert main(["query", str(an), "누가 .env를 읽었어?"]) == 0
    out = capsys.readouterr().out
    assert "agent/read" in out and ".env" in out

def test_query_who_read_id_rsa(built_root, tmp_path, capsys):
    # 점 없는 파일명(id_rsa) read 규명 — SSH키 핵심경로, broad-match 아님(1건만)
    an = _prep(built_root, tmp_path)
    assert main(["query", str(an), "누가 id_rsa 읽었어?"]) == 0
    out = capsys.readouterr().out
    assert "agent/read" in out and "id_rsa" in out
    assert out.count("agent/read") == 1     # id_rsa 하나만 (전체 read broad 반환 아님)

def test_query_read_without_filename_not_broad(built_root, tmp_path, capsys):
    # 파일명 없는 read 쿼리가 모든 read(5건)를 broad 반환하지 않음 → search 폴백
    an = _prep(built_root, tmp_path)
    assert main(["query", str(an), "누가 읽었어?"]) == 0
    out = capsys.readouterr().out
    assert out.count("agent/read") < 5      # broad면 5건 전부; 폴백이라 그 미만

def test_query_timeline(built_root, tmp_path, capsys):
    # 자연어 timeline 쿼리 → eng.timeline() 결정적 ts순 전체 반환
    an = _prep(built_root, tmp_path)
    assert main(["query", str(an), "타임라인 보여줘"]) == 0
    out = capsys.readouterr().out
    assert "agent/read" in out and "user/" in out      # 전체 이벤트 포함
    assert "events)" in out

def test_query_secrets(built_root, tmp_path, capsys):
    an = _prep(built_root, tmp_path)
    assert main(["query", str(an), "유출된 비밀 뭐야?"]) == 0
    out = capsys.readouterr().out
    assert "‹secret›" in out or "secret" in out

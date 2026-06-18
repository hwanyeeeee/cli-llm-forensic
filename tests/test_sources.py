from pathlib import Path

from clfx.sources.claude import ClaudeSource

def test_iter_jsonl_missing_path_yields_nothing_no_onfile(tmp_path):
    # OPT-4: exists() precheck 제거 후 직접 open. 없는 파일 → 0 이벤트·예외 없음·on_file 미발화.
    seen = []
    src = ClaudeSource(str(tmp_path), on_file=lambda p: seen.append(p))
    missing = tmp_path / "nope" / "ghost.jsonl"
    assert list(src._iter_jsonl(missing)) == []   # yield 없음, 예외 없음
    assert seen == []                               # 없는 파일엔 on_file 미발화

def test_iter_jsonl_existing_path_fires_onfile_once(tmp_path):
    # 열리는 파일은 on_file 정확히 1회(open 성공 후) 발화.
    import json as _j
    seen = []
    p = tmp_path / "h.jsonl"
    p.write_text(_j.dumps({"pastedContents": {}}) + "\n", encoding="utf-8")
    src = ClaudeSource(str(tmp_path), on_file=lambda x: seen.append(x))
    list(src._iter_jsonl(p))
    assert seen == [str(p)]

def test_history_records_yield_file_line_obj(built_root):
    src = ClaudeSource(built_root)
    recs = list(src.history_records())
    assert recs[0].file.endswith("history.jsonl") and recs[0].line == 1
    assert "pastedContents" in recs[0].obj

def test_transcript_records_span_project_files(built_root):
    src = ClaudeSource(built_root)
    recs = list(src.transcript_records())
    assert any(r.obj.get("toolUseResult") for r in recs)
    assert all(r.line >= 1 and r.file.endswith(".jsonl") for r in recs)

def test_paste_cache_path_resolves(built_root):
    src = ClaudeSource(built_root)
    h = next(iter(src.history_records())).obj["pastedContents"]["1"]["contentHash"]
    assert src.paste_cache_path(h).exists()

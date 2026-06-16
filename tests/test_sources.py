from clfx.sources.claude import ClaudeSource

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

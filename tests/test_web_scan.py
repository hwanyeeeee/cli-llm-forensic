from clfx.web.api import scan_to_engine, sources_payload


def test_scan_builds_engine_from_fixture():
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    assert len(eng.events) > 0
    assert any("origin:" in t for e in eng.events for t in e.tags)


def test_scan_enriches_secrets():
    # enrich가 돌았으면 secret/pii 태그 또는 마스킹(‹…›)이 존재해야 함(CLFXTEST 픽스처).
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    tagged = any(("secret" in e.tags or "pii" in e.tags) for e in eng.events)
    masked = any("‹" in (e.preview or "") for e in eng.events)
    assert tagged or masked


def test_sources_payload_shape():
    p = sources_payload()
    assert "sources" in p and isinstance(p["sources"], list)
    assert all({"path", "label", "exists"} <= set(s) for s in p["sources"])


def test_sources_payload_only_existing(monkeypatch):
    # 없는 후보(exists=False)는 화면에 안 보여야. discover_sources는 함수-지역 import라 원본을 패치.
    monkeypatch.setattr("clfx.discover.discover_sources",
        lambda: [{"path": "/a/.claude", "label": "wsl", "exists": True},
                 {"path": "/b/.claude", "label": "wsl", "exists": False}])
    out = sources_payload()
    assert [s["path"] for s in out["sources"]] == ["/a/.claude"]
    assert all(s["exists"] for s in out["sources"])


def test_scan_progress_is_file_count_based():
    from clfx.web.api import scan_to_engine
    calls = []
    eng = scan_to_engine(["tests/fixtures/dot-claude"], on_progress=lambda d,t,ev,cur: calls.append((d,t)))
    assert eng.events
    total = calls[-1][1]
    assert total > 0
    assert calls[-1][0] == total            # 최종 done==total(파일 전부 처리)
    assert all(d <= t for d,t in calls)     # done은 total 이하 단조


def test_claudesource_on_file_fires_per_file(tmp_path):
    from clfx.sources.claude import ClaudeSource
    import json as _j
    root = tmp_path / ".claude"; (root/"projects"/"p").mkdir(parents=True)
    (root/"history.jsonl").write_text(_j.dumps({"display":"x"})+"\n", encoding="utf-8")
    (root/"projects"/"p"/"a.jsonl").write_text("", encoding="utf-8")
    seen=[]
    src=ClaudeSource(str(root), on_file=lambda p: seen.append(p))
    list(src.history_records()); list(src.transcript_records())
    assert len(seen) == 2                   # history + a.jsonl 각 1회
    assert len(src.jsonl_files()) == 2 and len(src.transcript_files()) == 1


def test_scan_to_engine_reports_progress():
    from clfx.web.api import scan_to_engine
    calls = []
    eng = scan_to_engine(["tests/fixtures/dot-claude"], on_progress=lambda d,t,ev,cur: calls.append((d,t,ev)))
    assert eng.events
    assert calls and calls[-1][0] == calls[-1][1]          # done==total 마지막
    assert calls[-1][2] > 0                                 # 누적 events>0


def test_scan_merge_is_input_order_deterministic():
    from clfx.web.api import scan_to_engine
    # 같은 두 루트를 여러 번 스캔 → events의 (source.file,line) 시퀀스가 동일(run-to-run 결정적, I2)
    roots = ["tests/fixtures/dot-claude", "tests/fixtures/dot-claude"]
    seq1 = [(e.source.file, e.source.line) for e in scan_to_engine(roots).events]
    seq2 = [(e.source.file, e.source.line) for e in scan_to_engine(roots).events]
    assert seq1 == seq2 and len(seq1) > 0


def test_scan_equivalent_to_sequential():
    # 병렬·단일패스 결과 == 기존 순차(parse_source_tagged+enrich): 이벤트 전량·순서·태그 동일(무손실·I2 증명).
    from clfx.web.api import scan_to_engine
    from clfx.cli import parse_source_tagged
    from clfx.sources.claude import ClaudeSource
    from clfx.analyze.attribution import enrich
    root = "tests/fixtures/dot-claude"
    src = ClaudeSource(root); ref = parse_source_tagged(src, root); enrich(ref, src)
    got = scan_to_engine([root]).events
    assert len(got) == len(ref) and len(ref) > 0
    for a, b in zip(got, ref):
        assert (a.ts, a.actor, a.action, a.target, a.preview, a.source.file, a.source.line, sorted(a.tags)) \
            == (b.ts, b.actor, b.action, b.target, b.preview, b.source.file, b.source.line, sorted(b.tags))


def test_scan_bypass_collected_equals_reread():
    # 단일읽기 수집 bypass 태깅 == _bypass_sessions 재읽기 태깅(같은 read 이벤트에 bypass-mode).
    from clfx.web.api import scan_to_engine
    from clfx.cli import parse_source_tagged
    from clfx.sources.claude import ClaudeSource
    from clfx.analyze.attribution import enrich
    root = "tests/fixtures/dot-claude"
    src = ClaudeSource(root); ref = parse_source_tagged(src, root); enrich(ref, src)
    got = scan_to_engine([root]).events
    ref_b = {(e.source.file, e.source.line) for e in ref if "bypass-mode" in e.tags}
    got_b = {(e.source.file, e.source.line) for e in got if "bypass-mode" in e.tags}
    assert got_b == ref_b


def test_scan_parallel_merges_all_roots(tmp_path):
    # 병렬 scan: fixture + 빈 루트 → fixture 이벤트만, 정상 병합(빈 루트 0건).
    empty = tmp_path / "empty" / ".claude"; empty.mkdir(parents=True)
    eng = scan_to_engine(["tests/fixtures/dot-claude", str(empty)])
    assert len(eng.events) > 0
    # 엔진은 저장 시 정렬 안 함(질의 시 정렬) → 여기선 병합 완전성만 단언.
    assert any("origin:" in t for e in eng.events for t in e.tags)

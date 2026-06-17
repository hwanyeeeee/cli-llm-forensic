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


def test_scan_parallel_merges_all_roots(tmp_path):
    # 병렬 scan: fixture + 빈 루트 → fixture 이벤트만, 정상 병합(빈 루트 0건).
    empty = tmp_path / "empty" / ".claude"; empty.mkdir(parents=True)
    eng = scan_to_engine(["tests/fixtures/dot-claude", str(empty)])
    assert len(eng.events) > 0
    # 엔진은 저장 시 정렬 안 함(질의 시 정렬) → 여기선 병합 완전성만 단언.
    assert any("origin:" in t for e in eng.events for t in e.tags)

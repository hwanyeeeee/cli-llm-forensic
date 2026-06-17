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

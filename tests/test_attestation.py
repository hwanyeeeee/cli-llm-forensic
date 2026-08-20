def test_attestation_includes_db_triplet_and_collection_window():
    from clfx.web.api import attestation_payload

    manifest = {
        "/evidence/rollout.jsonl": "a" * 64,
        "/evidence/state_5.sqlite": "b" * 64,
        "/evidence/state_5.sqlite-wal": "c" * 64,
        "/evidence/state_5.sqlite-shm": "d" * 64,
    }
    result = attestation_payload(
        manifest, {"acquired_hashes": {}, "stat_only": []},
        started_at="2026-08-21T00:00:00Z", finished_at="2026-08-21T00:00:01Z")

    assert [row["path"] for row in result["acquired"]] == sorted(manifest)
    assert result["collection_started_at"] == "2026-08-21T00:00:00Z"
    assert result["collection_finished_at"] == "2026-08-21T00:00:01Z"

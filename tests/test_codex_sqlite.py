import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from clfx.event import Event, Source


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wal_db(path, schema, inserts, migration):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    conn.execute("CREATE TABLE _sqlx_migrations(version INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO _sqlx_migrations VALUES (?)", (migration,))
    for statement in schema:
        conn.execute(statement)
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for statement, params in inserts:
        conn.execute(statement, params)
    conn.commit()  # latest rows stay in WAL while this writer remains open
    assert Path(str(path) + "-wal").exists()
    assert Path(str(path) + "-shm").exists()
    return conn


def _sqlite_fixture(tmp_path, rollout_paths):
    root = tmp_path / "sqlite"
    state = root / "state_5.sqlite"
    state_conn = _wal_db(state, [
        """CREATE TABLE threads(
               id TEXT PRIMARY KEY, rollout_path TEXT, cwd TEXT, git_branch TEXT,
               git_sha TEXT, model TEXT, approval_mode TEXT, sandbox_policy TEXT)""",
    ], [
        ("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)",
         ("thread-1", str(rollout_paths[0]), "/case/one", "main", "abc123",
          "synthetic-model", "on-request", '{"type":"workspace-write"}')),
        ("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)",
         ("thread-2", str(rollout_paths[1]), "/case/two", "topic", "def456",
          "synthetic-model", "never", '{"type":"read-only"}')),
    ], migration=46)

    history = root / "thread_history_1.sqlite"
    history_conn = _wal_db(history, [
        """CREATE TABLE thread_turns(
               thread_id TEXT, turn_id TEXT, rollout_byte_offset INTEGER,
               rollout_end_ordinal INTEGER, rollout_end_byte_offset INTEGER)""",
        """CREATE TABLE thread_items(
               thread_id TEXT, turn_id TEXT, item_id TEXT, item_json TEXT,
               item_type TEXT)""",
    ], [
        ("INSERT INTO thread_turns VALUES (?,?,?,?,?)",
         ("thread-1", "turn-1", 120, 9, 480)),
        ("INSERT INTO thread_items VALUES (?,?,?,?,?)",
         ("thread-1", "turn-1", "item-1",
          json.dumps({"type": "commandExecution", "command": "printf synthetic"}),
          "commandExecution")),
    ], migration=4)

    logs = root / "logs_2.sqlite"
    logs_conn = _wal_db(logs, ["CREATE TABLE logs(id INTEGER PRIMARY KEY, body TEXT)"],
                        [("INSERT INTO logs(body) VALUES (?)", ("synthetic",))], migration=2)
    goals = root / "goals_1.sqlite"
    goals_conn = _wal_db(goals, ["CREATE TABLE thread_goals(id TEXT PRIMARY KEY)"],
                         [("INSERT INTO thread_goals VALUES (?)", ("goal-1",))], migration=2)
    memories = root / "memories_1.sqlite"
    memories_conn = _wal_db(memories, ["CREATE TABLE jobs(id TEXT PRIMARY KEY)"],
                            [("INSERT INTO jobs VALUES (?)", ("job-1",))], migration=1)
    queue = root / "queue_1.sqlite"
    queue_conn = _wal_db(queue, ["CREATE TABLE queued_items(id TEXT PRIMARY KEY)"],
                         [("INSERT INTO queued_items VALUES (?)", ("queue-1",))], migration=1)
    return root, [state_conn, history_conn, logs_conn, goals_conn, memories_conn, queue_conn]


def test_sqlite_snapshot_reads_wal_without_mutating_original(tmp_path):
    from clfx import roio
    from clfx.codex_sqlite import sqlite_snapshot

    main = tmp_path / "state_5.sqlite"
    writer = _wal_db(main, ["CREATE TABLE evidence(value TEXT)"],
                     [("INSERT INTO evidence VALUES (?)", ("latest-in-wal",))], migration=46)
    original = {str(Path(str(main) + suffix)): _digest(Path(str(main) + suffix))
                for suffix in ("", "-wal", "-shm")}
    roio.reset_audit()
    snapshot_dir = None
    try:
        with sqlite_snapshot(main) as snap:
            snapshot_dir = snap.directory
            assert [tuple(row) for row in snap.connection.execute(
                "SELECT value FROM evidence")] == [("latest-in-wal",)]
            assert snap.connection.execute("PRAGMA query_only").fetchone()[0] == 1
            with pytest.raises(sqlite3.OperationalError):
                snap.connection.execute("INSERT INTO evidence VALUES ('forbidden')")
            assert set(snap.manifest) == set(original)
            assert snap.started_at <= snap.finished_at
        assert not snapshot_dir.exists()
        assert {path: _digest(Path(path)) for path in original} == original
        audited = {row["path"] for row in roio.audit_records()}
        assert set(original) <= audited
    finally:
        writer.close()


def test_discovery_uses_migrations_and_collects_coverage_provenance(tmp_path):
    from clfx.codex_sqlite import collect_sqlite_support

    rollouts = [tmp_path / f"rollout-{number}.jsonl" for number in range(1, 4)]
    root, writers = _sqlite_fixture(tmp_path, rollouts)
    try:
        result = collect_sqlite_support(root, rollouts)
    finally:
        for writer in writers:
            writer.close()

    assert [(row["role"], row["migration_version"]) for row in result["databases"]] == [
        ("goals", 2), ("logs", 2), ("memories", 1), ("queue", 1),
        ("state", 46), ("thread_history", 4)]
    assert result["coverage"] == {
        "rollout_count": 3, "thread_count": 2, "projection_thread_count": 1}
    assert result["warnings"] == [{
        "kind": "sqlite_coverage", "rollout_count": 3, "thread_count": 2,
        "projection_thread_count": 1}]
    assert result["item_json_storage"] == "text"
    assert result["turns"] == [{
        "thread_id": "thread-1", "turn_id": "turn-1", "rollout_byte_offset": 120,
        "rollout_end_ordinal": 9, "rollout_end_byte_offset": 480}]
    assert all(Path(path).name in {
        "state_5.sqlite", "state_5.sqlite-wal", "state_5.sqlite-shm",
        "thread_history_1.sqlite", "thread_history_1.sqlite-wal",
        "thread_history_1.sqlite-shm", "logs_2.sqlite", "logs_2.sqlite-wal",
        "logs_2.sqlite-shm", "goals_1.sqlite", "goals_1.sqlite-wal",
        "goals_1.sqlite-shm", "memories_1.sqlite", "memories_1.sqlite-wal",
        "memories_1.sqlite-shm", "queue_1.sqlite", "queue_1.sqlite-wal",
        "queue_1.sqlite-shm"} for path in result["manifest"])


def test_sqlite_support_augments_raw_events_without_overriding_raw_policy(tmp_path):
    from clfx.codex_sqlite import augment_events, collect_sqlite_support

    rollouts = [tmp_path / "rollout-1.jsonl", tmp_path / "rollout-2.jsonl"]
    root, writers = _sqlite_fixture(tmp_path, rollouts)
    event = Event("2026-08-21T00:00:00Z", "codex", "thread-1", "agent", "response",
                  "", "synthetic", Source(str(rollouts[0]), 4),
                  meta={"turn_id": "turn-1", "sandbox_policy": {"type": "raw-policy"}})
    try:
        support = collect_sqlite_support(root, rollouts)
        augment_events([event], support)
    finally:
        for writer in writers:
            writer.close()

    assert event.meta["cwd"] == "/case/one"
    assert event.meta["git_branch"] == "main"
    assert event.meta["git_sha"] == "abc123"
    assert event.meta["model"] == "synthetic-model"
    assert event.meta["approval_mode"] == "on-request"
    assert event.meta["sandbox_policy"] == {"type": "raw-policy"}
    assert event.meta["sqlite_thread_id"] == "thread-1"
    assert event.meta["rollout_byte_offset"] == 120
    assert event.meta["rollout_end_ordinal"] == 9
    assert event.meta["rollout_end_byte_offset"] == 480


def test_scan_engine_merges_sqlite_manifest_warning_and_meta(tmp_path):
    from clfx.web.api import scan_to_engine

    root = tmp_path / ".codex"
    rollout = root / "sessions" / "2026" / "08" / "21" / "rollout-synthetic.jsonl"
    rollout.parent.mkdir(parents=True)
    rows = [
        {"timestamp": "2026-08-21T00:00:00Z", "type": "session_meta", "ordinal": 1,
         "payload": {"id": "thread-1", "cli_version": "0.147.0", "originator": "codex-tui"}},
        {"timestamp": "2026-08-21T00:00:01Z", "type": "event_msg", "ordinal": 2,
         "payload": {"type": "item_completed", "thread_id": "thread-1", "turn_id": "turn-1",
                     "item": {"type": "AgentMessage", "id": "item-1", "text": "synthetic"}}},
    ]
    rollout.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    sqlite_root, writers = _sqlite_fixture(tmp_path, [rollout, tmp_path / "other.jsonl"])
    (root / "config.toml").write_text(f'sqlite_home = "{sqlite_root}"\n', encoding="utf-8")
    try:
        engine = scan_to_engine([root])
    finally:
        for writer in writers:
            writer.close()

    event = engine.events[0]
    assert event.meta["sqlite_thread_id"] == "thread-1"
    assert event.meta["rollout_byte_offset"] == 120
    assert any(warning["kind"] == "sqlite_coverage" for warning in engine.source_warnings)
    assert set(engine.sqlite_support["coverage"]) == {
        "rollout_count", "thread_count", "projection_thread_count"}
    db_names = {Path(path).name for path in engine.evidence_manifest if ".sqlite" in path}
    assert {"state_5.sqlite", "state_5.sqlite-wal", "state_5.sqlite-shm"} <= db_names

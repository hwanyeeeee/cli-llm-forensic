"""Codex SQLite auxiliary index acquisition; rollout JSONL remains authoritative."""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from clfx import roio


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _path_key(path):
    return os.path.normcase(os.path.normpath(os.path.expanduser(str(path))))


def _copy_hash(source, destination):
    digest = hashlib.sha256()
    with roio._ro_open(source, "rb") as src, open(destination, "wb") as dst:
        while True:
            block = src.read(1 << 20)
            if not block:
                break
            digest.update(block)
            dst.write(block)
    return digest.hexdigest()


@dataclass
class SQLiteSnapshot:
    connection: sqlite3.Connection
    directory: Path
    manifest: dict
    started_at: str
    finished_at: str


@contextmanager
def sqlite_snapshot(main_path):
    """Copy main/WAL/SHM to an external temp dir, then open only the copy read-only."""
    main = Path(main_path)
    started_at = _now()
    temp = tempfile.TemporaryDirectory(prefix="clfx-sqlite-")
    directory = Path(temp.name)
    copied_main = directory / main.name
    manifest = {}
    connection = None
    try:
        for suffix in ("", "-wal", "-shm"):
            source = Path(str(main) + suffix)
            if not source.is_file():
                continue
            destination = Path(str(copied_main) + suffix)
            manifest[str(source)] = _copy_hash(source, destination)
        if str(main) not in manifest:
            raise FileNotFoundError(str(main))
        finished_at = _now()
        uri = "file:" + quote(copied_main.as_posix(), safe="/") + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        yield SQLiteSnapshot(connection, directory, manifest, started_at, finished_at)
    finally:
        if connection is not None:
            connection.close()
        temp.cleanup()


def _database_paths(root):
    paths = set()
    base = Path(root)
    for pattern in ("*.sqlite", "*.db"):
        paths.update(path for path in base.rglob(pattern)
                     if not path.name.endswith(("-wal", "-shm")))
    return sorted(paths, key=lambda path: _path_key(path))


def _tables(connection):
    return {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _role(tables):
    if "threads" in tables:
        return "state"
    if "thread_turns" in tables or "thread_items" in tables:
        return "thread_history"
    if "logs" in tables:
        return "logs"
    if "thread_goals" in tables:
        return "goals"
    if "jobs" in tables:
        return "memories"
    if "queued_items" in tables:
        return "queue"
    return "other"


def _rows(connection, table, wanted):
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    selected = [column for column in wanted if column in columns]
    if not selected:
        return []
    query = f"SELECT {','.join(selected)} FROM {table}"
    return [{column: row[column] for column in selected}
            for row in connection.execute(query)]


def _json_value(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def collect_sqlite_support(root, rollout_paths):
    """Acquire recognized SQLx DBs and return auxiliary metadata, never projected Events."""
    started_at = _now()
    databases = []
    manifest = {}
    warnings = []
    threads = []
    turns = []
    projection_threads = set()
    item_json_types = set()
    item_types = set()
    for path in _database_paths(root):
        try:
            with sqlite_snapshot(path) as snapshot:
                connection = snapshot.connection
                tables = _tables(connection)
                if "_sqlx_migrations" not in tables:
                    continue
                migration = connection.execute(
                    "SELECT max(version) FROM _sqlx_migrations").fetchone()[0]
                role = _role(tables)
                databases.append({"path": str(path), "role": role,
                                  "migration_version": migration})
                manifest.update(snapshot.manifest)
                missing = [str(path) + suffix for suffix in ("-wal", "-shm")
                           if str(path) + suffix not in snapshot.manifest]
                if missing:
                    warnings.append({"kind": "sqlite_sidecar_missing", "file": str(path),
                                     "missing": missing})
                if role == "state":
                    threads.extend(_rows(connection, "threads", (
                        "id", "rollout_path", "cwd", "git_branch", "git_sha", "model",
                        "approval_mode", "sandbox_policy")))
                elif role == "thread_history":
                    if "thread_turns" in tables:
                        turns.extend(_rows(connection, "thread_turns", (
                            "thread_id", "turn_id", "rollout_byte_offset",
                            "rollout_end_ordinal", "rollout_end_byte_offset")))
                    if "thread_items" in tables:
                        projection_threads.update(row[0] for row in connection.execute(
                            "SELECT DISTINCT thread_id FROM thread_items"))
                        item_json_types.update(row[0] for row in connection.execute(
                            "SELECT DISTINCT typeof(item_json) FROM thread_items"))
                        item_types.update(row[0] for row in connection.execute(
                            "SELECT DISTINCT item_type FROM thread_items") if row[0] is not None)
        except (OSError, sqlite3.Error) as error:
            warnings.append({"kind": "sqlite_acquisition", "file": str(path),
                             "error": type(error).__name__})

    threads.sort(key=lambda row: (str(row.get("rollout_path") or ""), str(row.get("id") or "")))
    turns.sort(key=lambda row: (str(row.get("thread_id") or ""),
                                str(row.get("turn_id") or "")))
    for row in threads:
        row["sandbox_policy"] = _json_value(row.get("sandbox_policy"))
    coverage = {
        "rollout_count": len({_path_key(path) for path in rollout_paths}),
        "thread_count": len({row.get("id") for row in threads if row.get("id")}),
        "projection_thread_count": len(projection_threads),
    }
    if len(set(coverage.values())) > 1:
        warnings.append({"kind": "sqlite_coverage", **coverage})
    warnings.sort(key=lambda row: (row.get("file", ""), row.get("kind", "")))
    storage = next(iter(item_json_types)) if len(item_json_types) == 1 else ",".join(sorted(item_json_types))
    return {
        "databases": sorted(databases, key=lambda row: _path_key(row["path"])),
        "threads": threads,
        "turns": turns,
        "item_types": sorted(item_types),
        "item_json_storage": storage,
        "coverage": coverage,
        "warnings": warnings,
        "manifest": {path: manifest[path] for path in sorted(manifest)},
        "collection_started_at": started_at,
        "collection_finished_at": _now(),
    }


def augment_events(events, support):
    """Attach SQLite session/turn metadata with setdefault; raw rollout values always win."""
    threads = support.get("threads") or []
    by_path = {_path_key(row["rollout_path"]): row for row in threads if row.get("rollout_path")}
    by_id = {str(row["id"]): row for row in threads if row.get("id")}
    turns = {(str(row.get("thread_id") or ""), str(row.get("turn_id") or "")): row
             for row in support.get("turns") or []}
    for event in events:
        thread = by_path.get(_path_key(event.source.file)) or by_id.get(str(event.session))
        if thread:
            event.meta.setdefault("sqlite_thread_id", thread.get("id"))
            for key in ("cwd", "git_branch", "git_sha", "model", "approval_mode",
                        "sandbox_policy"):
                if thread.get(key) is not None:
                    event.meta.setdefault(key, thread[key])
        thread_id = str(event.meta.get("sqlite_thread_id") or
                        event.meta.get("thread_id") or event.session or "")
        turn_id = str(event.meta.get("turn_id") or "")
        turn = turns.get((thread_id, turn_id))
        if turn:
            for key in ("rollout_byte_offset", "rollout_end_ordinal",
                        "rollout_end_byte_offset"):
                if turn.get(key) is not None:
                    event.meta.setdefault(key, turn[key])
    return events

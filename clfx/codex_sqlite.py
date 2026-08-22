"""Codex SQLite auxiliary index acquisition; rollout JSONL remains authoritative."""
import hashlib
import json
import os
import re
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


# --- 원격 채널 판별 (logs_2.sqlite) ----------------------------------------
# rollout 에는 원격 여부가 없다. logs_2 의 tracing span 텍스트에서
#   app_server.connection_id=N ∧ app_server.client_name="…"
# 로 연결별 클라이언트를 만들고, 같은 span 에 실린 thread_id 로 스레드에 잇는다.
# **연결 단위로 묶는 게 핵심**이다 — 최근 RPC 표본만 훑으면 connection 0 의 codex-tui
# plugin/list 노이즈가 다수라 원격 연결이 묻힌다(실측: tui 138행 vs 원격 69행).
_LOG_CONNECTION = re.compile(r"app_server\.connection_id=(\d+)")
_LOG_CLIENT = re.compile(r'app_server\.client_name="([^"]*)"')
_LOG_THREAD = re.compile(r'thread_id[=:]\s*"?([0-9a-fA-F][0-9a-fA-F-]{7,})')
_LOG_TURN_START = re.compile(r"turn/start connection_id=ConnectionId\((\d+)\)")
_REMOTE_CLIENT_MARKER = "_remote"
# 원격 client_name 에는 조작 단말의 OS 가 박혀 있다: codex_chatgpt_ios_remote /
# codex_chatgpt_android_remote. Claude 에는 이 축이 아예 없다 — Codex 로그만 갖는 정보다.
_CLIENT_OS_SUFFIXES = (("_ios_remote", "ios"), ("_android_remote", "android"))


def _client_channel(client_name):
    """client_name → remote | local. 빈 이름은 판정 불가(None)."""
    if not client_name:
        return None
    return "remote" if client_name.endswith(_REMOTE_CLIENT_MARKER) else "local"


def _client_os(client_name):
    """client_name → 조작 단말 OS.

    로컬 클라이언트는 None 이다 — `codex-tui` 는 "로컬"을 말할 뿐 OS 를 말하지 않는다.
    locality 는 origin_channel 이 이미 담으므로 여기서 겹쳐 싣지 않는다.
    원격인데 접미가 낯설면 unknown — 새 플랫폼이 조용히 누락되면 안 된다."""
    if _client_channel(client_name) != "remote":
        return None
    for suffix, os_name in _CLIENT_OS_SUFFIXES:
        if client_name.endswith(suffix):
            return os_name
    return "unknown"


def _collect_remote_channel(connection):
    """logs 테이블 → {"threads": {thread_id: {"channel","seen"}}, "connections", "turn_connections"}.

    한 스레드가 원격·로컬 연결 양쪽에 보이면 어느 **턴**이 어느 쪽인지 단정할 수 없다 → unknown.
    실측에서 실제로 나온다: 로컬 TUI 로 시작한 스레드를 폰에서 thread/resume 하면 둘 다 찍힌다.
    그 경우에도 관측 자체는 버리지 않고 `seen` 에 남긴다 — unknown 의 근거를 사후 감사하려고.
    로그에 아예 안 보이는 스레드는 여기 없다(관측 부재 ≠ 로컬)."""
    clients, thread_seen, turn_connections = {}, {}, set()
    columns = {row[1] for row in connection.execute("PRAGMA table_info(logs)")}
    if "feedback_log_body" not in columns:      # 스키마가 다른 logs 테이블 → 판별 불가(빈 결과)
        return {"threads": {}, "connections": {}, "turn_connections": []}
    for (body,) in connection.execute(          # 스트리밍 — 로그 본문 전체를 리스트로 물리지 않는다
            "SELECT feedback_log_body FROM logs WHERE feedback_log_body IS NOT NULL"):
        conn_match = _LOG_CONNECTION.search(body)
        client_match = _LOG_CLIENT.search(body)
        if conn_match and client_match and client_match.group(1):
            clients.setdefault(conn_match.group(1), set()).add(client_match.group(1))
        for started in _LOG_TURN_START.findall(body):
            turn_connections.add(started)
        if conn_match:
            for thread in _LOG_THREAD.findall(body):
                thread_seen.setdefault(thread, set()).add(conn_match.group(1))

    connections = {}
    for cid, names in clients.items():
        channels = {_client_channel(name) for name in names} - {None}
        oses = {_client_os(name) for name in names} - {None}
        connections[cid] = {"client_names": sorted(names),
                            "channel": channels.pop() if len(channels) == 1 else "unknown",
                            "os": oses.pop() if len(oses) == 1 else ("unknown" if oses else None),
                            "started_turns": cid in turn_connections}
    threads = {}
    for thread, cids in thread_seen.items():
        channels = {connections.get(cid, {}).get("channel") for cid in cids} - {None, "unknown"}
        # OS 는 원격 연결에서만 나온다. 로컬로만 보인 스레드는 빈 집합 → 필드를 안 단다.
        oses = {connections.get(cid, {}).get("os") for cid in cids} - {None}
        threads[thread] = {"channel": channels.copy().pop() if len(channels) == 1 else "unknown",
                           "seen": sorted(channels),
                           "os": oses.copy().pop() if len(oses) == 1 else ("unknown" if oses else None),
                           "os_seen": sorted(oses - {"unknown"})}
    return {"threads": threads,
            "connections": {cid: connections[cid] for cid in sorted(connections, key=int)},
            "turn_connections": sorted(turn_connections, key=int)}


def _collect_enrollments(connection):
    """remote_control_enrollments → 등록 행. 0행이 미사용을 뜻하지 않는다(enroll 실패도 0행)."""
    return _rows(connection, "remote_control_enrollments",
                 ("websocket_url", "account_id", "app_server_client_name", "server_id",
                  "environment_id", "server_name", "updated_at", "remote_control_enabled"))


def enrollment_marker(support):
    """`remote_control_enrollments` → 원격제어 마커 1행(소스 메타 계층, Event 아님).

    **0행은 미사용이 아니다.** enroll 이 MFA 로 거부돼도 행은 안 남는다 — 그래서
    빈 결과는 `none` 이 아니라 `unknown` 이다. state DB 를 아예 못 읽었을 때와
    구분하려고 DB 유무를 status 로 나눈다."""
    from clfx.sources.markers import marker
    databases = [row for row in (support or {}).get("databases") or []
                 if row.get("role") == "state"]
    path = databases[0]["path"] if databases else "(state DB 미발견)"
    note = ("등록 행은 '어느 환경에 등록됐나'까지만 말한다. 0행은 미사용이 아니다 — "
            "enroll 이 MFA 로 거부돼도 0행이고, 등록이 남아 있어도 채널은 죽어 있을 수 있다.")
    if not databases:
        return marker("codex_remote_control_enrollments", "codex", path,
                      "missing", "unknown", note)
    rows = (support or {}).get("remote_control_enrollments") or []
    # 자격증명·URL 은 안 싣는다. 조사자가 알아야 하는 건 '어느 환경에 등록됐나'다.
    # 빈 문자열은 관측이 아니라 빈 칸이라 뺀다. 0/False 는 남긴다 — 그건 실제 값이다.
    listed = [{key: row[key] for key in
               ("environment_id", "server_name", "app_server_client_name",
                "remote_control_enabled", "updated_at")
               if row.get(key) is not None and row.get(key) != ""}
              for row in rows]
    return marker("codex_remote_control_enrollments", "codex", path, "observed",
                  "configured" if rows else "unknown", note,
                  values={"enrollments": len(rows)}, enrollments=listed)


def collect_sqlite_support(root, rollout_paths):
    """Acquire recognized SQLx DBs and return auxiliary metadata, never projected Events."""
    started_at = _now()
    databases = []
    manifest = {}
    warnings = []
    threads = []
    turns = []
    enrollments = []
    remote_channel = {"threads": {}, "connections": {}, "turn_connections": []}
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
                    enrollments.extend(_collect_enrollments(connection))
                elif role == "logs":
                    remote_channel = _collect_remote_channel(connection)
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
        "remote_channel": remote_channel,
        "remote_control_enrollments": enrollments,
        "warnings": warnings,
        "manifest": {path: manifest[path] for path in sorted(manifest)},
        "collection_started_at": started_at,
        "collection_finished_at": _now(),
    }


def augment_events(events, support):
    """Attach SQLite session/turn metadata with setdefault; raw rollout values always win."""
    channels = (support.get("remote_channel") or {}).get("threads") or {}
    # 원격 등록 정보는 '어느 환경에 등록됐나'까지만 말한다(VR-023: 행이 있어도 채널은 죽어 있을 수 있음).
    # 그래서 원격으로 판정된 Event 에만 붙인다 — 등록 행 자체가 원격 실행의 근거는 아니다.
    enrollment = next(iter(support.get("remote_control_enrollments") or []), {})
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
        observed = channels.get(thread_id)
        if observed:                      # 로그에 안 보이는 스레드는 필드를 안 단다(관측 부재 ≠ local)
            event.meta.setdefault("origin_channel", observed["channel"])
            if len(observed["seen"]) > 1:      # unknown 인 이유(원격·로컬 양쪽 관측)를 남긴다
                event.meta.setdefault("origin_channels_seen", observed["seen"])
            # OS 는 채널이 remote 로 확정됐을 때만 단정한다. 채널이 unknown 이면 그 이벤트는
            # 로컬 턴일 수도 있고, 그런 이벤트에 단말을 붙이면 없는 사실을 만든다.
            # 관측 자체는 버리지 않고 candidates 로 남긴다(그 스레드를 만진 원격 단말이 뭐였는지).
            if observed.get("os"):
                if observed["channel"] == "remote":
                    event.meta.setdefault("origin_os", observed["os"])
                    if len(observed.get("os_seen") or []) > 1:
                        event.meta.setdefault("origin_os_seen", observed["os_seen"])
                else:
                    event.meta.setdefault("origin_os_candidates",
                                          observed.get("os_seen") or [observed["os"]])
            if "remote" in observed["seen"]:
                for key in ("environment_id", "server_name"):
                    if enrollment.get(key):
                        event.meta.setdefault(key, enrollment[key])
    return events

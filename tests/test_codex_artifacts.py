import json
import os


def _file(path, data, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


def test_codex_temp_summary_reports_observation_not_retention_policy(tmp_path):
    from clfx.analyze.codex_artifacts import codex_temp_summary

    now = 1_000_000.0
    root = tmp_path / ".codex"
    _file(root / "tmp" / "run.tmp", b"123", now - 2 * 86400)
    _file(root / ".tmp" / "plugins" / "cache-a", b"1234", now - 1 * 86400)
    _file(root / ".tmp" / "marketplaces" / "cache-b", b"12", now - 3 * 86400)
    _file(root / "shell_snapshots" / "shell.sh", b"12345", now - 4 * 86400)
    _file(root / "thread-writer-locks" / "lock", b"1", now - 5 * 86400)
    _file(root / "attachments" / "input.png", b"123456", now - 6 * 86400)
    _file(root / "dictation-history" / "speech.txt", b"1234567", now - 7 * 86400)
    temp = tmp_path / "windows-temp"
    _file(temp / "codex-clipboard-one.png", b"12345678", now - 8 * 86400)
    _file(temp / "unrelated.png", b"ignored", now - 9 * 86400)

    result = codex_temp_summary([root], temp_dirs=[temp], now_epoch=now)

    rows = {row["kind"]: row for row in result["rows"]}
    assert rows[".tmp"]["count"] == 2 and rows[".tmp"]["bytes"] == 6
    assert rows[".tmp"]["observed_age_days"] == {"min": 1.0, "max": 3.0, "median": 2.0}
    assert rows[".tmp"]["content_class"] == "plugin_cache_sync"
    assert rows["clipboard"]["count"] == 1 and rows["clipboard"]["bytes"] == 8
    assert {"tmp", "shell_snapshots", "thread-writer-locks", "attachments",
            "dictation-history", "clipboard"} <= set(rows)
    assert all(row["policy"] == "unknown" and row["attribution"] == "unknown"
               for row in rows.values())
    assert "RETENTION_DAYS" not in repr(result)
    assert "expires_in_days" not in repr(result)
    assert result["errors"] == []

    from clfx.web.api import forensic_scan
    surfaced = forensic_scan([], roots=[root], tmp_dirs=[])
    assert {row["kind"] for row in surfaced["codex_temp"]["rows"]} >= {".tmp", "tmp"}


def test_codex_config_exposes_only_keys_and_keeps_web_search_separate(tmp_path):
    from clfx import roio
    from clfx.analyze.codex_artifacts import codex_config_summary

    root = tmp_path / ".codex"
    root.mkdir()
    config = root / "config.toml"
    config.write_text("""
[mcp_servers.safe-server]
command = "do-not-output-command"
args = ["--token", "do-not-output-token"]
env = { API_TOKEN = "do-not-output-env" }
headers = { Authorization = "do-not-output-auth" }

[hooks]
after_save = ["do-not-output-hook"]

[plugins.alpha]
enabled = true

[web]
search = true
""", encoding="utf-8")
    roio.reset_audit()

    result = codex_config_summary(root)

    assert result["mcp_configs"] == [{
        "server": "safe-server", "scope": "codex", "project": None,
        "command": None, "args": [], "type": None, "url": None,
        "env_keys": ["API_TOKEN"], "source_file": str(config),
        "config_keys": ["args", "command", "env", "headers"],
    }]
    assert result["hooks"] == ["after_save"]
    assert result["plugins"] == ["alpha"]
    assert result["web_search"] == ["web.search"]
    assert "web.search" not in {row["server"] for row in result["mcp_configs"]}
    blob = repr(result)
    for secret in ("do-not-output-command", "do-not-output-token", "do-not-output-env",
                   "do-not-output-auth", "do-not-output-hook"):
        assert secret not in blob
    assert roio.audit_records() == [{"path": str(config), "mode": "rb"}]


def test_cli_parse_applies_same_codex_sqlite_meta_as_scan(tmp_path, monkeypatch):
    from clfx.cli import parse_roots
    import clfx.codex_sqlite as codex_sqlite

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
    support = {
        "databases": [{"path": "/db/state.sqlite", "role": "state", "migration_version": 1}],
        "threads": [{"id": "thread-1", "rollout_path": str(rollout), "cwd": "/case"}],
        "turns": [], "warnings": [], "manifest": {}, "coverage": {},
    }
    monkeypatch.setattr(codex_sqlite, "collect_sqlite_support",
                        lambda sqlite_root, rollout_paths: support)

    events = parse_roots([root])

    assert events[0].meta["sqlite_thread_id"] == "thread-1"
    assert events[0].meta["cwd"] == "/case"

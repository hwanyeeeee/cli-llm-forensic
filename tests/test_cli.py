from pathlib import Path
from types import SimpleNamespace

import clfx.cli as cli


def test_parse_roots_constructs_sources_through_registry(monkeypatch):
    seen = []
    fake = object()
    monkeypatch.setattr(cli, "source_for", lambda root: seen.append(root) or fake)
    monkeypatch.setattr(cli, "parse_source_tagged", lambda src, root: [] if src is fake else None)
    assert cli.parse_roots(["one", "two"]) == []
    assert seen == ["one", "two"]


def test_null_source_agent_is_explicit_not_claude_hardcoded():
    assert cli._NullSource("codex").agent == "codex"
    assert cli._NullSource("unknown").agent == "unknown"


def test_direct_claude_source_construction_removed_from_entrypoints():
    root = Path(__file__).resolve().parents[1]
    for rel in ("clfx/cli.py", "clfx/web/api.py", "clfx/wsl_helper.py"):
        assert "ClaudeSource(" not in (root / rel).read_text(encoding="utf-8"), rel


def test_parse_reports_source_errors_and_exits_nonzero(tmp_path, capsys):
    root = tmp_path / ".codex"
    rollout = root / "sessions" / "2026" / "08" / "21" / "rollout-broken.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text('{"type":"session_meta","payload":{}}\n{broken}\n', encoding="utf-8")
    out = tmp_path / "events.jsonl"
    assert cli.main(["parse", str(root), "-o", str(out)]) == 1
    assert out.exists()
    stderr = capsys.readouterr().err
    assert "source warning" in stderr and "JSONDecodeError" in stderr


def test_parse_sqlite_advisory_warnings_do_not_fail_real_run(tmp_path, monkeypatch, capsys):
    source = SimpleNamespace(sqlite_warnings=[
        {"kind": "sqlite_coverage", "rollout_count": 3, "thread_count": 2,
         "projection_thread_count": 1},
        {"kind": "sqlite_sidecar_missing", "file": "/db/queue.sqlite",
         "missing": ["/db/queue.sqlite-wal"]},
    ])

    def parse_roots(_roots, sources_out):
        sources_out.append(source)
        return []

    monkeypatch.setattr(cli, "parse_roots", parse_roots)
    args = SimpleNamespace(root=["synthetic"], out=str(tmp_path / "events.jsonl"))

    assert cli.cmd_parse(args) == 0
    assert capsys.readouterr().err.count("clfx source warning") == 2

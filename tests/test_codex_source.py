import hashlib
import json
from pathlib import Path
import tomllib

import pytest

from clfx import roio
import clfx.sources as sources


def _api():
    assert hasattr(sources, "CodexSource") and hasattr(sources, "source_for")
    return sources.CodexSource, sources.source_for


def _write_rollout(root, day, name, rows):
    path = root / "sessions" / "2026" / "08" / day / f"rollout-{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join(row if isinstance(row, bytes) else json.dumps(row).encode() + b"\n"
                    for row in rows)
    path.write_bytes(data)
    return path, data


def test_codex_source_streams_recursive_rollouts_and_preserves_errors(tmp_path):
    CodexSource, _ = _api()
    root = tmp_path / ".codex"
    good1 = {"type": "session_meta", "payload": {"id": "s"}}
    good2 = {"type": "event_msg", "payload": {"type": "task_complete"}}
    path, data = _write_rollout(root, "21", "a", [good1, b"{broken}\n", good2])
    _write_rollout(root, "20", "b", [good2])

    seen = []
    roio.reset_audit()
    src = CodexSource(root, on_file=seen.append)
    sha = {}
    records = list(src._iter_jsonl(path, sha_out=sha))

    assert src.agent == "codex"
    assert [(r.line, r.obj) for r in records] == [(1, good1), (3, good2)]
    assert src.parse_errors == [{"file": str(path), "line": 2, "error": "JSONDecodeError"}]
    assert sha["sha"] == hashlib.sha256(data).hexdigest()
    assert seen == [str(path)]
    assert roio.modes_seen() == ["rb"]
    assert [p.parent.name for p in src.jsonl_files()] == ["20", "21"]
    assert list(src.history_records()) == []


def test_codex_home_and_sqlite_root_are_resolved_separately(tmp_path, monkeypatch):
    CodexSource, _ = _api()
    home = tmp_path / "home" / ".codex"; home.mkdir(parents=True)
    configured = tmp_path / "configured-sqlite"; configured.mkdir()
    env_sqlite = tmp_path / "env-sqlite"; env_sqlite.mkdir()
    explicit = tmp_path / "explicit"; explicit.mkdir()
    (home / "config.toml").write_text(f'sqlite_home = "{configured}"\n', encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("CODEX_SQLITE_HOME", str(env_sqlite))

    src = CodexSource()
    assert src.root == home and src.sqlite_root == configured

    (home / "config.toml").unlink()
    assert CodexSource().sqlite_root == env_sqlite
    assert CodexSource(explicit).root == explicit


def test_sqlite_home_supports_toml_comments_and_project_requires_python_311(
        tmp_path, monkeypatch):
    import clfx.sources.codex as codex
    root = tmp_path / ".codex"; root.mkdir()
    configured = tmp_path / "sqlite"; configured.mkdir()
    fallback = tmp_path / "fallback"; fallback.mkdir()
    config = root / "config.toml"
    config.write_text(f'sqlite_home = "{configured}" # valid TOML comment\n', encoding="utf-8")
    monkeypatch.setenv("CODEX_SQLITE_HOME", str(fallback))
    src = codex.CodexSource(root)
    assert src.sqlite_root == configured
    assert src.config_errors == []

    repo = Path(__file__).parents[1]
    project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["requires-python"] == ">=3.11"
    source = (repo / "clfx" / "sources" / "codex.py").read_text(encoding="utf-8")
    assert "ModuleNotFoundError" not in source
    assert "tomllib = None" not in source


def test_config_permission_error_is_not_treated_as_missing(tmp_path, monkeypatch):
    CodexSource, _ = _api()
    root = tmp_path / ".codex"; root.mkdir()
    fallback = tmp_path / "fallback"; fallback.mkdir()
    config = root / "config.toml"
    monkeypatch.setenv("CODEX_SQLITE_HOME", str(fallback))
    real_open = roio._ro_open

    def deny_config(target, mode="rb", **kwargs):
        if str(target) == str(config):
            raise PermissionError("denied")
        return real_open(target, mode, **kwargs)

    monkeypatch.setattr(roio, "_ro_open", deny_config)
    src = CodexSource(root)
    assert src.sqlite_root == fallback
    assert src.config_errors == [{"file": str(config), "error": "PermissionError"}]


def test_rollout_open_failure_is_an_acquisition_error(tmp_path, monkeypatch):
    CodexSource, _ = _api()
    root = tmp_path / ".codex"
    path, _ = _write_rollout(root, "21", "denied", [{"type": "session_meta"}])
    src = CodexSource(root)
    real_open = roio._ro_open

    def deny_rollout(target, mode="rb", **kwargs):
        if str(target) == str(path):
            raise PermissionError("denied")
        return real_open(target, mode, **kwargs)

    monkeypatch.setattr(roio, "_ro_open", deny_rollout)
    assert list(src._iter_jsonl(path)) == []
    assert src.acquisition_errors == [{"file": str(path), "error": "PermissionError"}]


def test_source_warnings_are_sorted_by_file_and_line(tmp_path):
    CodexSource, _ = _api()
    src = CodexSource(tmp_path / ".codex")
    src.parse_errors.extend([
        {"file": "/z/rollout.jsonl", "line": 9, "error": "JSONDecodeError"},
        {"file": "/a/rollout.jsonl", "line": 4, "error": "JSONDecodeError"},
    ])
    src.acquisition_errors.append(
        {"file": "/a/rollout.jsonl", "error": "PermissionError"})

    assert sources.source_warnings(src) == [
        {"kind": "acquisition", "file": "/a/rollout.jsonl",
         "error": "PermissionError"},
        {"kind": "parse", "file": "/a/rollout.jsonl", "line": 4,
         "error": "JSONDecodeError"},
        {"kind": "parse", "file": "/z/rollout.jsonl", "line": 9,
         "error": "JSONDecodeError"},
    ]


def test_missing_sessions_directory_is_an_acquisition_warning(tmp_path):
    _, source_for = _api()
    root = tmp_path / ".codex"
    root.mkdir()
    src = source_for(root)
    expected = {"file": str(root / "sessions"), "error": "FileNotFoundError"}

    assert src.jsonl_files() == []
    assert src.jsonl_files() == []
    assert src.acquisition_errors == [expected]
    assert sources.source_warnings(src) == [{"kind": "acquisition", **expected}]


def test_scan_engine_and_events_api_surface_source_warnings(tmp_path):
    from clfx.web.api import events_payload, scan_to_engine
    root = tmp_path / ".codex"
    path, _ = _write_rollout(root, "21", "broken", [b"{broken}\n"])
    engine = scan_to_engine([root])
    expected = [{"kind": "parse", "file": str(path), "line": 1,
                 "error": "JSONDecodeError"}]
    assert engine.source_warnings == expected
    assert events_payload(engine)["warnings"] == expected


def test_source_registry_detects_layout_and_rejects_ambiguous_parent(tmp_path):
    ClaudeSource = sources.ClaudeSource
    CodexSource, source_for = _api()
    claude = tmp_path / "claude-layout"; (claude / "projects").mkdir(parents=True)
    codex = tmp_path / "codex-layout"; (codex / "sessions").mkdir(parents=True)
    assert isinstance(source_for(claude), ClaudeSource)
    assert isinstance(source_for(codex), CodexSource)

    parent = tmp_path / "parent"; (parent / ".codex").mkdir(parents=True)
    assert source_for(parent).root == parent / ".codex"
    (parent / ".claude").mkdir()
    with pytest.raises(ValueError, match="ambiguous"):
        source_for(parent)


@pytest.mark.parametrize("name, expected", [(".claude", "claude"), (".codex", "codex")])
def test_explicit_source_basename_never_probes_filesystem(monkeypatch, name, expected):
    def fail_probe(_path):
        raise AssertionError("explicit source basename must not call is_dir")

    monkeypatch.setattr(sources.Path, "is_dir", fail_probe)
    kind, resolved = sources._source_layout(sources.Path(r"\\wsl.localhost\Ubuntu\home\u") / name)
    assert kind == expected and resolved.name == name


def test_nonstandard_codex_home_is_authoritative_without_layout_probe(monkeypatch):
    root = sources.Path(r"\\wsl.localhost\Ubuntu\evidence\custom-home")
    monkeypatch.setenv("CODEX_HOME", str(root))
    monkeypatch.setattr(sources.Path, "is_dir",
                        lambda _path: (_ for _ in ()).throw(AssertionError("unexpected probe")))
    assert sources._source_layout(root) == ("codex", root)

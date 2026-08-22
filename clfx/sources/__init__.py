"""Source registry and layout detection."""
import os
from pathlib import Path

from clfx.sources.claude import ClaudeSource
from clfx.sources.codex import CodexSource


SOURCE_REGISTRY = {"claude": ClaudeSource, "codex": CodexSource}


def _source_layout(root):
    path = Path(root)
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home and Path(codex_home).expanduser() == path.expanduser():
        return "codex", path
    basename = path.name.lower()
    if basename in (".claude", ".codex"):
        return basename[1:], path
    direct = []
    if (path / "projects").is_dir():
        direct.append(("claude", path))
    if (path / "sessions").is_dir():
        direct.append(("codex", path))
    if len(direct) == 1:
        return direct[0]
    if len(direct) > 1:
        raise ValueError(f"ambiguous source root: {path}")

    nested = [(name, path / f".{name}") for name in SOURCE_REGISTRY
              if (path / f".{name}").is_dir()]
    if len(nested) == 1:
        return nested[0]
    if len(nested) > 1:
        raise ValueError(f"ambiguous source root: {path}")
    raise ValueError(f"unknown source root: {path}")


def source_for(root, on_file=None):
    name, resolved = _source_layout(root)
    return SOURCE_REGISTRY[name](resolved, on_file=on_file)


def remote_control_markers(source):
    """소스 1개의 원격제어 마커 목록. `source_warnings` 와 같은 계층 — Event 가 아니다.

    마커 판독은 소스별 레이아웃 지식이라 각 소스 클래스가 갖는다. 여기서는 라우팅만.
    읽기 실패는 마커 안의 `status` 로 보고되므로 예외로 스캔을 죽이지 않는다."""
    reader = getattr(source, "remote_control_markers", None)
    return list(reader()) if reader else []


def source_warnings(source):
    out = []
    for kind, attr in (("acquisition", "acquisition_errors"),
                       ("config", "config_errors"), ("parse", "parse_errors"),
                       ("unsupported_schema", "schema_warnings"),
                       ("capability_mismatch", "capability_warnings")):
        out.extend({"kind": kind, **row} for row in getattr(source, attr, ()))
    out.extend(getattr(source, "sqlite_warnings", ()))
    return sorted(out, key=lambda row: (row.get("file", ""), row.get("line", 0),
                                        row.get("kind", ""), row.get("error", "")))


__all__ = ["ClaudeSource", "CodexSource", "SOURCE_REGISTRY", "source_for",
           "source_warnings", "remote_control_markers"]

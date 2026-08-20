"""Codex-specific temp observations and key-only config inventory."""
import fnmatch
import os
import stat
import statistics
import tomllib
from pathlib import Path

from clfx import roio


_KINDS = (
    ("tmp", "tmp", "runtime_temp"),
    (".tmp", ".tmp", "plugin_cache_sync"),
    ("shell_snapshots", "shell_snapshots", "runtime_temp"),
    ("thread-writer-locks", "thread-writer-locks", "runtime_lock"),
    ("attachments", "attachments", "input_cache"),
    ("dictation-history", "dictation-history", "input_cache"),
)


def _inventory(directory, errors):
    files = []
    if not directory.is_dir():
        return files

    def onerror(error):
        errors.append({"path": str(getattr(error, "filename", None) or directory),
                       "reason": type(error).__name__})

    for dirpath, _dirnames, names in os.walk(directory, followlinks=False, onerror=onerror):
        for name in names:
            path = Path(dirpath) / name
            try:
                info = path.lstat()
            except OSError as error:
                errors.append({"path": str(path), "reason": type(error).__name__})
                continue
            if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                files.append((path, info))
    return files


def codex_temp_summary(roots, temp_dirs=None, now_epoch=None):
    """Report only observed age/count/bytes; Codex retention policy is unknown."""
    now = float(now_epoch if now_epoch is not None else __import__("time").time())
    grouped = {kind: {"roots": [], "files": [], "class": content_class}
               for kind, _dirname, content_class in _KINDS}
    errors = []
    for root in roots or []:
        base = Path(root)
        for kind, dirname, _content_class in _KINDS:
            directory = base / dirname
            files = _inventory(directory, errors)
            if files:
                grouped[kind]["roots"].append(str(directory))
                grouped[kind]["files"].extend(files)

    clipboard_dirs = list(temp_dirs or [])
    if temp_dirs is None and os.name == "nt":
        clipboard_dirs = [value for key in ("TEMP", "TMP")
                          if (value := os.environ.get(key))]
    clipboard = []
    clipboard_roots = []
    for directory in sorted({Path(path) for path in clipboard_dirs}, key=str):
        if not directory.is_dir():
            continue
        clipboard_roots.append(str(directory))
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as error:
            errors.append({"path": str(directory), "reason": type(error).__name__})
            continue
        for path in entries:
            if not fnmatch.fnmatch(path.name, "codex-clipboard-*.png"):
                continue
            try:
                info = path.lstat()
            except OSError as error:
                errors.append({"path": str(path), "reason": type(error).__name__})
                continue
            if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                clipboard.append((path, info))
    grouped["clipboard"] = {"roots": clipboard_roots, "files": clipboard,
                            "class": "input_cache"}

    rows = []
    for kind in sorted(grouped):
        group = grouped[kind]
        if not group["files"]:
            continue
        ages = sorted(max(0.0, (now - info.st_mtime) / 86400)
                      for _path, info in group["files"])
        rows.append({
            "kind": kind,
            "paths": sorted(group["roots"]),
            "count": len(group["files"]),
            "bytes": sum(info.st_size for _path, info in group["files"]),
            "observed_age_days": {
                "min": round(min(ages), 3), "max": round(max(ages), 3),
                "median": round(statistics.median(ages), 3),
            },
            "policy": "unknown",
            "attribution": "unknown",
            "content_class": group["class"],
        })
    return {"rows": rows, "errors": sorted(errors, key=lambda row: row["path"])}


def _table_keys(value):
    return sorted(str(key) for key in value) if isinstance(value, dict) else []


def codex_config_summary(root):
    """Read config.toml but expose only table/key/server names, never values."""
    path = Path(root) / "config.toml"
    try:
        with roio._ro_open(path, "rb") as source:
            data = tomllib.load(source)
    except FileNotFoundError:
        return {"mcp_configs": [], "hooks": [], "plugins": [],
                "web_search": [], "errors": []}
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        return {"mcp_configs": [], "hooks": [], "plugins": [],
                "web_search": [],
                "errors": [{"path": str(path), "reason": type(error).__name__}]}

    configs = []
    servers = data.get("mcp_servers") if isinstance(data.get("mcp_servers"), dict) else {}
    for name in sorted(servers):
        config = servers[name] if isinstance(servers[name], dict) else {}
        env = config.get("env") if isinstance(config.get("env"), dict) else {}
        configs.append({
            "server": str(name), "scope": "codex", "project": None,
            "command": None, "args": [], "type": None, "url": None,
            "env_keys": sorted(str(key) for key in env), "source_file": str(path),
            "config_keys": sorted(str(key) for key in config),
        })
    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    web_search = ["web.search"] if "search" in web else []
    if "web_search" in data:
        web_search.append("web_search")
    return {
        "mcp_configs": configs,
        "hooks": _table_keys(data.get("hooks")),
        "plugins": _table_keys(data.get("plugins")),
        "web_search": sorted(set(web_search)),
        "errors": [],
    }

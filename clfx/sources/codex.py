"""Codex rollout JSONL read-only source."""
import hashlib
import json
import os
from pathlib import Path
import tomllib

from clfx import roio
from clfx.sources.claude import RawRecord
from clfx.sources.markers import flag_marker


class CodexSource:
    agent = "codex"

    def __init__(self, root=None, on_file=None):
        self.root = Path(root or os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
        self._on_file = on_file
        self.parse_errors = []
        self.config_errors = []
        self.acquisition_errors = []
        self.schema_warnings = []
        self.capability_warnings = []
        self.orchestration_records = []
        self.sqlite_warnings = []
        self.sqlite_support = {}
        self.sqlite_root = self._sqlite_root()

    def _sqlite_root(self):
        config = self.root / "config.toml"
        try:
            with roio._ro_open(config, "rb") as f:
                value = tomllib.load(f).get("sqlite_home")
            if isinstance(value, str) and value:
                return Path(value).expanduser()
        except FileNotFoundError:
            pass
        except OSError as e:
            self.config_errors.append({"file": str(config), "error": type(e).__name__})
        except (ValueError, TypeError, UnicodeError) as e:
            self.config_errors.append({"file": str(config), "error": type(e).__name__})
        return Path(os.environ.get("CODEX_SQLITE_HOME") or self.root).expanduser()

    def _iter_jsonl(self, path: Path, sha_out=None):
        try:
            f = roio._ro_open(path, "rb")
        except OSError as e:
            self.acquisition_errors.append({"file": str(path),
                                            "error": type(e).__name__})
            return
        if self._on_file:
            self._on_file(str(path))
        h = hashlib.sha256()
        with f:
            for i, raw in enumerate(f, start=1):
                h.update(raw)
                if not raw.strip():
                    continue
                try:
                    obj = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    self.parse_errors.append({"file": str(path), "line": i,
                                              "error": type(e).__name__})
                    continue
                yield RawRecord(str(path), i, obj)
        if sha_out is not None:
            sha_out["sha"] = h.hexdigest()

    def history_records(self):
        return iter(())

    def transcript_records(self):
        for path in self.jsonl_files():
            yield from self._iter_jsonl(path)

    def jsonl_files(self):
        sessions = self.root / "sessions"
        if not sessions.is_dir():
            error = {"file": str(sessions), "error": "FileNotFoundError"}
            if error not in self.acquisition_errors:
                self.acquisition_errors.append(error)
            return []
        return sorted(sessions.rglob("rollout-*.jsonl"))

    def transcript_files(self):
        return self.jsonl_files()

    def remote_control_markers(self):
        """app-server-daemon/settings.json 의 remoteControlEnabled — **호스트 단위** 스위치.

        켜져 있어도 채널이 살아 있다는 뜻은 아니고, 어느 계정이 썼는지도 말하지 않는다.
        파일은 데몬이 처음 뜰 때 만들어지므로 부재는 판정 불가(unknown)다."""
        return [flag_marker(
            "codex_remote_control_setting", self.agent,
            self.root / "app-server-daemon" / "settings.json",
            ("remoteControlEnabled",),
            "호스트 단위 스위치다. true 는 '이 머신에서 원격제어가 켜져 있다'까지고, "
            "채널이 실제로 연결돼 있다는 뜻도 누가 썼다는 뜻도 아니다. 파일은 "
            "app-server 데몬이 처음 실행될 때 생성된다.")]

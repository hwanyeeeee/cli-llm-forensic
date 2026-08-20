"""Codex rollout records -> Event, selected by structure rather than cli_version."""
import json
import re
import shlex
from urllib.parse import unquote, urlparse

from clfx.event import Event, Source, norm_ts


_PREVIEW_MAX = 4000
_IMAGE_PLACEHOLDER = re.compile(r"^\s*\[Image #[1-9]\d*\]\s*$")
_PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
_ITEM_TYPES = {"Reasoning", "CommandExecution", "AgentMessage", "Extension",
               "UserMessage", "SubAgentActivity", "FileChange", "CollabAgentToolCall",
               "ContextCompaction", "ImageView"}
_ENVELOPES_WITHOUT_EVENTS = {"turn_context", "inter_agent_communication_metadata",
                             "world_state", "compacted"}
_RESPONSE_WITHOUT_EVENTS = {"message", "reasoning", "web_search_call", "agent_message",
                            "tool_search_call", "tool_search_output", "ghost_snapshot"}
_EVENTS_WITHOUT_EVENTS = {"token_count", "task_started", "agent_reasoning",
                          "thread_goal_updated", "thread_rolled_back", "error"}


def _clip(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = _json_text(value)
    return value if len(value) <= _PREVIEW_MAX else value[:_PREVIEW_MAX] + "…"


def _json_text(value):
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (_text(part) for part in value)))
    if isinstance(value, dict):
        return _text(value.get("text") or value.get("message") or value.get("content"))
    return ""


def _file_url(value):
    if not isinstance(value, str) or not value.startswith("file:"):
        return value or ""
    parsed = urlparse(value)
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc != "localhost":
        path = f"//{parsed.netloc}{path}"
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return path


def _without_placeholders(text, elements):
    if not isinstance(text, str) or not isinstance(elements, list):
        return text
    raw = text.encode("utf-8")
    ranges = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        byte_range = element.get("byte_range") or {}
        start, end = byte_range.get("start"), byte_range.get("end")
        placeholder = element.get("placeholder")
        if (isinstance(start, int) and isinstance(end, int) and isinstance(placeholder, str)
                and 0 <= start <= end <= len(raw)
                and raw[start:end] == placeholder.encode("utf-8")):
            ranges.append((start, end))
    cleaned = bytearray(raw)
    for start, end in sorted(ranges, reverse=True):
        del cleaned[start:end]
    return cleaned.decode("utf-8", errors="replace").strip()


def _command(value):
    if isinstance(value, list):
        return shlex.join(str(arg) for arg in value)
    return _clip(value)


def _identity(payload):
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("call_id") or payload.get("id") or "")


class CodexFileParser:
    """Single-pass file accumulator. Only call/output state is retained."""

    def __init__(self, source):
        self.source = source
        self.events = []
        self.by_id = {}
        self.pending = {}
        self.unsupported = {}
        self.capabilities = set()
        self.file = ""
        self.session = ""
        self.cli_version = ""
        self.meta_line = 0

    def feed(self, rec):
        if not self.file:
            self.file = rec.file
        obj = rec.obj
        if not isinstance(obj, dict):
            self._warn(rec, "envelope", type(obj).__name__, obj)
            return
        envelope = obj.get("type")
        if "ordinal" in obj:
            self.capabilities.add("ordinal")
        if envelope == "session_meta":
            payload = obj.get("payload") or {}
            if not isinstance(payload, dict):
                self._warn(rec, "session_meta", type(payload).__name__, payload)
                return
            self.session = str(payload.get("id") or self.session)
            self.cli_version = str(payload.get("cli_version") or "")
            self.meta_line = rec.line
        elif envelope == "event_msg":
            self._event_msg(rec, obj)
        elif envelope == "response_item":
            self._response_item(rec, obj)
        elif envelope in _ENVELOPES_WITHOUT_EVENTS:
            return
        else:
            self._warn(rec, "envelope", str(envelope), obj)

    def finish(self):
        for event in self.events:
            if not event.session:
                event.session = self.session
        for row in self.unsupported.values():
            self.source.schema_warnings.append(row)
        self._check_version()
        return self.events

    def _warn(self, rec, layer, name, raw):
        keys = sorted(str(key) for key in raw) if isinstance(raw, dict) else []
        key = (rec.file, layer, name, tuple(keys))
        if key in self.unsupported:
            self.unsupported[key]["count"] += 1
            return
        self.unsupported[key] = {"file": rec.file, "line": rec.line, "layer": layer,
                                 "name": name, "keyset": keys, "count": 1}

    def _meta(self, rec, payload, **extra):
        ident = _identity(payload)
        meta = {"id": ident} if ident else {}
        if "ordinal" in rec.obj:
            meta["ordinal"] = rec.obj["ordinal"]
        meta.update({key: value for key, value in extra.items() if value is not None})
        return meta

    def _emit(self, rec, actor, action, target="", preview="", payload=None,
              merge=False, **meta):
        payload = payload if isinstance(payload, dict) else {}
        event_meta = self._meta(rec, payload, **meta)
        ident = event_meta.get("id", "")
        event = Event(norm_ts(rec.obj.get("timestamp")), "codex", self.session, actor,
                      action, _clip(target), _clip(preview), Source(rec.file, rec.line),
                      meta=event_meta)
        if merge and ident and ident in self.by_id:
            current = self.by_id[ident]
            if event.target:
                current.target = event.target
            if event.preview:
                current.preview = event.preview
            current.meta.update(event.meta)
            return current
        self.events.append(event)
        if merge and ident:
            self.by_id[ident] = event
            self._apply_pending(event, self.pending.get(ident, {}))
        return event

    @staticmethod
    def _apply_pending(event, update):
        if update.get("preview"):
            if event.action == "write" and event.preview:
                event.meta["output"] = _clip(update["preview"])
            else:
                event.preview = _clip(update["preview"])
        event.meta.update(update.get("meta", {}))

    def _update(self, ident, preview=None, **meta):
        if not ident:
            return
        update = self.pending.setdefault(ident, {"meta": {}})
        if preview:
            update["preview"] = preview
        update["meta"].update({key: value for key, value in meta.items() if value is not None})
        event = self.by_id.get(ident)
        if event:
            self._apply_pending(event, update)

    def _event_msg(self, rec, obj):
        payload = obj.get("payload") or {}
        if not isinstance(payload, dict):
            self._warn(rec, "event_msg", type(payload).__name__, payload)
            return
        kind = payload.get("type")
        if kind == "item_completed":
            self.capabilities.add("item")
            self._item(rec, payload.get("item"))
        elif kind == "user_message":
            self.capabilities.add("legacy")
            self._legacy_user(rec, payload)
        elif kind == "agent_message":
            self.capabilities.add("legacy")
            self._emit(rec, "agent", "response", preview=_text(payload.get("message")),
                       payload=payload)
        elif kind == "exec_command_end":
            ident = _identity(payload)
            preview = payload.get("stdout") or payload.get("output") or payload.get("stderr")
            status = payload.get("status") or ("completed" if payload.get("exit_code") is not None else "unknown")
            if ident not in self.by_id:
                self._emit(rec, "agent", "bash", target=_command(payload.get("command")),
                           preview=preview, payload=payload, merge=True, status=status,
                           exit_code=payload.get("exit_code"))
            self._update(ident, preview, status=status, exit_code=payload.get("exit_code"))
        elif kind == "patch_apply_end":
            ident = _identity(payload)
            status = payload.get("status") or "completed"
            changes = payload.get("changes") if isinstance(payload.get("changes"), dict) else {}
            current = self.by_id.get(ident)
            if current and not current.target and changes:
                current.target = next(iter(changes))
            if not current and not changes:
                current = self._emit(rec, "agent", "write", target=payload.get("path") or "",
                                     preview=payload.get("stdout") or payload.get("stderr") or "",
                                     payload=payload, merge=True, status=status)
            for path, change in changes.items():
                if current and current.target == path:
                    continue
                change = change if isinstance(change, dict) else {}
                self._emit(rec, "agent", "write", path,
                           change.get("content") or change.get("unified_diff") or "",
                           payload=payload, status=status, change_type=change.get("type"))
            self._update(ident, payload.get("stdout") or payload.get("stderr"),
                         status=status, success=payload.get("success"))
        elif kind == "mcp_tool_call_end":
            invocation = payload.get("invocation") if isinstance(payload.get("invocation"), dict) else {}
            server = payload.get("server") or invocation.get("server") or ""
            tool = payload.get("tool") or payload.get("name") or invocation.get("tool") or ""
            target = f"mcp__{server}__{tool}" if server and tool else tool or server
            arguments = payload.get("arguments") if "arguments" in payload else invocation.get("arguments")
            preview = _json_text({key: value for key, value in (
                ("arguments", arguments), ("result", payload.get("result"))) if value is not None})
            self._emit(rec, "agent", "mcp", target, preview, payload=payload,
                       status=payload.get("status") or "completed")
        elif kind == "web_search_end":
            self._emit(rec, "agent", "search", payload.get("query") or "",
                       payload.get("result") or "", payload=payload,
                       status=payload.get("status") or "completed")
        elif kind in _EVENTS_WITHOUT_EVENTS:
            return
        else:
            self._warn(rec, "event_msg", str(kind), payload)

    def _legacy_user(self, rec, payload):
        message = _text(payload.get("message"))
        if message.strip() and not _IMAGE_PLACEHOLDER.match(message):
            self._emit(rec, "user", "prompt", preview=message, payload=payload)
        images = payload.get("local_images") or []
        images += payload.get("images") or []
        for number, image in enumerate(images, start=1):
            target = image if isinstance(image, str) else _text(image)
            self._emit(rec, "user", "paste", target or f"[Image #{number}]",
                       "<image:local>", payload=payload)

    def _response_item(self, rec, obj):
        payload = obj.get("payload") or {}
        if not isinstance(payload, dict):
            self._warn(rec, "response_item", type(payload).__name__, payload)
            return
        kind = payload.get("type")
        if kind == "function_call":
            self.capabilities.add("function_call")
            name = payload.get("name")
            if name not in {"exec_command", "shell_command", "run"}:
                self._warn(rec, "function_call.name", str(name), payload)
                return
            args = _object(payload.get("arguments"))
            target = args.get("cmd") or args.get("command") or args.get("script") or ""
            self._emit(rec, "agent", "bash", target=target, payload=payload, merge=True,
                       status=payload.get("status") or "unknown")
        elif kind == "function_call_output":
            self._update(_identity(payload), _text(payload.get("output")), status="completed")
        elif kind == "custom_tool_call":
            self.capabilities.add("custom_tool_call")
            name = payload.get("name")
            raw_input = payload.get("input") or ""
            if name == "exec":
                self._emit(rec, "agent", "bash", target=_json_text(raw_input), payload=payload,
                           merge=True, status=payload.get("status") or "unknown")
            elif name == "apply_patch":
                text = _json_text(raw_input)
                match = _PATCH_PATH.search(text)
                self._emit(rec, "agent", "write", target=match.group(1) if match else "",
                           preview=text, payload=payload, merge=True,
                           status=payload.get("status") or "unknown")
            else:
                self._warn(rec, "custom_tool_call.name", str(name), payload)
        elif kind == "custom_tool_call_output":
            self._update(_identity(payload), _text(payload.get("output")), status="completed")
        elif kind in _RESPONSE_WITHOUT_EVENTS:
            return
        else:
            self._warn(rec, "response_item", str(kind), payload)

    def _item(self, rec, item):
        if not isinstance(item, dict):
            self._warn(rec, "item", type(item).__name__, item)
            return
        kind = item.get("type")
        if kind not in _ITEM_TYPES:
            self._warn(rec, "item", str(kind), item)
            return
        if kind in {"Reasoning", "ContextCompaction"}:
            return
        if kind == "UserMessage":
            self._item_user(rec, item)
        elif kind == "AgentMessage":
            self._emit(rec, "agent", "response", preview=_text(item), payload=item)
        elif kind == "CommandExecution":
            meta = {"status": item.get("status") or "unknown",
                    "cwd": _file_url(item.get("cwd")), "exit_code": item.get("exit_code")}
            preview = item.get("aggregated_output") or item.get("output") or ""
            self._emit(rec, "agent", "bash", _command(item.get("command")), preview,
                       payload=item, merge=True, **meta)
        elif kind == "FileChange":
            changes = item.get("changes")
            if not isinstance(changes, dict):
                self._warn(rec, "FileChange.changes", type(changes).__name__, item)
                return
            for path, change in changes.items():
                change = change if isinstance(change, dict) else {}
                preview = change.get("content") or change.get("unified_diff") or ""
                self._emit(rec, "agent", "write", path, preview, payload=item,
                           status=item.get("status") or "unknown",
                           change_type=change.get("type"), move_path=change.get("move_path"))
        elif kind == "Extension":
            extension = item.get("kind")
            if extension != "web.search":
                self._warn(rec, "extension.kind", str(extension), item)
                return
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            queries = action.get("queries") if isinstance(action.get("queries"), list) else []
            query = (item.get("query") or action.get("query") or
                     "\n".join(str(value) for value in queries) or
                     _object(item.get("value")).get("query") or "")
            self._emit(rec, "agent", "search", query, item.get("result") or "",
                       payload=item, status=item.get("status") or "completed")
        elif kind in {"SubAgentActivity", "CollabAgentToolCall"}:
            target = (item.get("agent_thread_id") or item.get("agent_id") or
                      item.get("tool") or item.get("name") or "")
            self._emit(rec, "agent", "spawn", target, _text(item.get("message")),
                       payload=item, status=item.get("status"))
        elif kind == "ImageView":
            self._emit(rec, "agent", "read", item.get("path") or item.get("image_path") or "",
                       payload=item, status=item.get("status") or "completed")

    def _item_user(self, rec, item):
        content = item.get("content")
        content = content if isinstance(content, list) else [content]
        image_number = 0
        for part in content:
            if isinstance(part, str):
                part = {"type": "text", "text": part}
            if not isinstance(part, dict):
                continue
            kind = part.get("type")
            if kind == "text":
                text = _without_placeholders(_text(part.get("text")),
                                             part.get("text_elements"))
                if text.strip() and not _IMAGE_PLACEHOLDER.match(text):
                    self._emit(rec, "user", "prompt", preview=text, payload=item)
            elif kind == "local_image":
                image_number += 1
                target = part.get("path") or part.get("url") or f"[Image #{image_number}]"
                self._emit(rec, "user", "paste", target, "<image:local>", payload=item)
            else:
                self._warn(rec, "UserMessage.content", str(kind), part)

    def _check_version(self):
        if not self.cli_version:
            return
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", self.cli_version)
        if not match:
            return
        # Version never selects a parser. It only diagnoses disagreement with observed structure.
        expected = "item" if tuple(map(int, match.groups())) >= (0, 147, 0) else "legacy"
        observed = {cap for cap in self.capabilities if cap in {"item", "legacy", "ordinal"}}
        mismatch = (expected == "legacy" and bool(observed & {"item", "ordinal"})) or (
            expected == "item" and (("item" not in observed and "legacy" in observed)
                                    or ("item" in observed and "ordinal" not in observed)))
        if mismatch:
            self.source.capability_warnings.append({
                "file": self.file,
                "line": self.meta_line,
                "cli_version": self.cli_version,
                "expected": expected,
                "capabilities": sorted(observed),
            })

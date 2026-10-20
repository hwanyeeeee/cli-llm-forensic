"""10단계 — Codex 정확도 정량 측정 (신청서 목표 ⑤).

`docs/validation/정확도-검증-시나리오.md`의 3시나리오(주체 식별·접근 파일 판정·MCP 호출 탐지)를
Codex 기록 형식으로 확장한다. 정답 라벨을 가진 합성 rollout을 만들고, 도구가 낸 Event와
`(source.file, source.line)`으로 1:1 비교한다.

- 실데이터 복사 없음. 모든 값은 합성이고 민감값(경로·토큰·사람 이름)이 없다.
- 결정적: 난수 없음. 같은 입력 → 같은 표.
- era 구성은 **legacy 50 : item 50(균형)**. 실측 분포는 legacy 323 : item 21(≒94:6)이지만
  그 비율이면 item era 표본이 6건뿐이라 era별 정확도를 따로 낼 수 없다(회수율 착시).
  두 era 각각의 정확도를 분리 집계하려고 균형 구성을 택했다 — 수치도 era별로 나눠 보고한다.
"""
import json
from pathlib import Path

from clfx.analyze.mcp import _split_target, mcp_usage_from_events
from clfx.parser import parse_source
from clfx.sources import source_for

MCP_SERVERS = ("notion", "playwright", "ghidra", "drive", "slack", "sqlitebrowser")
MCP_TOOLS = ("search", "fetch", "create", "list", "update",
             "delete", "append", "move", "export", "describe")


def _ts(n):
    return f"2026-08-21T05:{n // 60:02d}:{n % 60:02d}Z"


class Corpus:
    """합성 rollout 1개. rows[0]=session_meta(라벨 없음), 이후 줄마다 정답 라벨을 붙인다.

    줄 번호(1-based)가 그대로 Event.source.line이 되므로 라벨 키로 쓴다.
    한 레코드가 정확히 한 Event를 내도록 구성해 (file, line)이 유일 키가 되게 한다."""

    def __init__(self, era, session):
        self.era = era
        version = "0.44.0" if era == "legacy" else "0.147.0"
        meta = {"timestamp": _ts(0), "type": "session_meta",
                "payload": {"id": session, "cli_version": version,
                            "originator": "codex-tui"}}
        if era == "item":            # ordinal은 item era 표지 — legacy에 달면 capability_mismatch
            meta["ordinal"] = 1
        self.rows = [meta]
        self.truth = {}
        self.clock = 0

    def _stamp(self):
        self.clock += 1
        return _ts(self.clock)

    def legacy_event(self, payload, **label):
        self._add({"timestamp": self._stamp(), "type": "event_msg", "payload": payload}, label)

    def legacy_response(self, payload, **label):
        self._add({"timestamp": self._stamp(), "type": "response_item", "payload": payload}, label)

    def item(self, item, **label):
        self._add({"timestamp": self._stamp(), "type": "event_msg", "ordinal": self.clock + 1,
                   "payload": {"type": "item_completed", "turn_id": "turn-1",
                               "thread_id": "thread-1", "item": item}}, label)

    def _add(self, row, label):
        self.rows.append(row)
        if label:
            self.truth[len(self.rows)] = {"era": self.era, **label}

    def write(self, root, name):
        path = root / "sessions" / "2026" / "08" / "21" / f"rollout-{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in self.rows),
                        encoding="utf-8")
        return {(str(path), line): label for line, label in self.truth.items()}


def _parse(root):
    """도구 실행 진입점. 여기서 나온 Event만 채점한다 — 추가 읽기·재집계 없음."""
    src = source_for(str(root))
    events = list(parse_source(src))
    assert not src.schema_warnings, src.schema_warnings          # fixture가 스키마에 맞는지
    assert not src.capability_warnings, src.capability_warnings  # era 표기와 구조가 일치하는지
    return events, src


# --------------------------------------------------------------------------
# 시나리오 1 — 주체 식별 (100건)
# --------------------------------------------------------------------------

def _actor_corpus(era, session, disk_dir):
    """user 20 / agent 30 = 50건. 각 era 동일 구성."""
    c = Corpus(era, session)
    tag = era[0]
    for i in range(13):
        text = f"synthetic prompt {tag}{i}"
        if era == "legacy":
            c.legacy_event({"type": "user_message", "message": text},
                           actor="user", action="prompt")
        else:
            c.item({"type": "UserMessage", "id": f"{tag}-um-{i}",
                    "content": [{"type": "text", "text": text}]},
                   actor="user", action="prompt")
    for i in range(5):
        image = str(disk_dir / f"{era}-paste-{i}.png")
        Path(image).write_bytes(b"synthetic-image")
        if era == "legacy":
            c.legacy_event({"type": "user_message", "message": "[Image #1]",
                            "local_images": [image]}, actor="user", action="paste")
        else:
            c.item({"type": "UserMessage", "id": f"{tag}-ui-{i}",
                    "content": [{"type": "local_image", "path": image}]},
                   actor="user", action="paste")
    for i in range(2):                     # source=user_shell → 사람이 직접 친 명령(실측 1건)
        command = ["/bin/bash", "-lc", f"printf shell-{i}"]
        if era == "legacy":
            c.legacy_event({"type": "exec_command_end", "call_id": f"{tag}-ushell-{i}",
                            "command": command, "exit_code": 0, "status": "completed",
                            "source": "user_shell"}, actor="user", action="bash")
        else:
            c.item({"type": "CommandExecution", "id": f"{tag}-ushell-{i}", "command": command,
                    "cwd": "file:///case", "source": "user_shell", "status": "completed",
                    "aggregated_output": "synthetic", "exit_code": 0},
                   actor="user", action="bash")
    for i in range(10):
        text = f"synthetic response {tag}{i}"
        if era == "legacy":
            c.legacy_event({"type": "agent_message", "message": text},
                           actor="agent", action="response")
        else:
            c.item({"type": "AgentMessage", "id": f"{tag}-am-{i}", "text": text},
                   actor="agent", action="response")
    for i in range(10):                    # unified_exec_startup → 5단계 정정 대상(왜곡 케이스)
        command = ["/bin/bash", "-lc", f"rtk gain --window {i}"]
        if era == "legacy":
            c.legacy_event({"type": "exec_command_end", "call_id": f"{tag}-acmd-{i}",
                            "command": command, "exit_code": 0, "status": "completed",
                            "source": "unified_exec_startup"},
                           actor="agent", action="bash", distortion="unified_exec_startup")
        else:
            c.item({"type": "CommandExecution", "id": f"{tag}-acmd-{i}", "command": command,
                    "cwd": "file:///case", "source": "unified_exec_startup",
                    "status": "completed", "aggregated_output": "synthetic", "exit_code": 0},
                   actor="agent", action="bash", distortion="unified_exec_startup")
    for i in range(5):                     # 디스크에도 만든다 → 소유자만 보면 사람으로 오인
        path = str(disk_dir / f"{era}-agent-write-{i}.txt")
        Path(path).write_text("synthetic", encoding="utf-8")
        change = {"type": "add", "content": "synthetic"}
        if era == "legacy":
            c.legacy_event({"type": "patch_apply_end", "call_id": f"{tag}-patch-{i}",
                            "status": "completed", "changes": {path: change}},
                           actor="agent", action="write", distortion="disk_owner")
        else:
            c.item({"type": "FileChange", "id": f"{tag}-fc-{i}", "status": "completed",
                    "changes": {path: change}},
                   actor="agent", action="write", distortion="disk_owner")
    for i in range(5):
        path = str(disk_dir / f"{era}-view-{i}.png")
        Path(path).write_bytes(b"synthetic-image")
        if era == "legacy":
            c.legacy_response({"type": "function_call", "name": "view_image",
                               "call_id": f"{tag}-view-{i}", "status": "completed",
                               "arguments": json.dumps({"path": path})},
                              actor="agent", action="read")
        else:
            c.item({"type": "ImageView", "id": f"{tag}-iv-{i}", "path": path},
                   actor="agent", action="read")
    return c


def _actor_dataset(tmp_path):
    root = tmp_path / "actor" / ".codex"
    disk = tmp_path / "actor" / "disk"
    disk.mkdir(parents=True)
    truth = {}
    for era, session in (("legacy", "acc-actor-legacy"), ("item", "acc-actor-item")):
        truth.update(_actor_corpus(era, session, disk).write(root, f"actor-{era}"))
    return root, truth


def score_actor(tmp_path):
    root, truth = _actor_dataset(tmp_path)
    events, _ = _parse(root)
    by_line = {}
    for event in events:
        by_line.setdefault((event.source.file, event.source.line), []).append(event)

    hits, misses, confusion = 0, [], {}
    per_era = {"legacy": [0, 0], "item": [0, 0]}
    distortion = {"unified_exec_startup": [0, 0], "disk_owner": [0, 0]}
    for key, label in truth.items():
        found = by_line.get(key, [])
        actual = found[0].actor if len(found) == 1 else f"<{len(found)} events>"
        confusion[(label["actor"], actual)] = confusion.get((label["actor"], actual), 0) + 1
        per_era[label["era"]][1] += 1
        bucket = distortion.get(label.get("distortion"))
        if bucket is not None:
            bucket[1] += 1
        if actual == label["actor"]:
            hits += 1
            per_era[label["era"]][0] += 1
            if bucket is not None:
                bucket[0] += 1
        else:
            misses.append({"key": key, "expected": label["actor"], "actual": actual,
                           "action": label["action"], "era": label["era"]})
    extra = sorted(k for k in by_line if k not in truth)
    return {"total": len(truth), "hits": hits, "misses": misses, "confusion": confusion,
            "per_era": per_era, "distortion": distortion, "unlabelled_events": extra}


def test_actor_identification_accuracy():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = score_actor(Path(tmp))
    assert result["total"] == 100
    assert result["unlabelled_events"] == []          # 과계수 0 — 라벨 없는 Event가 없다
    assert result["misses"] == []
    assert result["hits"] == 100
    assert result["per_era"] == {"legacy": [50, 50], "item": [50, 50]}
    assert result["distortion"]["unified_exec_startup"] == [20, 20]
    assert result["distortion"]["disk_owner"] == [10, 10]
    assert result["confusion"] == {("user", "user"): 40, ("agent", "agent"): 60}


def test_paired_call_and_end_are_one_event_not_two():
    """과계수 방지: function_call(exec_command) + exec_command_end가 call_id로 묶이면 Event 1개다.
    두 레코드를 각각 세면 명령 실행 건수가 2배로 부풀어 보고서가 틀린다."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / ".codex"
        corpus = Corpus("legacy", "acc-merge")
        for i in range(3):
            corpus.legacy_response({"type": "function_call", "name": "exec_command",
                                    "call_id": f"pair-{i}", "status": "completed",
                                    "arguments": json.dumps({"cmd": f"printf pair-{i}"})})
            corpus.legacy_event({"type": "exec_command_end", "call_id": f"pair-{i}",
                                 "command": ["/bin/bash", "-lc", f"printf pair-{i}"],
                                 "exit_code": 0, "status": "completed",
                                 "source": "unified_exec_startup"})
        corpus.write(root, "merge")
        events, _ = _parse(root)

    bash = [e for e in events if e.action == "bash"]
    assert len(bash) == 3                                   # 6 레코드 → 3 Event
    assert {e.actor for e in bash} == {"agent"}
    assert {e.meta["source"] for e in bash} == {"unified_exec_startup"}


# --------------------------------------------------------------------------
# 시나리오 2 — 접근 파일 판정 (100건)
# --------------------------------------------------------------------------

def _access_dataset(tmp_path):
    """접근 70(write 40 · read 30) + decoy 30 = 100. 부속으로 shell redirect 10건."""
    root = tmp_path / "access" / ".codex"
    disk = tmp_path / "access" / "disk"
    disk.mkdir(parents=True)
    truth, decoys, redirects = {}, set(), {}

    for era, session in (("legacy", "acc-file-legacy"), ("item", "acc-file-item")):
        c = Corpus(era, session)
        tag = era[0]
        for i in range(20):
            path = str(disk / f"{era}-write-{i}.txt")
            Path(path).write_text("synthetic", encoding="utf-8")
            change = {"type": "add", "content": "synthetic"}
            if era == "legacy":
                c.legacy_event({"type": "patch_apply_end", "call_id": f"{tag}-w-{i}",
                                "status": "completed", "changes": {path: change}},
                               target=path, action="write")
            else:
                c.item({"type": "FileChange", "id": f"{tag}-w-{i}", "status": "completed",
                        "changes": {path: change}}, target=path, action="write")
        for i in range(15):
            path = str(disk / f"{era}-read-{i}.png")
            Path(path).write_bytes(b"synthetic-image")
            if era == "legacy":
                c.legacy_response({"type": "function_call", "name": "view_image",
                                   "call_id": f"{tag}-r-{i}", "status": "completed",
                                   "arguments": json.dumps({"path": path})},
                                  target=path, action="read")
            else:
                c.item({"type": "ImageView", "id": f"{tag}-r-{i}", "path": path},
                       target=path, action="read")
        for i in range(5):     # 부속: shell redirect — FileChange에 안 잡히는 구조적 비포착(§3-6)
            path = str(disk / f"{era}-redirect-{i}.log")
            command = ["/bin/bash", "-lc", f"printf synthetic > {path}"]
            if era == "legacy":
                c.legacy_event({"type": "exec_command_end", "call_id": f"{tag}-x-{i}",
                                "command": command, "exit_code": 0, "status": "completed",
                                "source": "unified_exec_startup"})
            else:
                c.item({"type": "CommandExecution", "id": f"{tag}-x-{i}", "command": command,
                        "cwd": "file:///case", "source": "unified_exec_startup",
                        "status": "completed", "aggregated_output": "", "exit_code": 0})
            redirects[path] = era
        truth.update(c.write(root, f"file-{era}"))

    for i in range(30):        # transcript에 전혀 등장하지 않는 디스크 파일 → 잡으면 오탐
        path = disk / f"decoy-{i}.txt"
        path.write_text("synthetic", encoding="utf-8")
        decoys.add(str(path))
    return root, truth, decoys, redirects


def score_access(tmp_path):
    root, truth, decoys, redirects = _access_dataset(tmp_path)
    events, _ = _parse(root)

    expected = {(label["target"], label["action"]) for label in truth.values()}
    reported = {(e.target, e.action) for e in events if e.action in {"read", "write"}}
    missing = sorted(expected - reported)
    spurious = sorted(reported - expected)
    false_positive_decoys = sorted(t for t, _ in reported if t in decoys)

    per_era = {"legacy": [0, 0], "item": [0, 0]}
    for label in truth.values():
        per_era[label["era"]][1] += 1
        if (label["target"], label["action"]) in reported:
            per_era[label["era"]][0] += 1

    flagged = {e.meta["write_target"]: e.meta.get("confidence")
               for e in events if "write_target" in e.meta}
    return {"expected": len(expected), "decoys": len(decoys),
            "missing": missing, "spurious": spurious,
            "false_positive_decoys": false_positive_decoys, "per_era": per_era,
            "redirect_total": len(redirects),
            "redirect_flagged": sorted(p for p in redirects if p in flagged),
            "redirect_as_write_event": sorted(p for p in redirects
                                              if (p, "write") in reported),
            "redirect_confidences": sorted({flagged[p] for p in redirects if p in flagged})}


def test_file_access_accuracy():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = score_access(Path(tmp))
    assert result["expected"] == 70 and result["decoys"] == 30
    assert result["missing"] == []                   # 누락 0 (무손실 제약)
    assert result["spurious"] == []                  # 오탐 0
    assert result["false_positive_decoys"] == []
    assert result["per_era"] == {"legacy": [35, 35], "item": [35, 35]}
    # 부속 — shell redirect 10건: write Event로 주장하지 않되(직접 증거 없음)
    # write_target + confidence=low 로 후보를 남긴다. 이게 §3-6 구조적 비포착의 하한이다.
    assert result["redirect_total"] == 10
    assert len(result["redirect_flagged"]) == 10
    assert result["redirect_as_write_event"] == []
    assert result["redirect_confidences"] == ["low"]


# --------------------------------------------------------------------------
# 시나리오 3 — MCP 호출 탐지 (100건)
# --------------------------------------------------------------------------

def _mcp_dataset(tmp_path):
    """MCP 60(legacy mcp_tool_call_end) + 비-MCP 40(두 era 혼합) = 100.

    item era(0.147)에는 MCP 레코드 형식 자체가 없다 — 실측 표본에서도 MCP 사용 0,
    Extension은 kind=web.search 162건뿐이다. 그래서 양성 60건은 legacy 형식으로만 만들고,
    오탐 쪽(비-MCP 40건)에 item era를 넣어 두 era를 모두 태운다."""
    root = tmp_path / "mcp" / ".codex"
    legacy = Corpus("legacy", "acc-mcp-legacy")
    item = Corpus("item", "acc-mcp-item")
    truth = {}

    n = 0
    for server in MCP_SERVERS:
        for tool in MCP_TOOLS:
            legacy.legacy_event({"type": "mcp_tool_call_end", "call_id": f"mcp-{n}",
                                 "server": server, "tool": tool, "status": "completed",
                                 "arguments": {"query": "synthetic"},
                                 "result": "synthetic result"},
                                mcp=True, server=server, tool=tool)
            n += 1
    for i in range(10):        # 일반 명령 — MCP로 세면 오탐
        legacy.legacy_event({"type": "exec_command_end", "call_id": f"legacy-cmd-{i}",
                             "command": ["/bin/bash", "-lc", f"printf plain-{i}"],
                             "exit_code": 0, "status": "completed",
                             "source": "unified_exec_startup"}, mcp=False)
    for i in range(5):
        legacy.legacy_event({"type": "agent_message", "message": f"mcp__looking__text {i}"},
                            mcp=False)
    for i in range(10):        # web.search는 MCP가 아니다 — 함정
        item.item({"type": "Extension", "id": f"ws-{i}", "kind": "web.search",
                   "status": "completed", "action": {"queries": [f"synthetic query {i}"]},
                   "result": "synthetic result"}, mcp=False)
    for i in range(10):
        item.item({"type": "CommandExecution", "id": f"item-cmd-{i}",
                   "command": ["/bin/bash", "-lc", f"printf plain-{i}"], "cwd": "file:///case",
                   "source": "unified_exec_startup", "status": "completed",
                   "aggregated_output": "synthetic", "exit_code": 0}, mcp=False)
    for i in range(5):
        path = f"/case/item-mcp-{i}.txt"
        item.item({"type": "FileChange", "id": f"item-fc-{i}", "status": "completed",
                   "changes": {path: {"type": "add", "content": "synthetic"}}}, mcp=False)

    truth.update(legacy.write(root, "mcp-legacy"))
    truth.update(item.write(root, "mcp-item"))
    return root, truth


def score_mcp(tmp_path):
    root, truth = _mcp_dataset(tmp_path)
    events, _ = _parse(root)
    by_line = {(e.source.file, e.source.line): e for e in events}

    detected_misses, false_positives, identity_misses = [], [], []
    positives = negatives = 0
    for key, label in truth.items():
        event = by_line.get(key)
        is_mcp = event is not None and event.action == "mcp"
        if label["mcp"]:
            positives += 1
            if not is_mcp:
                detected_misses.append(key)
                continue
            server, tool = _split_target(event.target)
            if (server, tool) != (label["server"], label["tool"]):
                identity_misses.append({"key": key, "expected": (label["server"], label["tool"]),
                                        "actual": (server, tool)})
        else:
            negatives += 1
            if is_mcp:
                false_positives.append({"key": key, "target": event.target})

    usage = mcp_usage_from_events(events)
    usage_pairs = {(row["server"], row["tool"]) for row in usage}
    expected_pairs = {(l["server"], l["tool"]) for l in truth.values() if l["mcp"]}
    return {"positives": positives, "negatives": negatives,
            "detected_misses": detected_misses, "false_positives": false_positives,
            "identity_misses": identity_misses,
            "usage_rows": len(usage), "usage_matches_truth": usage_pairs == expected_pairs,
            "usage_total_count": sum(row["count"] for row in usage)}


def test_mcp_detection_accuracy():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = score_mcp(Path(tmp))
    assert result["positives"] == 60 and result["negatives"] == 40
    assert result["detected_misses"] == []
    assert result["false_positives"] == []            # web.search 10건 포함해 오탐 0
    assert result["identity_misses"] == []
    assert result["usage_rows"] == 60 and result["usage_matches_truth"]
    assert result["usage_total_count"] == 60


# --------------------------------------------------------------------------
# 표 — 발표 패널 ③결과에 그대로 들어가는 수치. `pytest -s` 로 확인한다.
# --------------------------------------------------------------------------

def test_accuracy_report_table():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        actor = score_actor(base / "s1")
        access = score_access(base / "s2")
        mcp = score_mcp(base / "s3")

    def rate(hit, total):
        return f"{100.0 * hit / total:.1f}%"

    def era_rate(per_era, era):
        hit, total = per_era[era]
        return rate(hit, total)

    access_hit = access["expected"] - len(access["missing"])
    rows = [
        ("주체 식별", 100, rate(actor["hits"], actor["total"]),
         f"legacy {era_rate(actor['per_era'], 'legacy')} · "
         f"item {era_rate(actor['per_era'], 'item')} · "
         f"왜곡 {actor['distortion']['unified_exec_startup'][0] + actor['distortion']['disk_owner'][0]}/30"),
        ("접근 파일 판정", 100, rate(access_hit + access["decoys"] - len(access["spurious"]), 100),
         f"legacy {era_rate(access['per_era'], 'legacy')} · "
         f"item {era_rate(access['per_era'], 'item')} · "
         f"누락 {len(access['missing'])} · 오탐 {len(access['spurious'])} · "
         f"redirect 후보 {len(access['redirect_flagged'])}/{access['redirect_total']}"),
        ("MCP 호출 탐지", 100,
         rate(mcp["positives"] - len(mcp["detected_misses"])
              + mcp["negatives"] - len(mcp["false_positives"]), 100),
         f"누락 {len(mcp['detected_misses'])} · 오탐 {len(mcp['false_positives'])} · "
         f"server/tool {60 - len(mcp['identity_misses'])}/60"),
    ]
    print("\n시나리오            건수   정확도   비고")
    for name, count, accuracy, note in rows:
        print(f"{name:<16} {count:>5}   {accuracy:>6}   {note}")

    assert all(accuracy == "100.0%" for _, _, accuracy, _ in rows)

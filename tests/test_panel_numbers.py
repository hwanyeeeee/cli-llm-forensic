"""15단계 — 패널 수치 고정. A1은 인쇄되면 못 고친다.

패널·`docs/AgenTrace-종합-아티팩트-분석.md`에 실리는 수치를 코드·실데이터로 **재계산**해 단언한다.
발표 직전에 이 파일 하나만 돌리면 숫자가 아직 맞는지 확인된다.

두 부류를 다르게 다룬다.

- **합성 fixture 기반**(정확도 3×100건, 유출 시연 화면) → 값을 **정확히** 고정한다.
  입력이 저장소 안에 있으니 드리프트할 이유가 없다. 달라지면 그건 회귀다.
- **실데이터 의존**(코퍼스 건수·회수율) → 값을 고정하지 않는다. 우리가 Codex를 계속 쓰는 한
  숫자는 자란다. 대신 **산식과 방향**을 고정한다. 14단계에서 실제로 틀린 게 값이 아니라 산식이었다:
  `exec_command_end`를 `function_call`과 단순 합산해 분모를 부풀렸고, 그래서 쓰기 회수율이
  4배 낮게 나왔다. 그 종류의 오류가 다시 들어오면 여기서 걸린다.

실데이터가 없는 환경에서는 skip 하되 **조용히 통과시키지 않는다** — 경고로 사유를 남긴다
(`-q`에서도 warnings summary에 보인다).

> 실데이터 스캔이 있어 이 파일은 다른 테스트보다 느리다(수 초). 인쇄 전 점검용이다.
"""
import json
import os
import re
import warnings
from pathlib import Path

import pytest

from tests.test_accuracy_codex import score_access, score_actor, score_mcp

CODEX_HOME = Path.home() / ".codex"
CLAUDE_HOME = Path.home() / ".claude"
EXEC_NAMES = {"exec_command", "shell_command", "run"}

# iOS(S1·S2)는 2026-08-22 별도 세션에서 실측이 끝났다. 취득본은 저장소 밖(별도 프로젝트의
# 케이스 디렉터리)에 있고 여기로 복사하지 않는다 — 원본 무변경 원칙이고, 백업 이미지를 이 저장소에
# 끌고 들어올 이유가 없다. 그래서 게이트를 "취득본이 있느냐"가 아니라 **"인계 문서가 여섯 축을
# 실제로 채웠느냐"**로 옮겼다. 패널이 잘못 인쇄되는 경로는 파일의 부재가 아니라 문서의 빈칸이다.
IOS_ACQUISITION = Path(os.environ.get("CLFX_IOS_ACQUISITION",
                                      Path.home() / "cases" / "ios-remote-control"))
HANDOFF_DOC = Path(__file__).resolve().parents[1] / "docs" / "AgenTrace-아티팩트-인계문서.md"

# ①마커 위치 ②원격/로컬 판별자 ③결속축 ④폰에 지시 내용 ⑤자격증명 보호 수준 ⑥종료 후 존속
IOS_AXES = (
    ("①마커 위치", ("AppDomain-com.anthropic.claude", "AppDomain-com.openai.chat")),
    ("②원격/로컬 판별자", ("codex_chatgpt_ios_remote",)),
    ("③결속축", ("selectedEnvironment", "environment_id")),
    ("④폰에 지시 내용", ("전수 검색 0건",)),
    ("⑤자격증명 보호 수준", ("키체인", "인증 자격을 재사용",)),
    # ⑥은 표지를 짧게 잡는다. 주변 산문은 다시 쓰이지만("미측정 칸" → §7.2 한계) 이 어구는
    # 축 자체의 이름이라 살아남는다. 실제로 한 번 문구가 바뀌어 여기서 잡혔다.
    ("⑥종료 후 존속", ("종료 후 존속",)),                        # 미측정임을 명시했는지
)


def _require(path, what):
    if not path.is_dir():
        reason = (f"실데이터 없음: {path} — {what} 수치를 검증하지 못했다. "
                  f"패널 인쇄 전에는 실데이터가 있는 머신에서 반드시 다시 돌려라.")
        warnings.warn(reason, UserWarning)      # -q 에서도 warnings summary 에 뜬다
        pytest.skip(reason)


def _identity(payload):
    return str(payload.get("call_id") or payload.get("id") or payload.get("event_id") or "")


@pytest.fixture(scope="module")
def codex_corpus():
    """rollout 원본을 한 번만 훑어 회수율 산식의 입력을 만든다.

    call_id 는 파일 안에서만 유일하므로 (파일, id) 쌍으로 센다."""
    _require(CODEX_HOME, "Codex 코퍼스")
    files = sorted(CODEX_HOME.glob("sessions/**/rollout-*.jsonl"))
    if not files:
        _require(Path("/nonexistent"), "Codex rollout")
    out = {"files": len(files), "files_with_item": set(),
           "fc_exec": set(), "ctc_exec": set(), "exec_end": set(),
           "apply_patch": set(), "patch_end": set(),
           "item_command": 0, "item_filechange": 0}
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                # 프리필터 — 관심 레코드는 소수라 대부분의 줄에서 json 파싱을 건너뛴다.
                if not ("function_call" in line or "custom_tool_call" in line
                        or "_end" in line or "item_completed" in line):
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                payload = obj.get("payload")
                if not isinstance(payload, dict):
                    continue
                kind, envelope = payload.get("type"), obj.get("type")
                key = (str(path), _identity(payload))
                if envelope == "response_item":
                    if kind == "function_call" and payload.get("name") in EXEC_NAMES:
                        out["fc_exec"].add(key)
                    elif kind == "custom_tool_call":
                        if payload.get("name") == "exec":
                            out["ctc_exec"].add(key)
                        elif payload.get("name") == "apply_patch":
                            out["apply_patch"].add(key)
                elif envelope == "event_msg":
                    if kind == "exec_command_end":
                        out["exec_end"].add(key)
                    elif kind == "patch_apply_end":
                        out["patch_end"].add(key)
                    elif kind == "item_completed":
                        out["files_with_item"].add(str(path))
                        item = payload.get("item")
                        if isinstance(item, dict):
                            if item.get("type") == "CommandExecution":
                                out["item_command"] += 1
                            elif item.get("type") == "FileChange":
                                out["item_filechange"] += 1
    # 24단계: legacy 파일 한정 집합. 회수율 분모는 **이쪽**이다 — 전 코퍼스를 쓰면
    # item-era 파일이 같은 명령을 custom_tool_call(exec) 로도 적어 분자·분모 이중계상된다.
    for name in ("fc_exec", "ctc_exec", "exec_end", "apply_patch", "patch_end"):
        out["legacy_" + name] = {key for key in out[name]
                                 if key[0] not in out["files_with_item"]}
    return out


@pytest.fixture(scope="module")
def codex_events():
    """코퍼스를 Event 로 복원한 현재 상태. 동결값과 대조할 '현재값'의 출처."""
    _require(CODEX_HOME, "Codex 이벤트 복원")
    from clfx.parser import parse_source
    from clfx.sources import source_for
    source = source_for(str(CODEX_HOME))
    return list(parse_source(source)), source


@pytest.fixture(scope="module")
def claude_prompt_sources():
    _require(CLAUDE_HOME / "projects", "Claude promptSource 분포")
    counts, combos = {}, {}
    for path in (CLAUDE_HOME / "projects").rglob("*.jsonl"):
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if '"promptSource"' not in line:      # 프리필터
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                source = obj.get("promptSource")
                if source is None:
                    continue
                counts[source] = counts.get(source, 0) + 1
                origin = obj.get("origin")
                kind = origin.get("kind") if isinstance(origin, dict) else None
                combos[(source, kind)] = combos.get((source, kind), 0) + 1
    return counts, combos


# =========================================================================
# 합성 fixture 기반 — 정확히 고정한다
# =========================================================================

def test_panel_accuracy_numbers_are_exact(tmp_path):
    """패널 ③결과의 '정확도 3시나리오 100%'. 입력이 저장소 안에 있으니 흔들릴 이유가 없다."""
    actor = score_actor(tmp_path / "actor")
    access = score_access(tmp_path / "access")
    mcp = score_mcp(tmp_path / "mcp")

    assert (actor["total"], actor["hits"]) == (100, 100)
    assert actor["distortion"]["unified_exec_startup"] == [20, 20]
    assert actor["distortion"]["disk_owner"] == [10, 10]
    assert (access["expected"], access["decoys"]) == (70, 30)
    assert access["missing"] == [] and access["spurious"] == []
    assert (mcp["positives"], mcp["negatives"]) == (60, 40)
    assert mcp["detected_misses"] == [] and mcp["false_positives"] == []
    assert mcp["identity_misses"] == []


def test_panel_demo_screen_numbers_are_exact():
    """패널 ④ 시연 화면. 유출 데이터셋은 커밋돼 있으니 값이 확정이다."""
    from clfx.web.api import scan_to_engine, stats_payload
    repo = Path(__file__).resolve().parents[1]
    engine = scan_to_engine([str(repo / "tests/fixtures/leak-scenario/claude"),
                             str(repo / "tests/fixtures/leak-scenario/codex")])
    assert stats_payload(engine) == {"total": 19, "user": 7, "agent": 12,
                                     "unknown": 0, "actor_warnings": 0, "bypass": 2}


# =========================================================================
# 실데이터 의존 — 값이 아니라 산식과 방향을 고정한다
# =========================================================================

def test_exec_command_end_is_a_duplicate_not_a_separate_command(codex_corpus):
    """회수율 분모 오류의 진원지.

    `exec_command_end` 는 앞선 `function_call(exec_command)` 의 **결과**지 별개 명령이 아니다.
    call_id 가 완전히 겹치므로 둘을 더하면 분모가 부풀고 회수율이 낮게 나온다."""
    fc, end = codex_corpus["fc_exec"], codex_corpus["exec_end"]
    assert end, "exec_command_end 표본이 없어 중복 여부를 확인할 수 없다"
    assert end <= fc, f"function_call 과 짝이 없는 exec_command_end {len(end - fc)}건 — 산식 재검토"
    assert not (end & codex_corpus["ctc_exec"])      # ctc 와는 id 네임스페이스가 다르다


def test_apply_patch_and_patch_apply_end_overlap(codex_corpus):
    """쓰기 쪽도 같다. 완전포함은 아니지만 상당수가 겹친다 — 단순 합산 금지."""
    ap, pae = codex_corpus["apply_patch"], codex_corpus["patch_end"]
    assert ap and pae
    assert ap & pae, "겹침이 사라졌다면 두 레코드의 관계가 바뀐 것 — 산식을 다시 확인해라"


def test_recovery_rate_uses_deduplicated_denominators(codex_corpus):
    """회수율 산식 자체를 고정한다. 값은 코퍼스가 자라면 변하므로 고정하지 않는다.

    단순 합산은 분모를 부풀려 회수율을 **낮게** 만든다. 그 방향을 못박아 두면
    '쓰기 1.85%' 같은 과소 수치가 다시 실릴 때 여기서 걸린다."""
    corpus = codex_corpus
    legacy_cmd = corpus["fc_exec"] | corpus["ctc_exec"] | corpus["exec_end"]
    naive_cmd = len(corpus["fc_exec"]) + len(corpus["ctc_exec"]) + len(corpus["exec_end"])
    legacy_write = corpus["apply_patch"] | corpus["patch_end"]
    naive_write = len(corpus["apply_patch"]) + len(corpus["patch_end"])

    assert len(legacy_cmd) < naive_cmd, "명령 분모에서 중복이 제거되지 않았다"
    assert len(legacy_write) < naive_write, "쓰기 분모에서 중복이 제거되지 않았다"

    def rate(item, legacy):
        return item / (item + legacy)

    cmd_rate = rate(corpus["item_command"], len(legacy_cmd))
    write_rate = rate(corpus["item_filechange"], len(legacy_write))
    assert 0 < cmd_rate < 1 and 0 < write_rate < 1
    # 단순 합산본보다 dedup 본이 반드시 크다 — 과소보고 방향을 차단
    assert write_rate > rate(corpus["item_filechange"], naive_write)
    assert cmd_rate > rate(corpus["item_command"], naive_cmd)


def test_recovery_denominator_excludes_item_era_files(codex_corpus):
    """분모 **범위**를 못박는다. 두 문서가 11.5%(전 코퍼스) vs 12.9%(legacy 파일)로 갈렸다.

    전 코퍼스 분모가 틀린 이유는 취향이 아니라 실측이다: 늘어나는 분량이 **전부**
    item-era 파일의 `custom_tool_call(exec)` 이고, 그 파일들은 같은 명령을
    `item_completed CommandExecution` 으로도 적는다 — item 파서에 보이는 명령을
    '안 보이는 legacy' 칸에 넣는 셈이라 회수율이 낮게 나온다."""
    corpus = codex_corpus
    whole = corpus["fc_exec"] | corpus["ctc_exec"] | corpus["exec_end"]
    legacy = (corpus["legacy_fc_exec"] | corpus["legacy_ctc_exec"]
              | corpus["legacy_exec_end"])
    extra = whole - legacy
    assert extra, "item-era 파일이 legacy 형식을 하나도 안 낸다면 두 분모가 같아야 한다"
    # 늘어난 분량은 전부 custom_tool_call(exec) — fc·end 는 item 파일에서 안 나온다.
    assert extra <= corpus["ctc_exec"], "예상 밖 레코드가 분모에 섞였다 — 산식 재검토"
    item_files = {key[0] for key in extra}
    assert item_files <= corpus["files_with_item"]

    def rate(item, den):
        return item / (item + den)

    assert rate(corpus["item_command"], len(legacy)) > rate(corpus["item_command"], len(whole)), \
        "전 코퍼스 분모는 이중계상이라 회수율을 낮춘다 — 그 방향이 뒤집히면 산식이 바뀐 것"
    # 쓰기는 두 분모가 같아야 한다: item-era 파일은 legacy 형식 쓰기를 안 낸다.
    assert (corpus["apply_patch"] | corpus["patch_end"]) == (
        corpus["legacy_apply_patch"] | corpus["legacy_patch_end"])


def test_legacy_files_contain_no_item_records(codex_corpus):
    """패널이 쓰는 이진 속성: legacy 세션 파일에는 `item_completed` 가 **한 건도** 없다.

    비율이 아니라 0/1 이라 코퍼스가 자라도 흔들리지 않는다 —
    '단일 스키마 파서는 이 파일들에서 0건을 낸다'가 그대로 유지된다."""
    corpus = codex_corpus
    without = corpus["files"] - len(corpus["files_with_item"])
    assert corpus["files_with_item"], "item era 표본이 없다"
    assert without > 0
    # 두 era 가 섞인 파일은 없다 = item 이 있는 파일과 없는 파일이 정확히 이분된다
    assert without + len(corpus["files_with_item"]) == corpus["files"]
    assert without / corpus["files"] > 0.5, "legacy 다수라는 전제가 깨졌다 — 패널 문구 재검토"


def test_codex_actor_domain_holds_on_real_data(codex_events):
    """패널 ③의 'unknown 0'. 값이 아니라 도메인 불변식이다."""
    events, source = codex_events
    actors = {event.actor for event in events}

    assert actors <= {"user", "agent"}, f"unknown 이 생겼다: {actors}"
    assert not source.schema_warnings, source.schema_warnings[:3]
    commands = [e for e in events if e.meta.get("record_type") == "command_execution"]
    sources = {e.meta.get("source") for e in commands}
    assert "user_shell" in sources, "user_shell 표본이 사라졌다 — §4.2 근거가 없어진다"
    assert "unified_exec_startup" in sources


def test_claude_remote_channel_evidence_survives(claude_prompt_sources):
    """패널 ③의 origin_channel. 246 은 고정하지 않고 판별 조합이 살아 있는지만 본다."""
    counts, combos = claude_prompt_sources
    assert counts.get("queued"), "queued 표본이 사라졌다 — 원격 판별 근거가 없어진다"
    assert combos.get(("queued", "human")), "queued ∧ human 조합이 0 — §9.4 전제가 깨진다"
    assert combos.get(("typed", "human")), "typed ∧ human 조합이 0"
    # 원격이 로컬보다 훨씬 적다는 방향(패널 서술의 전제)
    assert combos[("queued", "human")] < combos[("typed", "human")]


# =========================================================================
# 동결 수치 동기화 — 두 문서가 같은 값을 말하는가
# =========================================================================
# 2026-08-22 17:20 을 동결 시각으로 잡고 두 문서를 그 값으로 맞췄다.
# 코퍼스는 계속 자라므로 **동결값 == 현재값**은 요구하지 않는다.
# 요구하는 것은 두 가지뿐이다: ①동결값이 두 문서 사이에서 서로 일치할 것
# ②스냅샷 시각이 표기돼 있을 것. 현재값과의 격차는 실패가 아니라 경고로 알린다.
#
# 원래 짝은 종합문서 ↔ 패널 F6 그림이었다. 포스터 제작을 이 저장소에서 접으면서(2026-08-22)
# 짝을 팀원 인계문서로 옮겼다. 같은 수치를 말하는 문서가 둘이면 한쪽만 고치는 사고가 나고,
# 그게 지금 남은 유일한 드리프트 경로다.

REPO = Path(__file__).resolve().parents[1]
FROZEN_DOC = REPO / "docs" / "AgenTrace-종합-아티팩트-분석.md"
FROZEN_HANDOFF = REPO / "docs" / "AgenTrace-아티팩트-인계문서.md"
DRIFT_WARN_RATIO = 0.02      # 2% 넘게 벌어지면 '갱신 검토' 경고


def _int(text):
    return int(text.replace(",", ""))


def _frozen_from_doc(text):
    """§9.2 실측 표와 §3.3 ① 블록에 박힌 동결값. 표현이 바뀌면 못 찾고 실패한다 — 의도된 것이다."""
    found = {}
    for key, pattern in (
            ("events", r"복원 이벤트\s*\|\s*\*{0,2}([\d,]+)"),
            # 종합문서 "| rollout | **353파일** |" · 인계문서 "| Codex rollout 코퍼스 | **353파일** |"
            ("files", r"\|[^|\n]*rollout[^|\n]*\|\s*\*{0,2}([\d,]+)\s*파일"),
    ):
        match = re.search(pattern, text)
        if match:
            found[key] = _int(match.group(1))
    # 24단계: 회수율 표. 두 문서가 같은 지표에 다른 분모(21,482 vs 18,927)를 써서
    # 11.5% / 12.9% 로 갈렸는데 위 키들이 그 행을 안 봐서 못 잡았다.
    cmd = re.search(r"\|\s*명령\s*\|\s*\*{0,2}([\d,]+)\*{0,2}\s*\|\s*\*{0,2}([\d,]+)"
                    r"\*{0,2}\s*\|\s*\*{0,2}([\d.]+)\s*%", text)
    if cmd:
        found["cmd_legacy"], found["cmd_item"] = _int(cmd.group(1)), _int(cmd.group(2))
        found["cmd_rate"] = float(cmd.group(3))
    write = re.search(r"\|\s*(?:파일 )?쓰기\s*\|\s*\*{0,2}([\d,]+)\*{0,2}\s*\|\s*\*{0,2}([\d,]+)"
                      r"\*{0,2}\s*\|\s*\*{0,2}([\d.]+)\s*%", text)
    if write:
        found["write_legacy"], found["write_item"] = _int(write.group(1)), _int(write.group(2))
        found["write_rate"] = float(write.group(3))
    actor = re.search(r"agent\s+([\d,]+)\s*[·/]\s*user\s+([\d,]+)", text)
    if actor:
        found["agent"], found["user"] = _int(actor.group(1)), _int(actor.group(2))
    window = re.search(r"세션 파일\s*\*{0,2}([\d,]+)\s*/\s*([\d,]+)\s*=\s*([\d.]+)\s*%", text)
    if window:
        found["zero_files"] = _int(window.group(1))
        found["zero_total"] = _int(window.group(2))
        found["zero_pct"] = float(window.group(3))
    found["snapshot"] = bool(re.search(r"20\d\d-\d\d-\d\d(?:\s+\d\d:\d\d)?\s*스냅샷", text))
    return found


@pytest.fixture(scope="module")
def frozen():
    missing = [str(p) for p in (FROZEN_DOC, FROZEN_HANDOFF) if not p.is_file()]
    if missing:
        reason = (f"동결 수치 원본 없음: {', '.join(missing)} — 두 문서의 동기화를 확인하지 못했다.")
        warnings.warn(reason, UserWarning)
        pytest.skip(reason)
    return (_frozen_from_doc(FROZEN_DOC.read_text(encoding="utf-8")),
            _frozen_from_doc(FROZEN_HANDOFF.read_text(encoding="utf-8")))


def test_frozen_numbers_agree_between_the_two_documents(frozen):
    """같은 값이 두 곳에 박혀 있다. 한쪽만 고치면 인쇄물이 자기모순한다."""
    doc, handoff = frozen
    shared = sorted(set(doc) & set(handoff) - {"snapshot"})
    assert shared, f"두 문서에서 공통으로 뽑힌 동결값이 없다 — 표현이 바뀌었는지 확인해라 (종합={doc}, 인계={handoff})"
    mismatched = {key: (doc[key], handoff[key]) for key in shared if doc[key] != handoff[key]}
    assert not mismatched, f"두 문서의 동결값 불일치 {{항목: (종합, 인계)}}: {mismatched}"


def test_frozen_numbers_are_internally_consistent(frozen):
    """동결값끼리의 산수도 맞아야 한다 — 한 칸만 고치고 파생값을 안 고치는 실수를 막는다."""
    for source, name in zip(frozen, ("문서", "F6")):
        if {"agent", "user", "events"} <= set(source):
            assert source["agent"] + source["user"] == source["events"], (
                f"{name}: agent+user={source['agent'] + source['user']} 인데 "
                f"이벤트는 {source['events']} — unknown 0 이라면 합이 같아야 한다")
        if {"zero_files", "zero_total", "zero_pct"} <= set(source):
            computed = round(100 * source["zero_files"] / source["zero_total"], 1)
            assert computed == source["zero_pct"], (
                f"{name}: {source['zero_files']}/{source['zero_total']} = {computed}% "
                f"인데 {source['zero_pct']}% 로 적혀 있다")
        if {"files", "zero_total"} <= set(source):
            assert source["files"] == source["zero_total"], (
                f"{name}: rollout {source['files']}파일 vs 0건 구간 분모 {source['zero_total']}")
        # 회수율은 item/(legacy+item) — 표에 적힌 두 수로 그 퍼센트가 다시 나와야 한다.
        for prefix in ("cmd", "write"):
            keys = {f"{prefix}_legacy", f"{prefix}_item", f"{prefix}_rate"}
            if keys <= set(source):
                legacy, item = source[f"{prefix}_legacy"], source[f"{prefix}_item"]
                computed = round(100 * item / (legacy + item), 1)
                assert computed == source[f"{prefix}_rate"], (
                    f"{name}: {prefix} {item}/({legacy}+{item}) = {computed}% 인데 "
                    f"{source[f'{prefix}_rate']}% 로 적혀 있다")


def test_frozen_numbers_carry_a_snapshot_time(frozen):
    """동결값은 시각 표기 없이는 못 읽는다 — 언제 기준인지 모르면 낡았는지도 모른다."""
    doc, handoff = frozen
    assert doc["snapshot"], "종합 문서에 '스냅샷' 시각 표기가 없다"
    assert handoff["snapshot"], "인계문서에 'YYYY-MM-DD HH:MM 스냅샷' 표기가 없다"


def test_frozen_versus_current_drift_is_reported(frozen, codex_events, codex_corpus):
    """실패시키지 않는다. 발표 직전에 '얼마나 낡았는지'를 보고 갱신 여부를 판단하라고 알릴 뿐이다."""
    doc, _ = frozen
    events, _ = codex_events
    current = {"events": len(events), "files": codex_corpus["files"],
               "agent": sum(1 for e in events if e.actor == "agent"),
               "user": sum(1 for e in events if e.actor == "user"),
               "zero_files": codex_corpus["files"] - len(codex_corpus["files_with_item"])}

    drifted = []
    print("\n── 동결값 대 현재값 ──")
    for key in sorted(set(doc) & set(current)):
        frozen_value, now = doc[key], current[key]
        delta = now - frozen_value
        ratio = abs(delta) / frozen_value if frozen_value else 0
        flag = "  ← 갱신 검토" if ratio > DRIFT_WARN_RATIO else ""
        print(f"{key:<12} 동결 {frozen_value:>8,} · 현재 {now:>8,} · 차이 {delta:+,}{flag}")
        if ratio > DRIFT_WARN_RATIO:
            drifted.append(f"{key}: {frozen_value:,} → {now:,} ({delta:+,})")
    if drifted:
        warnings.warn("동결 수치가 현재값과 " + f"{DRIFT_WARN_RATIO:.0%} 넘게 벌어졌다 — "
                      "패널 인쇄 전에 갱신 검토: " + " · ".join(drifted), UserWarning)


# =========================================================================
# iOS(S1·S2) — 아직 미측정. 자리만 잡아두고, 데이터가 오면 깨어난다.
# =========================================================================

def test_ios_six_axes_are_written_down():
    """iOS(S1·S2) 여섯 축이 인계 문서에 **글로 남아 있는지** 단언한다.

    원래 이 자리는 "취득본이 오면 깨어나는" 센티넬이었다. 실측이 끝난 지금 남은 위험은
    취득본의 부재가 아니라 **문서의 빈칸**이다 — 패널을 만드는 사람은 취득본을 보지 않고
    이 문서만 본다. 그래서 축마다 그 축을 실제로 다뤘다는 표지 문자열을 요구한다.

    ⑥은 특이하다. iOS 존속 실험은 하지 않았으므로 **"미측정이라고 적었는지"**를 요구한다.
    빈칸을 "Android와 같다"로 읽는 것이 이 테스트가 막으려는 유일한 사고다.
    """
    if not HANDOFF_DOC.is_file():
        pytest.fail(f"인계 문서 없음: {HANDOFF_DOC}")
    text = HANDOFF_DOC.read_text(encoding="utf-8")
    missing = [f"{axis} (표지 {' / '.join(markers)} 없음)"
               for axis, markers in IOS_AXES
               if not any(m in text for m in markers)]
    assert not missing, (
        "인계 문서의 iOS 축이 비어 있다 — 패널에서 그 칸을 'Android와 같다'로 채우면 안 된다:\n  "
        + "\n  ".join(missing))


def test_panel_number_sheet(codex_corpus, claude_prompt_sources, tmp_path):
    """인쇄 직전 대조용 표. `pytest tests/test_panel_numbers.py -s` 로 본다."""
    corpus = codex_corpus
    counts, combos = claude_prompt_sources
    # 문서(§3.3 ②)와 **같은 분모** — legacy 파일 한정. 여기서 전 코퍼스를 쓰면
    # 대조표가 문서와 다른 회수율을 말한다.
    legacy_cmd = (corpus["legacy_fc_exec"] | corpus["legacy_ctc_exec"]
                  | corpus["legacy_exec_end"])
    legacy_write = corpus["legacy_apply_patch"] | corpus["legacy_patch_end"]
    without = corpus["files"] - len(corpus["files_with_item"])

    print("\n── 동결 수치 대조표 (실데이터, 스냅샷 시각 기준) ──")
    print(f"rollout 파일                {corpus['files']}")
    print(f"item_completed 없는 파일     {without}/{corpus['files']}"
          f" = {100 * without / corpus['files']:.1f}%  ← 단일 스키마 파서 0건 구간")
    print(f"명령 회수율                 "
          f"{100 * corpus['item_command'] / (corpus['item_command'] + len(legacy_cmd)):.1f}%"
          f"   (item {corpus['item_command']} / legacy distinct {len(legacy_cmd)})")
    print(f"쓰기 회수율                 "
          f"{100 * corpus['item_filechange'] / (corpus['item_filechange'] + len(legacy_write)):.1f}%"
          f"   (item {corpus['item_filechange']} / legacy distinct {len(legacy_write)})")
    print(f"  분모 중복 제거            명령 {len(corpus['legacy_fc_exec']) + len(corpus['legacy_ctc_exec']) + len(corpus['legacy_exec_end'])}"
          f"→{len(legacy_cmd)} · 쓰기 {len(corpus['legacy_apply_patch']) + len(corpus['legacy_patch_end'])}→{len(legacy_write)}")
    print(f"  분모 범위                 legacy 파일 {without}개 한정 — 전 코퍼스로 쓰면 "
          f"{len(corpus['fc_exec'] | corpus['ctc_exec'] | corpus['exec_end'])} (item-era "
          f"custom_tool_call 이중계상)")
    print(f"Claude queued               {counts.get('queued')}"
          f"  (queued∧human {combos.get(('queued', 'human'))})")
    print("합성 정확도                 주체/접근/MCP 각 100건 100.0% (위 테스트에서 고정)")
    print("시연 화면                   총 19 · 사용자 7 · 에이전트 12 · bypass 2 (고정)")
    print("iOS(S1·S2)                  실측 완료 — 인계 문서 §3.2 · 자격증명 축 0건(키체인)")
    print("  단 iOS 종료 후 존속        미측정 — 인계 문서 §7.2에 명시")

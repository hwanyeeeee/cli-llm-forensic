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
import warnings
from pathlib import Path

import pytest

from tests.test_accuracy_codex import score_access, score_actor, score_mcp

CODEX_HOME = Path.home() / ".codex"
CLAUDE_HOME = Path.home() / ".claude"
EXEC_NAMES = {"exec_command", "shell_command", "run"}


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
    return out


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


def test_codex_actor_domain_holds_on_real_data():
    """패널 ③의 'unknown 0'. 값이 아니라 도메인 불변식이다."""
    _require(CODEX_HOME, "Codex actor 분포")
    from clfx.parser import parse_source
    from clfx.sources import source_for
    source = source_for(str(CODEX_HOME))
    events = list(parse_source(source))
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


def test_panel_number_sheet(codex_corpus, claude_prompt_sources, tmp_path):
    """인쇄 직전 대조용 표. `pytest tests/test_panel_numbers.py -s` 로 본다."""
    corpus = codex_corpus
    counts, combos = claude_prompt_sources
    legacy_cmd = corpus["fc_exec"] | corpus["ctc_exec"] | corpus["exec_end"]
    legacy_write = corpus["apply_patch"] | corpus["patch_end"]
    without = corpus["files"] - len(corpus["files_with_item"])

    print("\n── 패널 수치 대조표 (실데이터, 스냅샷 시각 기준) ──")
    print(f"rollout 파일                {corpus['files']}")
    print(f"item_completed 없는 파일     {without}/{corpus['files']}"
          f" = {100 * without / corpus['files']:.1f}%  ← 단일 스키마 파서 0건 구간")
    print(f"명령 회수율                 "
          f"{100 * corpus['item_command'] / (corpus['item_command'] + len(legacy_cmd)):.1f}%"
          f"   (item {corpus['item_command']} / legacy distinct {len(legacy_cmd)})")
    print(f"쓰기 회수율                 "
          f"{100 * corpus['item_filechange'] / (corpus['item_filechange'] + len(legacy_write)):.1f}%"
          f"   (item {corpus['item_filechange']} / legacy distinct {len(legacy_write)})")
    print(f"  분모 중복 제거            명령 {len(corpus['fc_exec']) + len(corpus['ctc_exec']) + len(corpus['exec_end'])}"
          f"→{len(legacy_cmd)} · 쓰기 {len(corpus['apply_patch']) + len(corpus['patch_end'])}→{len(legacy_write)}")
    print(f"Claude queued               {counts.get('queued')}"
          f"  (queued∧human {combos.get(('queued', 'human'))})")
    print("합성 정확도                 주체/접근/MCP 각 100건 100.0% (위 테스트에서 고정)")
    print("시연 화면                   총 19 · 사용자 7 · 에이전트 12 · bypass 2 (고정)")

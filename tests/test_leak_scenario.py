"""11단계 — 유출 시나리오 재현 (A/B 두 결론).

같은 "민감파일이 외부로 나갔다"는 결과에서 **주체가 갈리는 두 사건**을 통제 데이터로 재현하고,
Claude·Codex 어느 형식이든 도구가 같은 결론을 내는지 고정한다.

  결론 A — 사용자 직접: 사람이 민감파일을 열어 프롬프트에 붙여넣어 전송
  결론 B — 에이전트 자율: 직접 지시 없이 권한확인 생략 모드에서 에이전트가 자율로 읽어 전송

데이터셋은 `tests/fixtures/leak-scenario/`. 전부 합성이고 자격증명은 AWS 공식 문서의
공개 example 값이다. 서술과 근거는 `docs/validation/유출시나리오-재현.md`.
"""
import json
import os
from pathlib import Path

import pytest

from clfx.web.api import scan_to_engine, stats_payload

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "leak-scenario"
CLAUDE_ROOT = str(FIXTURE / "claude")
CODEX_ROOT = str(FIXTURE / "codex")

SESSION_A = "0000000a-0000-4000-8000-00000000000a"
SESSION_B = "0000000b-0000-4000-8000-00000000000b"

ENV_PATH = "/srv/acme-demo/config/.env"
KEY_PATH = "/srv/acme-demo/keys/deploy_key"
ENDPOINT = "intake.example.net"
# 원문에는 있어야 하고(재현 데이터로서) preview에는 없어야 한다(마스킹 증명).
DUMMY_SECRETS = ("AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                 "demo-not-a-real-password", "BEGIN OPENSSH PRIVATE KEY")
# A1은 공개 전시물이다 — 캡처에 개인 경로가 한 조각도 섞이면 안 된다.
PERSONAL_PATH_MARKERS = ("/home/", "/mnt/c/Users/", "/Users/", "C:\\Users\\")


@pytest.fixture(scope="module")
def engine():
    return scan_to_engine([CLAUDE_ROOT, CODEX_ROOT])


def _by_scenario(events, agent, scenario):
    session = SESSION_A if scenario == "A" else SESSION_B
    return [e for e in events if e.agent == agent and e.session == session]


def _secret_events(events, agent, scenario):
    return [e for e in _by_scenario(events, agent, scenario) if "secret" in e.tags]


def _raw_text():
    out = []
    for directory, _, names in os.walk(FIXTURE):
        out += [Path(directory, name).read_text(encoding="utf-8")
                for name in sorted(names) if name.endswith(".jsonl")]
    return "".join(out)


def test_dataset_shape():
    files = sorted(str(Path(d, n).relative_to(FIXTURE))
                   for d, _, names in os.walk(FIXTURE) for n in names if n.endswith(".jsonl"))
    assert len(files) == 4, files
    assert sum("claude" in f for f in files) == 2
    assert sum("codex" in f for f in files) == 2
    raw = _raw_text()
    for token in DUMMY_SECRETS:              # 재현 데이터니까 원문에는 있어야 한다
        assert token in raw, token


def test_conclusion_a_is_the_person(engine):
    """A: 민감값을 실은 Event의 주체가 두 도구 모두 user다."""
    for agent in ("claude", "codex"):
        secrets = _secret_events(engine.events, agent, "A")
        assert secrets, agent
        assert {e.actor for e in secrets} == {"user"}, agent
        assert any(e.action == "prompt" for e in secrets), agent   # 붙여넣기로 전송


def test_conclusion_b_is_the_agent(engine):
    """B: 같은 파일인데 민감값을 실은 Event의 주체가 두 도구 모두 agent다."""
    for agent in ("claude", "codex"):
        secrets = _secret_events(engine.events, agent, "B")
        assert secrets, agent
        assert {e.actor for e in secrets} == {"agent"}, agent
        # Claude는 target이 경로 자체(read), Codex는 경로를 담은 명령(bash) — 둘 다 짚혀야 한다.
        touched = " ".join(e.target for e in secrets)
        assert ENV_PATH in touched and KEY_PATH in touched, (agent, touched)


def test_two_tools_reach_the_same_conclusion(engine):
    """핵심: 기록 형식이 달라도 주체 판정이 갈리지 않는다."""
    for scenario, expected in (("A", {"user"}), ("B", {"agent"})):
        claude = {e.actor for e in _secret_events(engine.events, "claude", scenario)}
        codex = {e.actor for e in _secret_events(engine.events, "codex", scenario)}
        assert claude == codex == expected, (scenario, claude, codex)


def test_b_has_no_user_instruction_naming_the_target(engine):
    """B가 '자율'인 근거: 사용자 프롬프트 어디에도 민감 경로·자격증명이 없다.
    지시가 있었다면 그건 자율이 아니라 위임이고 결론이 달라진다."""
    for agent in ("claude", "codex"):
        prompts = [e for e in _by_scenario(engine.events, agent, "B") if e.actor == "user"]
        assert prompts, agent
        for event in prompts:
            assert "secret" not in event.tags
            for token in (ENV_PATH, KEY_PATH, "key", "credential", ".env"):
                assert token not in event.preview, (agent, token)


def test_bypass_mode_evidence_is_recorded_per_tool(engine):
    """권한확인 생략 모드가 '어느 세션에서 켜졌는지' 기록으로 남는다 — 단 형태가 도구마다 다르다.

    Claude: permission-mode(bypassPermissions) 레코드 → read Event에 `bypass-mode` 태그
    Codex : turn_context(approval_policy=never · danger-full-access) → Event.meta에 정책 스냅샷

    이 비대칭 자체가 결과다. 두 근거를 하나의 태그로 합칠지는 미결(docs/validation/유출시나리오-재현.md §5)."""
    claude_b = _secret_events(engine.events, "claude", "B")
    assert all("bypass-mode" in e.tags for e in claude_b)
    assert all("bypass-mode" not in e.tags
               for e in _by_scenario(engine.events, "claude", "A"))

    codex_b = _secret_events(engine.events, "codex", "B")
    assert all(e.meta["approval_policy"] == "never" for e in codex_b)
    assert all(e.meta["sandbox_policy"] == {"type": "danger-full-access"} for e in codex_b)
    codex_a = _secret_events(engine.events, "codex", "A")
    assert all(e.meta["approval_policy"] == "on-request" for e in codex_a)
    assert all(e.meta["sandbox_policy"] == {"type": "workspace-write"} for e in codex_a)
    # Codex는 아직 `bypass-mode` 태그를 달지 않는다 — 대시보드 bypass 타일에 안 잡힌다.
    assert all("bypass-mode" not in e.tags for e in codex_b)


def test_codex_marks_the_human_run_command_as_user(engine):
    """A에서 Codex만 낼 수 있는 추가 근거: source=user_shell 명령의 주체는 사람이다.
    Claude에는 사용자가 직접 친 명령을 담는 레코드가 없다(§5-2 도구 간 범위 차이)."""
    shell = [e for e in _by_scenario(engine.events, "codex", "A")
             if e.meta.get("source") == "user_shell"]
    assert len(shell) == 1
    assert shell[0].actor == "user" and shell[0].action == "bash"
    assert ENV_PATH in shell[0].target


def test_exfiltration_is_attributed_to_the_agent(engine):
    """전송 행위 자체는 두 사건 모두 에이전트가 실행한다 — 갈리는 건 '누가 읽게 했나'다."""
    for agent in ("claude", "codex"):
        sent = [e for e in _by_scenario(engine.events, agent, "B")
                if e.action == "bash" and ENDPOINT in e.target]
        assert len(sent) == 1, agent
        assert sent[0].actor == "agent"


def test_previews_are_masked_and_citations_resolve(engine):
    """유출 재현 데이터인데도 화면에 원값이 뜨면 안 된다. 그리고 모든 근거는 file:line으로 되짚힌다."""
    for event in engine.events:
        for token in DUMMY_SECRETS:
            assert token not in (event.preview or ""), (event.source.file, token)
        line = Path(event.source.file).read_text(encoding="utf-8").splitlines()[
            event.source.line - 1]
        json.loads(line)                       # 인용 좌표가 실제 레코드를 가리킨다


def test_nothing_personal_is_showable(engine):
    """A1은 공개 전시물이다 — 이 데이터셋으로 캡처하면 개인 경로가 새지 않는다."""
    for event in engine.events:
        for marker in PERSONAL_PATH_MARKERS:
            assert marker not in (event.target or ""), (marker, event.target)
            assert marker not in (event.preview or ""), (marker, event.preview[:80])


def test_dashboard_demo_numbers(engine):
    """시연 화면에 뜨는 숫자를 고정한다. 데이터셋을 바꾸면 여기가 먼저 깨져야 한다."""
    assert stats_payload(engine) == {"total": 19, "user": 7, "agent": 12,
                                     "unknown": 0, "actor_warnings": 0, "bypass": 2}

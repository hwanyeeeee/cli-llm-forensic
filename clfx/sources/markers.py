"""원격제어 마커 — 호스트·계정 단위 **상태** 판독(Event 아님).

Event 는 "에이전트가 한 행동 하나"다. `hasUsedRemoteControl` 같은 플래그는 행동이
아니라 설정 상태라서 Event 로 만들면 같은 사실이 타임라인에 한 줄 더 늘어 과계수가
난다. 그래서 `source_warnings` 와 같은 계층 — 소스 메타 — 로만 노출한다.

## 판정 3값 (`signal`)

| 값 | 뜻 | 도구가 할 수 있는 말 |
|---|---|---|
| `configured` | 마커가 양성값을 들고 있다 | **"설정된 적 있다"까지만** |
| `none` | 파일을 읽었고 키도 있는데 값이 음성이다 | "이 마커는 음성이다" |
| `unknown` | 파일 없음·못 읽음·키 없음 | **아무 말도 못 한다** |

`configured` 는 "원격제어를 썼다"가 아니다. `~/.codex/app-server-daemon/settings.json`
이 true 여도 채널은 죽어 있을 수 있고, `remote_control_enrollments` 는 enroll 이 MFA
로 거부돼도 0행이다. 실제 원격 실행 여부는 Event 의 `origin_channel` 이 말한다 —
이 계층이 아니다.

## 휘발성 마커 (`volatile`)

`~/.claude/sessions/<pid>.json` 은 **정상종료 시 삭제된다.** 그래서 아무것도 못 찾은
것이 "원격제어를 안 썼다"의 근거가 될 수 없다. 휘발성 마커는 `none` 을 낼 수 없게
`marker()` 가 막는다 — 부재를 부재로 보고하지 않으려는 것이다.
"""
import json

from clfx import roio

SIGNALS = ("configured", "none", "unknown")


def marker(kind, agent, path, status, signal, note, volatile=False, **extra):
    """마커 1행. 관측 부재에 기본값을 주지 않는 규칙을 여기서 강제한다.

    - `status != "observed"` → 파일을 못 봤다는 뜻이므로 signal 은 언제나 `unknown`
    - `volatile` 마커는 `none` 을 못 낸다 — 사라지는 증거의 부재는 음성 근거가 아니다
    """
    if signal not in SIGNALS:
        raise ValueError(f"unknown signal: {signal}")
    if status != "observed":
        signal = "unknown"
    if volatile and signal == "none":
        raise ValueError(f"{kind}: 휘발성 마커는 none 을 낼 수 없다(부재≠미사용)")
    row = {"kind": kind, "agent": agent, "file": str(path), "status": status,
           "signal": signal, "volatile": bool(volatile), "note": note}
    row.update(extra)
    return row


def read_json(path):
    """증거 파일 1개 → (status, obj). 읽기 전용(roio 강제)·예외 없음.

    status 는 `observed` / `missing` / `unreadable` 셋뿐이다. 손상 JSON 을 빈 dict 로
    뭉개면 '파일은 있는데 플래그가 없다'와 구분이 안 된다 — 그래서 나눠서 돌려준다."""
    try:
        with roio._ro_open(path, "rb") as handle:
            obj = json.loads(handle.read().decode("utf-8", errors="replace"))
    except FileNotFoundError:
        return "missing", None
    except (OSError, ValueError):          # 권한·손상 JSON·디코딩 — 봤지만 못 읽음
        return "unreadable", None
    return ("observed", obj) if isinstance(obj, dict) else ("unreadable", None)


def flag_marker(kind, agent, path, keys, note):
    """최상위 boolean/count 플래그 묶음 1개를 마커로. 실제로 **있는 키만** values 에 싣는다.

    없는 키는 `absent_keys` 로 따로 보고한다 — 없는 것과 false 인 것을 같은 칸에 넣으면
    구버전 CLI(키 자체가 없음)와 '꺼 둠'이 구분되지 않는다."""
    status, obj = read_json(path)
    if obj is None:
        return marker(kind, agent, path, status, "unknown", note)
    values = {key: obj[key] for key in keys if key in obj}
    absent = [key for key in keys if key not in obj]
    if not values:
        signal = "unknown"                 # 파일은 읽었지만 이 축을 말해주는 키가 하나도 없다
    elif any(bool(value) for value in values.values()):
        signal = "configured"
    else:
        signal = "none"
    return marker(kind, agent, path, status, signal, note,
                  values=values, absent_keys=absent)


def summarize(markers):
    """마커 목록 → 소스 요약. 종합 boolean 을 만들지 않는 게 핵심이다.

    `claim` 은 `configured_before`(설정 흔적 있음) 아니면 `not_observed`(관측 없음)
    둘뿐이다. `not_used` 라는 값은 없다 — 이 계층은 미사용을 말할 수 없다."""
    rows = sorted(markers, key=lambda row: (row["agent"], row["kind"], row["file"]))
    counts = {signal: sum(1 for row in rows if row["signal"] == signal)
              for signal in SIGNALS}
    return {
        "markers": rows,
        "counts": counts,
        "claim": "configured_before" if counts["configured"] else "not_observed",
        "caveats": [
            "마커는 '설정된 적 있음'까지만 말한다. 실제 원격 실행 여부는 이벤트의 "
            "origin_channel 이 말한다.",
            "remote_control_enrollments 0행은 미사용이 아니다 — enroll 이 MFA 로 "
            "거부돼도 0행이다.",
            "settings.json 이 true 여도 채널이 살아 있다는 뜻은 아니다.",
            "sessions/<pid>.json 은 정상종료 시 삭제된다 — 없다고 원격제어를 안 쓴 게 아니다.",
        ],
    }

"""양식 규정 폰트 해석 — 포스터와 그림 4개가 **같은 글꼴**을 쓰게 하는 단일 지점.

경진대회 양식은 나눔스퀘어·KoPubWorld 7종만 허용한다(`docs/패널-구성안.md` §1).
그림은 `flowlib`이 그리는데, flowlib 기본 후보는 맑은고딕을 먼저 집으므로
각 그림 스크립트가 `Diagram(font=panel_font.resolve())`로 **명시해서 넘겨야** 한다.

한 곳에 모아 둔 이유: 포스터만 규정 폰트로 바꾸고 그림을 그대로 두면
같은 지면에서 본문과 그림 글꼴이 따로 논다. 실제로 그 상태로 한 번 구워졌다.

폰트가 없는 머신에서는 `resolve()`가 None을 돌려주고, 호출부는 기존 기본값으로
떨어진다 — 빌드는 되지만 규정 폰트는 아니다. `describe()`가 그 사실을 알려준다.
"""
from pathlib import Path

# 굵기별 파일명. 양식 폴더 동봉본 기준.
WEIGHTS = {
    "L": "NanumSquareL.otf",
    "R": "NanumSquareR.otf",
    "B": "NanumSquareB.otf",
    "EB": "NanumSquareEB.otf",
}

SEARCH_DIRS = [
    Path.home() / ".local/share/fonts/panel",
    Path.home() / ".local/share/fonts",
    Path("/usr/share/fonts/truetype/nanum"),
    Path("/usr/share/fonts/opentype/nanum"),
    Path(__file__).resolve().parent / "fonts",
]


def resolve(weight="B"):
    """규정 폰트 경로(str). 못 찾으면 None — 호출부가 기본값으로 떨어지게 한다."""
    name = WEIGHTS.get(weight, WEIGHTS["B"])
    for directory in SEARCH_DIRS:
        candidate = directory / name
        if candidate.is_file():
            return str(candidate)
    return None


def describe():
    """빌드 로그에 한 줄. 규정 폰트를 못 쓰고 있으면 그 사실이 보여야 한다."""
    found = resolve()
    if found:
        return f"폰트: 나눔스퀘어(규정) — {found}"
    return ("폰트: ⚠ 나눔스퀘어를 못 찾아 기본 글꼴로 렌더한다(양식 규정 미충족). "
            f"{SEARCH_DIRS[0]} 에 {', '.join(WEIGHTS.values())} 를 넣어라.")


if __name__ == "__main__":
    print(describe())
    for weight in WEIGHTS:
        print(f"  {weight:<2} {resolve(weight)}")

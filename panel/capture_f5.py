"""F5 대시보드 캡처 재생성 — `panel-f5-leak-scenario.png`.

    python3 panel/capture_f5.py

포스터가 쓰는 유일한 '손으로 만든' 입력이 이 캡처였다. 브라우저를 사람이 띄워
찍은 그림이 저장소에 굴러다니면, 나중에 누구도 같은 그림을 다시 만들 수 없다.
그래서 커밋된 유출 시나리오 fixture로 서버를 띄우고 headless Chrome으로 찍는다.

의존: `google-chrome`(또는 `chromium`) 실행 파일 하나. 파이썬 패키지 추가 없음.
입력: `tests/fixtures/leak-scenario/{claude,codex}` — 저장소에 커밋돼 있다.

캡처가 바뀌면 `draft_a1.py`의 `F5_CONTRAST` 크롭 좌표도 다시 맞춰야 한다.
그래서 마지막에 기대 해상도와 실제 해상도를 비교해 알려준다.
"""
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PANEL = Path(__file__).resolve().parent
REPO = PANEL.parent
OUTPUT = REPO / "panel-f5-leak-scenario.png"
# draft_a1.py의 F5_CONTRAST 크롭 좌표는 이 뷰포트에서 잡은 것이다.
# **CSS 뷰포트와 배율을 둘 다 맞춰야** 같은 레이아웃이 나온다 — 최종 픽셀 수만 같고
# CSS 폭이 다르면 반응형 배치가 달라져 크롭이 엉뚱한 줄을 집는다.
# --window-size는 CSS px, 최종 픽셀은 거기에 배율을 곱한 값이다.
# 세로를 1400으로 잡는 이유: A(09:13:22)와 B(14:05:33) 두 줄이 **한 화면에**
# 들어와야 크롭 두 개를 같은 캡처에서 뜰 수 있다.
VIEWPORT_CSS = (1600, 1400)
SCALE = 1.6
EXPECTED_SIZE = (int(VIEWPORT_CSS[0] * SCALE), int(VIEWPORT_CSS[1] * SCALE))
BROWSERS = ("google-chrome", "chromium", "chromium-browser", "google-chrome-stable")


def _browser():
    for name in BROWSERS:
        path = shutil.which(name)
        if path:
            return path
    sys.exit(f"headless 브라우저를 찾지 못했다. 다음 중 하나가 필요하다: {', '.join(BROWSERS)}")


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait(url, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def main():
    browser = _browser()
    roots = [str(REPO / "tests/fixtures/leak-scenario/claude"),
             str(REPO / "tests/fixtures/leak-scenario/codex")]
    for root in roots:
        if not Path(root).is_dir():
            sys.exit(f"유출 시나리오 fixture가 없다: {root}")

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "clfx.cli", "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait(f"{base}/api/scan/progress"):
            sys.exit("대시보드 서버가 안 떴다.")
        request = urllib.request.Request(
            f"{base}/api/scan", data=json.dumps({"roots": roots}).encode(),
            headers={"Content-Type": "application/json"})
        result = json.loads(urllib.request.urlopen(request, timeout=300).read())
        print(f"스캔 완료: {result['count']}건 · {result['by_origin']}")

        OUTPUT.unlink(missing_ok=True)
        subprocess.run(
            [browser, "--headless", "--disable-gpu", "--hide-scrollbars",
             f"--screenshot={OUTPUT}",
             f"--window-size={VIEWPORT_CSS[0]},{VIEWPORT_CSS[1]}",
             f"--force-device-scale-factor={SCALE}",
             "--virtual-time-budget=8000", base],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        server.terminate()
        server.wait(timeout=10)

    if not OUTPUT.is_file():
        sys.exit("캡처가 생성되지 않았다.")
    from PIL import Image
    with Image.open(OUTPUT) as image:
        size = image.size
    print(f"저장: {OUTPUT.relative_to(REPO)}  {size[0]}×{size[1]}  "
          f"{OUTPUT.stat().st_size / 1024:.0f}KB")
    if size != EXPECTED_SIZE:
        print(f"⚠ 기대 해상도 {EXPECTED_SIZE[0]}×{EXPECTED_SIZE[1]}와 다르다 — "
              f"draft_a1.py의 F5_CONTRAST 크롭 좌표를 다시 맞춰야 한다.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

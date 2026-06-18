"""clfx.exe 엔트리 — 로컬 서버(데몬) + 네이티브 GUI 창(pywebview). GUI 실패 시 브라우저 폴백. 인자 0."""
import os
import socket
import sys
import threading
import time
import webbrowser

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clfx.web.server import serve


def _free_port(host, start=8770, span=50):
    for p in range(start, start + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start


def _wait_ready(host, port, timeout=6.0):
    """서버가 바인드될 때까지 폴링(최대 timeout초)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with socket.create_connection((host, port), 0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def main(argv=None):
    host = "127.0.0.1"
    port = _free_port(host)
    url = f"http://{host}:{port}"
    threading.Thread(target=lambda: serve(None, host=host, port=port), daemon=True).start()
    _wait_ready(host, port)
    # 우선 네이티브 GUI 창. 백엔드 없으면(import/런타임 실패) 브라우저로 폴백.
    try:
        import webview                                  # pywebview
        # maximized로 화면 꽉 채워 起動(좌상단 절반만 차지 문제 해소) + resizable.
        # 구버전 pywebview는 maximized 미지원(TypeError) → 인자 없이 재생성(폴백 아님, 창은 뜸).
        try:
            webview.create_window("AgenTrace — CLI 에이전트 포렌식", url,
                                  width=1280, height=860, resizable=True, maximized=True)
        except TypeError:
            webview.create_window("AgenTrace — CLI 에이전트 포렌식", url,
                                  width=1280, height=860, resizable=True)
        webview.start()                                 # 메인스레드 블로킹 GUI 루프(창 닫으면 반환)
    except Exception as e:
        print(f"[clfx] GUI 백엔드 사용 불가({e}) → 브라우저로 엽니다.", file=sys.stderr)
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

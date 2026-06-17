"""clfx.exe 엔트리 — 빈 서버 起動 + 브라우저 자동 오픈. 인자 0 실행."""
import os
import socket
import sys
import threading
import webbrowser

# 개발 중 직접실행(python packaging/launcher.py) 시 repo root를 path에. frozen(exe)은 PyInstaller가 clfx 번들→스킵.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clfx.web.server import serve


def _free_port(host, start=8770, span=50):
    """start부터 span개 중 바인드 가능한 첫 포트. 다 막혔으면 start 반환(serve가 최종 에러 표면화)."""
    for p in range(start, start + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start


def main(argv=None):
    host = "127.0.0.1"
    port = _free_port(host)
    url = f"http://{host}:{port}"
    # 서버는 메인스레드서 블로킹 起動. 브라우저는 약간 늦게 데몬 타이머로 오픈(바인드 대기).
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"clfx: {url} 열림 (창을 닫으면 종료)", file=sys.stderr)
    serve(None, host=host, port=port)   # 빈 모드 → 브라우저에서 스캔
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

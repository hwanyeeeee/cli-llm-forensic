"""launcher._Api.save_url 단위 테스트 — 네이티브 SAVE 다이얼로그로 로컬 endpoint를 파일 저장.
webview/urllib을 mock해 GUI 없이 검증(write 동작·취소·실패 분기·content 무손실)."""
import importlib.util
import os
import sys
import types
import urllib.request

# 로컬 packaging/launcher.py를 파일경로로 로드(이름 'packaging'은 PyPI 패키지와 충돌 → importlib).
_LP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "packaging", "launcher.py")
_spec = importlib.util.spec_from_file_location("clfx_launcher", _LP)
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)


class _FakeWin:
    def __init__(self, dest):
        self.dest = dest
        self.calls = []

    def create_file_dialog(self, mode, save_filename=None):
        self.calls.append((mode, save_filename))
        return self.dest


def _install_fake_webview(monkeypatch, dest):
    win = _FakeWin(dest)
    fake = types.SimpleNamespace(
        SAVE_DIALOG="save",
        windows=[win],
        active_window=lambda: win,
        create_window=lambda *a, **k: None,
    )
    monkeypatch.setitem(sys.modules, "webview", fake)
    return win


def _fake_fetch(monkeypatch, payload):
    class _Resp:
        def read(self):
            return payload
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=10: _Resp())


def test_save_url_writes_fetched_bytes(tmp_path, monkeypatch):
    dest = str(tmp_path / "out.csv")
    win = _install_fake_webview(monkeypatch, dest)
    body = "﻿path,algorithm,sha256\r\n/a,SHA-256,aa\r\n".encode("utf-8")
    _fake_fetch(monkeypatch, body)

    api = launcher._Api("http://127.0.0.1:9")
    res = api.save_url("/api/attestation.csv", "acquisition-hash-manifest.csv")

    assert res == {"ok": True, "path": dest}
    with open(dest, "rb") as f:
        assert f.read() == body                       # 무손실: 받은 바이트 그대로(BOM 포함)
    assert win.calls == [("save", "acquisition-hash-manifest.csv")]   # 제안 파일명 전달


def test_save_url_dialog_tuple_result(tmp_path, monkeypatch):
    # pywebview SAVE_DIALOG는 일부 플랫폼서 (path,) 튜플 반환 → 첫 요소 사용.
    dest = str(tmp_path / "t.csv")
    _install_fake_webview(monkeypatch, (dest,))
    _fake_fetch(monkeypatch, b"x")
    api = launcher._Api("http://127.0.0.1:9")
    res = api.save_url("/api/attestation.csv", "f.csv")
    assert res["ok"] is True and res["path"] == dest


def test_save_url_cancel_writes_nothing(tmp_path, monkeypatch):
    _install_fake_webview(monkeypatch, None)          # 다이얼로그 취소
    _fake_fetch(monkeypatch, b"x")
    api = launcher._Api("http://127.0.0.1:9")
    res = api.save_url("/api/attestation.csv", "f.csv")
    assert res == {"ok": False, "cancelled": True}


def test_save_url_fetch_error_reported(monkeypatch):
    _install_fake_webview(monkeypatch, "/nowhere")
    def _boom(url, timeout=10):
        raise OSError("conn refused")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    api = launcher._Api("http://127.0.0.1:9")
    res = api.save_url("/api/attestation.csv", "f.csv")
    assert res["ok"] is False and "fetch:" in res["error"]


def test_view_titles_cover_every_dashboard_button():
    """exe 자식 창 제목은 index.html 의 포렌식 버튼과 **같은 집합**이어야 한다.

    브라우저 경로는 view.js 가 제목을 따로 갖고 있어 빠져도 안 드러난다 — exe 에서만
    '포렌식 뷰'라는 이름 없는 창으로 뜬다. 23단계 remote 가 실제로 그 상태였다.
    """
    import re
    html = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "clfx", "web", "static", "index.html")
    with open(html, encoding="utf-8") as f:
        buttons = set(re.findall(r'class="fbtn" data-modal="([^"]+)"', f.read()))
    assert buttons, "포렌식 버튼을 못 찾았다 — index.html 표현이 바뀌었는지 확인해라"
    assert buttons == set(launcher.TITLES), (
        f"버튼과 창 제목이 어긋난다 — 버튼에만: {sorted(buttons - set(launcher.TITLES))} · "
        f"제목에만: {sorted(set(launcher.TITLES) - buttons)}")

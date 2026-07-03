"""O9 적응형 파싱 동시성 — 원격성 분류 + 무손실(기존 등가성 테스트가 실행 경로 보증)."""
from clfx.web.api import _remote_root, scan_to_engine


def test_remote_root_classification():
    assert _remote_root(r"\\wsl.localhost\Ubuntu\home\u\.claude") is True
    assert _remote_root(r"\\wsl$\Ubuntu\home\u\.claude") is True
    assert _remote_root("/mnt/c/Users/u/.claude") is True
    assert _remote_root("/home/u/.claude") is False
    assert _remote_root(r"C:\Users\u\.claude") is False
    assert _remote_root("relative/path") is False


def test_native_fixture_scan_unchanged():
    # 네이티브 root(픽스처)는 이제 순차 경로 — 이벤트 결과는 기존과 동일해야 함.
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    assert len(eng.events) > 0
    assert all("origin:" in ",".join(e.tags) for e in eng.events)

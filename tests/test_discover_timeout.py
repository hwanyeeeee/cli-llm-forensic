"""O10 — 소스탐지가 9P wedge에서 hang 대신 타임아웃+표면화(완전성: 조용한 멈춤 금지)."""
import time

import clfx.discover as disc
from clfx.web.api import sources_payload


def test_isdir_t_normal(tmp_path):
    v, timed_out = disc._isdir_t(str(tmp_path), timeout=5.0)
    assert v is True and timed_out is False
    v2, t2 = disc._isdir_t(str(tmp_path / "nope"), timeout=5.0)
    assert v2 is False and t2 is False


def test_isdir_t_timeout(monkeypatch):
    def _hang(_p):
        time.sleep(2.0)
        return True
    monkeypatch.setattr(disc.os.path, "isdir", _hang)
    v, timed_out = disc._isdir_t(r"\\wsl.localhost\U\x", timeout=0.1)
    assert v is False and timed_out is True


def test_discover_sources_surfaces_timeout(monkeypatch):
    monkeypatch.setattr(disc, "_isdir_t", lambda p, timeout=3.0: (False, True))
    out = disc.discover_sources(candidates=[r"\\wsl.localhost\Ubuntu\home\u\.claude"])
    assert out[0]["exists"] is False
    assert "시간 초과" in out[0]["error"]


def test_sources_payload_warnings(monkeypatch):
    fake = [{"path": "/a/.claude", "label": "wsl", "exists": True},
            {"path": r"\\wsl.localhost\U\h\.claude", "label": "wsl", "exists": False,
             "error": "접근 시간 초과 — WSL 파일공유(9P) 응답 없음. wsl --shutdown 후 재시도"}]
    monkeypatch.setattr("clfx.discover.discover_sources", lambda candidates=None: fake)
    p = sources_payload()
    assert [s["path"] for s in p["sources"]] == ["/a/.claude"]   # exists만(기존 계약)
    assert len(p["warnings"]) == 1 and "시간 초과" in p["warnings"][0]

from clfx.event import Event, Source
from clfx.query.llm import OllamaLLM, make_llm, summarize


def _ev():
    return Event(ts="2026-06-11T01:00:00.000Z", agent="claude", session="s",
                 actor="agent", action="read", target=".env", preview="x",
                 source=Source("h.jsonl", 7), tags=[])


class _FakeLLM:
    def __init__(self): self.called = False
    def complete(self, prompt):
        self.called = True
        return "요약문 (h.jsonl:7)"


def test_summarize_uses_llm_when_present():
    llm = _FakeLLM()
    out = summarize([_ev()], llm=llm)
    assert llm.called and out["mode"] == "llm"
    assert out["citations"] == ["h.jsonl:7"]


def test_summarize_falls_back_when_llm_raises():
    class Dead:
        def complete(self, p): raise RuntimeError("ollama down")
    out = summarize([_ev()], llm=Dead())
    assert out["mode"] == "digest"          # 죽으면 digest


def test_make_llm_default_returns_ollama_client():
    llm = make_llm()
    assert isinstance(llm, OllamaLLM) and llm.model == "gemma4:12b"


def test_make_llm_disabled_returns_none():
    assert make_llm(use_ollama=False) is None


def test_ollama_complete_builds_request(monkeypatch):
    # urlopen을 가짜로 — 실제 ollama 없이 요청 구성·파싱 검증
    import clfx.query.llm as m
    captured = {}
    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"response": "hi"}'
    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = req.data
        return _Resp()
    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    out = OllamaLLM().complete("prompt-x")
    assert out == "hi"
    assert captured["url"].endswith("/api/generate")
    assert b"gemma4:12b" in captured["body"] and b"prompt-x" in captured["body"]

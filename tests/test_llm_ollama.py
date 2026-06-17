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


def test_ollama_default_host_is_ipv4_loopback():
    # exe(Windows)서 localhost가 IPv6 ::1로 풀려 ollama(IPv4 127.0.0.1 청취) 연결거부 → 127.0.0.1 고정.
    assert OllamaLLM().host == "http://127.0.0.1:11434"


def test_answer_llm_error_surfaced_on_failure():
    # LLM 실패 시 사유를 payload에 실어 UI가 원인(Connection refused/timeout) 표시 가능.
    from clfx.query.llm import answer
    class Dead:
        def complete(self, p): raise RuntimeError("Connection refused")
    evs = [Event(ts="2026-06-11T09:00:00Z", agent="claude", session="s", actor="agent",
                 action="read", target="id_rsa", preview="x", source=Source("h.jsonl", 7), tags=[])]
    out = answer("누가 읽었어?", evs, llm=Dead())
    assert out["mode"] == "digest" and "Connection refused" in out.get("llm_error", "")


def test_complete_uses_chat_endpoint(monkeypatch):
    # /api/chat(메시지 포맷 → 채팅 템플릿 적용) + keep_alive/num_predict/timeout300. message.content 추출.
    import clfx.query.llm as L, json as _json
    sent = {}
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return _json.dumps({"message": {"role": "assistant", "content": "요약 결과"}}).encode()
    def fake_urlopen(req, timeout=None):
        sent["url"] = req.full_url; sent["body"] = _json.loads(req.data.decode()); sent["timeout"] = timeout
        return FakeResp()
    monkeypatch.setattr(L.urllib.request, "urlopen", fake_urlopen)
    out = L.OllamaLLM().complete("질문")
    assert out == "요약 결과"
    assert sent["url"].endswith("/api/chat")
    assert sent["body"]["messages"][0]["content"] == "질문"
    assert sent["body"]["keep_alive"] == "30m" and sent["body"]["options"]["num_predict"] == 384
    assert sent["timeout"] == 300


def test_complete_thinking_fallback(monkeypatch):
    # content 비고 thinking에 답 있는 reasoning 모델 → thinking 사용(빈 응답 방지).
    import clfx.query.llm as L, json as _json
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return _json.dumps({"message": {"content": "  ", "thinking": "실제 답"}}).encode()
    monkeypatch.setattr(L.urllib.request, "urlopen", lambda req, timeout=None: FakeResp())
    assert L.OllamaLLM().complete("q") == "실제 답"


def test_complete_empty_raises_diagnostic(monkeypatch):
    # content·thinking 둘 다 비면 진단 에러 → answer가 llm_error로 라벨에 띄움(원인 파악).
    import clfx.query.llm as L, json as _json
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return _json.dumps({"message": {"content": ""}}).encode()
    monkeypatch.setattr(L.urllib.request, "urlopen", lambda req, timeout=None: FakeResp())
    try:
        L.OllamaLLM().complete("q")
        assert False, "빈 응답이면 raise 해야 함"
    except RuntimeError as e:
        assert "empty" in str(e)


def test_prewarm_swallows_errors(monkeypatch):
    import clfx.query.llm as L
    def boom(*a, **k): raise OSError("no ollama")
    monkeypatch.setattr(L.urllib.request, "urlopen", boom)
    L.prewarm()        # 예외 안 나야(무시·fire-and-forget)


def test_prewarm_uses_chat_endpoint(monkeypatch):
    import clfx.query.llm as L
    seen = {}
    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"message":{"content":"ok"}}'
    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url; return _Resp()
    monkeypatch.setattr(L.urllib.request, "urlopen", fake_urlopen)
    L.prewarm()
    assert seen["url"].endswith("/api/chat")

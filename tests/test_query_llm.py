from clfx.event import Event, Source
from clfx.query.engine import QueryEngine
from clfx.query.llm import route_intent, summarize

def _events():
    return [
        Event("2026-06-11T01:00:00Z","claude","s","user","paste","[Pasted #1]","env body",Source("history.jsonl",1),["secret"]),
        Event("2026-06-11T02:00:00Z","claude","s","agent","read","/x/.env","‹secret›",Source("sess.jsonl",3),["secret","bypass-mode"]),
    ]

def test_route_who_read():
    intent = route_intent("누가 .env 읽었어?")
    assert intent["op"] == "who_did" and intent["action"] == "read" and ".env" in intent["target"]

def test_route_secrets():
    assert route_intent("유출된 비밀 뭐야?")["op"] == "secrets"

def test_route_strips_korean_particles():
    # 한국어 조사가 파일명에 붙어도 path-safe 파일명만 추출 (.env를 → .env)
    for q, want in [("누가 .env를 읽었어?", ".env"),
                    ("config.py를 누가 읽음?", "config.py"),
                    ("/x/.npmrc에 접근한 게 누구야?", "/x/.npmrc")]:
        intent = route_intent(q)
        assert intent["op"] == "who_did" and intent["target"] == want, (q, intent)

def test_route_case_insensitive():
    # secret/summar 키워드 대소문자 무관(ql 일관)
    assert route_intent("SECRET leaked")["op"] == "secrets"
    assert route_intent("show me SUMMARY of secrets")["summarize"] is True

def test_route_read_verb_beats_secret_keyword():
    # 파일명에 secret 들어가도 read 동사가 있으면 who_did(read 의도 보존)
    intent = route_intent("누가 .secret.key 읽었어?")
    assert intent["op"] == "who_did" and intent["target"] == ".secret.key"

def test_route_no_dot_filename():
    # 점 없는 파일명(id_rsa/Dockerfile)도 추출 (SSH키 핵심경로)
    assert route_intent("누가 id_rsa 읽었어?") == {"op": "who_did", "action": "read",
                                                "target": "id_rsa", "summarize": False}
    assert route_intent("누가 Dockerfile 읽었어?")["target"] == "Dockerfile"
    assert route_intent("who read id_rsa")["target"] == "id_rsa"   # 영어 동사 제외

def test_route_read_without_target_no_broad_match():
    # 파일명 추출 실패 → broad who_did 금지, search 폴백
    intent = route_intent("누가 읽었어?")
    assert intent["op"] == "search"
    assert intent.get("target", "") == ""

def test_route_filler_not_picked_as_filename():
    # 영어 filler/의문사(did/anyone) 가 파일명으로 오인되지 않음
    assert route_intent("did anyone read id_rsa?")["target"] == "id_rsa"
    assert route_intent("did someone access Dockerfile?")["target"] == "Dockerfile"

def test_route_timeline():
    assert route_intent("타임라인 보여줘")["op"] == "timeline"
    assert route_intent("show me the timeline")["op"] == "timeline"
    assert route_intent("시간순으로 정리해줘")["op"] == "timeline"

def test_route_on_date():
    intent = route_intent("2026-06-11 무슨 대화했어 요약해줘")
    assert intent["op"] == "on_date" and intent["day"] == "2026-06-11" and intent["summarize"] is True

def test_summarize_cites_only_real_sources():
    eng = QueryEngine(_events())
    res = eng.who_did("read", ".env")
    out = summarize(res, llm=None)            # llm 없음 → digest fallback
    cited = set(out["citations"])
    real = {f"{e.source.file}:{e.source.line}" for e in res}
    assert cited and cited <= real
    assert out["text"]

def test_summarize_fallback_when_llm_dead():
    eng = QueryEngine(_events())
    out = summarize(eng.secrets(), llm=_DeadLLM())
    assert out["mode"] == "digest"

class _DeadLLM:
    def complete(self, prompt): raise RuntimeError("ollama down")

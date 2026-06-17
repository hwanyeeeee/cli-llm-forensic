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
    # 점 없는 파일명(id_rsa/Dockerfile)도 추출 (SSH키 핵심경로). actor 키 포함(§3, 누가→None).
    assert route_intent("누가 id_rsa 읽었어?") == {"op": "who_did", "action": "read",
                                                "target": "id_rsa", "actor": None, "summarize": False}
    assert route_intent("누가 Dockerfile 읽었어?")["target"] == "Dockerfile"
    assert route_intent("who read id_rsa")["target"] == "id_rsa"   # 영어 동사 제외


def test_route_actor_user_on_date():
    intent = route_intent("2026-06-11 사용자 행위 요약해줘")
    assert intent["op"] == "on_date" and intent["actor"] == "user" and intent["summarize"] is True


def test_route_actor_user_who_did():
    intent = route_intent("사용자가 .env 읽었어?")
    assert intent["op"] == "who_did" and intent["actor"] == "user"


def test_route_actor_agent():
    assert route_intent("에이전트가 뭐 읽었어")["actor"] == "agent"


def test_route_actor_none_for_who():
    assert route_intent("누가 .env 읽었어")["actor"] is None


def test_route_actor_not_from_filename():
    # 파일명류(user.json/CLAUDE.md)가 actor 어휘로 오인되면 안 됨(반대주체 누락 방지).
    assert route_intent("who read user.json?")["actor"] is None
    assert route_intent("누가 CLAUDE.md 읽었어?")["actor"] is None
    assert route_intent("사용자가 config.json 읽었어?")["actor"] == "user"   # 잔여 "사용자" 남음


def test_route_actor_not_from_target_span():
    # 점/슬래시 없는 타깃도 span 제거로 actor 오인 차단.
    assert route_intent("who read /tmp/user")["actor"] is None      # 경로 타깃 제거
    assert route_intent("who read CLAUDE")["actor"] is None         # 점없는 타깃 제거
    assert route_intent("user read config.json")["actor"] == "user"  # 타깃 제거 후 "user" 단어경계 매치

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


def test_answer_digest_fallback_no_llm():
    from clfx.query.llm import answer
    from clfx.event import Event, Source
    evs = [Event("2026-06-11T09:00:00Z","claude","s1","agent","read","id_rsa","x",Source("h.jsonl",7),[])]
    out = answer("누가 id_rsa 읽었어?", evs, llm=None)
    assert out["mode"] == "digest" and out["text"]
    assert out["citations"] == ["h.jsonl:7"]            # 실재 source


def test_answer_uses_llm_with_question():
    from clfx.query.llm import answer
    from clfx.event import Event, Source
    seen = {}
    class Stub:
        def complete(self, prompt):
            seen["p"] = prompt
            return "에이전트(B)가 id_rsa를 읽었습니다 (h.jsonl:7)."
    evs = [Event("2026-06-11T09:00:00Z","claude","s1","agent","read","id_rsa","x",Source("h.jsonl",7),[])]
    out = answer("누가 id_rsa 읽었어?", evs, llm=Stub())
    assert out["mode"] == "llm" and "id_rsa" in out["text"]
    assert "누가 id_rsa" in seen["p"]                    # 질문이 프롬프트에 포함(대화형)


def test_answer_empty_events_says_none():
    from clfx.query.llm import answer
    out = answer("말도 안되는 질문", [], llm=None)
    assert out["mode"] == "digest" and out["text"]      # 빈 결과도 답 반환("못 찾음")

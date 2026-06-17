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


def test_route_flexible_date_slash():
    i = route_intent("6/15일 내용 요약해줘")
    assert i["op"] == "on_date" and i["day"] == "06-15" and i["summarize"] is True


def test_route_flexible_date_korean():
    assert route_intent("6월 15일 뭐했어")["day"] == "06-15"


def test_route_full_date_still_works():
    assert route_intent("2026-06-15 요약")["day"] == "2026-06-15"

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
    assert out["mode"] == "empty" and out["text"]       # 빈 결과=empty(LLM 미연결과 구분)


def test_answer_empty_events_skips_llm():
    from clfx.query.llm import answer
    called = {"n": 0}
    class Stub:
        def complete(self, prompt):
            called["n"] += 1
            return "허위 가능 답"
    out = answer("아무거나", [], llm=Stub())
    assert out["mode"] == "empty" and out["citations"] == []
    assert called["n"] == 0                          # 근거 0건 → LLM 호출 안 됨(날조 차단)


def test_answer_overview_digest_no_llm():
    # 막연한 질문 → 전체 행위 개요(결정적 집계). llm 없으면 digest.
    from clfx.query.llm import answer_overview
    eng = QueryEngine(_events())
    out = answer_overview("이 사람 주로 뭐해?", eng.events, llm=None)   # 이벤트 리스트 기반(소스 필터 가능)
    assert out["mode"] == "digest"
    assert "전체 행위 개요" in out["text"] and "총 이벤트" in out["text"]
    assert out["citations"]                          # top files 근거(파일 패널 역추적)


def test_answer_overview_uses_llm():
    from clfx.query.llm import answer_overview
    seen = {}
    class Stub:
        def complete(self, prompt):
            seen["p"] = prompt
            return "주로 .env 파일 접근, 에이전트(B) 자율 읽기 중심입니다."
    eng = QueryEngine(_events())
    out = answer_overview("이 사람 주로 뭐해?", eng.events, llm=Stub())
    assert out["mode"] == "llm" and out["text"]
    assert "전체 집계" in seen["p"] and "이 사람 주로" in seen["p"]   # 집계 컨텍스트+질문 포함


def test_answer_overview_empty_engine():
    from clfx.query.llm import answer_overview
    out = answer_overview("뭐해?", [], llm=None)
    assert out["mode"] == "empty"                    # 기록 0건 → empty


def test_prompt_context_includes_preview_content():
    # LLM 컨텍스트에 실제 내용(preview) 포함 — prompt/response는 target="" 이라 내용 없으면 빈 껍데기.
    from clfx.query.llm import _prompt_context
    from clfx.event import Event, Source
    evs = [Event("2026-06-16T01:00:00Z", "claude", "s", "user", "prompt", "", "frida로 메모리 덤프 떠줘", Source("h", 1), [])]
    ctx = _prompt_context(evs)
    assert "frida로 메모리 덤프" in ctx              # 실제 내용이 LLM 컨텍스트에 들어감


def test_answer_uses_preview_in_prompt():
    from clfx.query.llm import answer
    from clfx.event import Event, Source
    seen = {}
    class Stub:
        def complete(self, p): seen["p"] = p; return "6/16에 사용자가 frida로 메모리 덤프를 요청했습니다 (h:1)."
    evs = [Event("2026-06-16T01:00:00Z", "claude", "s", "user", "prompt", "", "frida 메모리 덤프 요청", Source("h", 1), [])]
    out = answer("6/16 요약", evs, llm=Stub())
    assert out["mode"] == "llm" and "frida" in out["text"]
    assert "frida 메모리 덤프 요청" in seen["p"]       # preview 내용이 프롬프트에


def test_answer_empty_llm_response_falls_back():
    from clfx.query.llm import answer
    from clfx.event import Event, Source
    class Blank:
        def complete(self, p): return "   "             # 빈/공백 응답
    evs = [Event("2026-06-16T01:00:00Z", "claude", "s", "user", "prompt", "", "내용", Source("h", 1), [])]
    out = answer("요약", evs, llm=Blank())
    assert out["mode"] == "digest" and out["text"].strip()   # 빈 "결과 N건" 안 됨 — 내용 폴백
    assert out.get("llm_error") == "빈 응답"


def test_prompt_context_bounds_large_sets():
    # 대량 이벤트 → LLM 프롬프트는 [집계 헤더]+표본 N건으로 경계(전량 덤프=타임아웃/컨텍스트초과 차단).
    from clfx.query.llm import _prompt_context, _MAX_LLM_EVENTS
    from clfx.event import Event, Source
    evs = [Event(f"2026-06-11T00:00:{i%60:02d}Z", "claude", "s", "user", "prompt", "",
                 f"질문{i}", Source("h.jsonl", i), []) for i in range(300)]
    ctx = _prompt_context(evs)
    assert "[집계] 총 300건" in ctx                      # 대량=집계 헤더
    assert ctx.count("\n- ") <= _MAX_LLM_EVENTS + 1       # 표본만(전량 덤프 아님)


def test_answer_large_set_calls_llm_with_bounded_prompt():
    # 타임라인 등 대량 결과도 LLM은 경계 프롬프트 받음(요약 정상). 증거 citations는 전량(무손실).
    from clfx.query.llm import answer
    from clfx.event import Event, Source
    seen = {}
    class Stub:
        def complete(self, p): seen["len"] = len(p); seen["p"] = p; return "요약 산문 (h.jsonl:1)."
    evs = [Event(f"2026-06-11T00:00:{i%60:02d}Z", "claude", "s", "agent", "response", "",
                 f"응답{i}" * 20, Source("h.jsonl", i), []) for i in range(500)]
    out = answer("타임라인 요약해줘", evs, llm=Stub())
    assert out["mode"] == "llm" and "[집계] 총 500건" in seen["p"]
    assert len(out["citations"]) == 500                   # 증거는 전량(무손실)

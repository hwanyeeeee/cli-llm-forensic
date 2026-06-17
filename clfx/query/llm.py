import json
import re
import urllib.request

# read-target 추출 시 파일명으로 오인하면 안 되는 영어 동사/의문사/보조어(한글은 토큰이 아니라 무관)
_FILE_STOP = {
    "read", "reads", "reading", "access", "accessed", "file", "files",
    "who", "what", "when", "where", "why", "how", "whom",
    "did", "does", "do", "anyone", "anybody", "someone", "somebody", "any",
    "has", "have", "had", "was", "were", "is", "are", "am", "be", "been",
    "the", "a", "an", "please", "show", "list", "me", "you", "it",
    "that", "this", "of", "in", "on", "to", "for", "and", "or",
}


def _extract_filename(q):
    """질의에서 path-safe ASCII 파일명 토큰 추출. 한글 조사(.env를)는 ASCII 경계로 자동 분리.
    우선순위: (1) 점 포함 파일(.env/config.py//x/.npmrc),
              (2) 파일명스러운 토큰(_ / - 또는 숫자 포함; id_rsa/my-key) — 영어 filler 배제,
              (3) STOP 아닌 알파벳 토큰(Dockerfile/Makefile)."""
    m = re.search(r"[A-Za-z0-9._/-]*\.[A-Za-z0-9]+", q)   # (1) 확장자/hidden-file
    if m:
        return m.group(0).rstrip(".,);:")
    toks = re.findall(r"[A-Za-z0-9._/-]*[A-Za-z0-9][A-Za-z0-9._/-]*", q)
    for tok in toks:                                       # (2) 특수문자/숫자 포함 = 진짜 파일명스러움
        if tok.lower() not in _FILE_STOP and re.search(r"[_/\-]|\d", tok):
            return tok.rstrip(".,);:")
    for tok in toks:                                       # (3) STOP 아닌 알파벳 단어
        if tok.lower() not in _FILE_STOP:
            return tok.rstrip(".,);:")
    return ""


def route_intent(q):
    """자연어 → 질의 의도(룰 우선; MVP는 룰만으로 충분). LLM은 검색 안 함."""
    ql = q.lower()
    summarize = any(w in ql for w in ("요약", "정리", "summar"))   # ql로 대소문자 무관
    # 주체어 파싱(§3) — 모든 intent에 actor 실음. "누가/who"는 actor=None(전체).
    # 타깃(파일명/경로)을 먼저 뽑아 actor 탐지서 그 span을 제거 → "/tmp/user"·"CLAUDE"·"user.json"이
    # actor 어휘로 오인되어 반대 주체를 누락하는 충돌 차단. ("ai"는 email/main/fail 오탐이라 미사용.)
    tgt = _extract_filename(q)
    actor_text = ql
    if tgt:
        actor_text = actor_text.replace(tgt.lower(), " ")   # 타깃 span 제거
    actor_text = re.sub(r"\S*[./]\S*", " ", actor_text)     # 잔여 경로/파일 토큰(점·슬래시) 제거
    actor = None
    # 한국어: 조사 부착(사용자가) → substring. 영어(user/claude/agent): 파일명 충돌 방지 → 단어경계.
    if ("사용자" in actor_text or "유저" in actor_text or "내가" in actor_text
            or re.search(r"(?:^|\W)user(?:\W|$)", actor_text)):
        actor = "user"
    elif ("에이전트" in actor_text or "클로드" in actor_text or "자동" in actor_text
            or re.search(r"(?:^|\W)(?:claude|agent)(?:\W|$)", actor_text)):
        actor = "agent"
    m = re.search(r"(\d{4}-\d{2}-\d{2})", q)
    if m:
        return {"op": "on_date", "day": m.group(1), "actor": actor, "summarize": summarize}
    if any(w in ql for w in ("타임라인", "timeline", "시간순", "시간 순")):
        return {"op": "timeline", "actor": actor, "summarize": summarize}
    # read 동사가 명시되면 who_did 우선 — 파일명에 secret이 들어가도("누가 .secret.key 읽었어?") read 의도 보존.
    # tgt는 위에서 이미 추출함(재추출 금지·일관).
    if any(w in ql for w in ("읽", "read", "접근", "access")):
        if tgt:
            return {"op": "who_did", "action": "read", "target": tgt, "actor": actor, "summarize": summarize}
        # 명시 target 추출 실패 → broad-match(전체 read 반환) 금지, search 로 폴백.
        return {"op": "search", "kw": q.strip(), "actor": actor, "summarize": summarize}
    if any(w in ql for w in ("비밀", "시크릿", "secret", "유출", "키")):   # ql로 대소문자 무관
        return {"op": "secrets", "actor": actor, "summarize": summarize}
    return {"op": "search", "kw": q.strip(), "actor": actor, "summarize": summarize}


def _digest(events):
    lines = []
    for e in events:
        lines.append(f"- [{e.ts or '?'}] {e.actor}/{e.action} {e.target} "
                     f"({e.source.file}:{e.source.line})")
    return "\n".join(lines) if lines else "(결과 없음)"


def summarize(events, llm=None):
    """결정적으로 검색된 집합만 요약. citations = 실재 source(file:line). LLM 죽으면 digest.
    요약 채점 = 인용 source 실재 + 근거 집합 일치(산문 일치 아님)."""
    citations = [f"{e.source.file}:{e.source.line}" for e in events]
    if llm is None:
        return {"text": _digest(events), "citations": citations, "mode": "digest"}
    try:
        prompt = ("다음 포렌식 이벤트를 사실만으로 요약하라. 각 문장 끝에 (file:line) 인용.\n"
                  + _digest(events))
        text = llm.complete(prompt)
        return {"text": text, "citations": citations, "mode": "llm"}
    except Exception:
        return {"text": _digest(events), "citations": citations, "mode": "digest"}


def answer(question, events, llm=None):
    """사용자 질문에 검색된 이벤트만 근거로 대화형 답변. 증거=엔진(events), 산문=LLM.
    citations=실재 source(file:line). LLM 없거나 실패 시 digest 폴백(항상 답 반환)."""
    citations = [f"{e.source.file}:{e.source.line}" for e in events]
    _none = "관련 기록을 찾지 못했습니다."
    if not events:                                  # 근거 0건 → LLM 호출 안 함(날조/허위 인용 차단)
        # mode="empty"(="digest"와 구분): 빈 결과지 LLM 미연결 아님 → UI가 "LLM 미연결"로 오표기 방지.
        return {"text": _none, "citations": [], "mode": "empty"}
    if llm is None:
        return {"text": _digest(events), "citations": citations, "mode": "digest"}
    try:
        ev = _digest(events)
        prompt = (
            "너는 Claude Code 기록 포렌식 분석가다. 아래 [이벤트]만 근거로 [질문]에 한국어로 답하라.\n"
            "규칙: (1) 이벤트에 없는 사실 추측·날조 금지. (2) 핵심 문장 끝에 (file:line) 인용. "
            "(3) 근거 없으면 '해당 기록을 찾지 못했습니다'. (4) 행위 주체는 A=사용자 / B=에이전트로 구분.\n\n"
            f"[질문]\n{question}\n\n[이벤트]\n{ev}\n"
        )
        return {"text": llm.complete(prompt), "citations": citations, "mode": "llm"}
    except Exception:
        return {"text": (_digest(events) if events else _none), "citations": citations, "mode": "digest"}


def _overview_context(engine):
    """전체 행위의 결정적 집계 컨텍스트(문자열) + 대표 인용. 막연한 질문의 근거.
    모든 수치는 엔진 집계(추적 가능) — LLM은 문장화만, 날조 없음."""
    from clfx.event import norm_ts
    evs = engine.events
    actors = {"user": 0, "agent": 0}
    actions = {}
    for e in evs:
        a = e.actor if e.actor in ("user", "agent") else "user"
        actors[a] += 1
        actions[e.action] = actions.get(e.action, 0) + 1
    top_actions = sorted(actions.items(), key=lambda x: (-x[1], x[0]))[:6]
    top_files = engine.files()[:8]
    se = engine.sorted_events
    span = (f"{norm_ts(se[0].ts)} ~ {norm_ts(se[-1].ts)}" if se else "?")
    lines = [
        f"- 총 이벤트: {len(evs)} (A 사용자 {actors['user']} / B 에이전트 {actors['agent']})",
        f"- 기간: {span}",
        "- 주요 행위(빈도): " + (", ".join(f"{a}×{n}" for a, n in top_actions) or "없음"),
        "- 자주 접근한 파일:",
    ] + [f"  · {f['target']} ({f['count']}회, A{f['by_actor']['user']}/B{f['by_actor']['agent']})"
         for f in top_files]
    citations = [f["target"] for f in top_files]   # 파일 패널서 역추적 가능(집계 근거)
    return "\n".join(lines), citations


def answer_overview(question, engine, llm=None):
    """막연한/개요형 질문(특정 키워드 매칭 0건) → 전체 행위 결정적 집계를 근거로 대화형 답.
    증거=엔진 집계(추적 가능), 산문=LLM. LLM 없거나 실패 시 결정적 개요(digest) 폴백."""
    if not engine.events:
        return {"text": "분석할 기록이 없습니다.", "citations": [], "mode": "empty"}
    ctx, citations = _overview_context(engine)
    digest_text = "전체 행위 개요\n" + ctx
    if llm is None:
        return {"text": digest_text, "citations": citations, "mode": "digest"}
    try:
        prompt = (
            "너는 Claude Code 기록 포렌식 분석가다. 아래 [전체 집계]만 근거로 [질문]에 한국어로 간결히 답하라.\n"
            "규칙: (1) 집계에 없는 사실 추측·날조 금지. (2) 행위 주체는 A=사용자 / B=에이전트로 구분. "
            "(3) 수치는 집계 그대로 인용.\n\n"
            f"[질문]\n{question}\n\n[전체 집계]\n{ctx}\n"
        )
        return {"text": llm.complete(prompt), "citations": citations, "mode": "llm"}
    except Exception:
        return {"text": digest_text, "citations": citations, "mode": "digest"}


class OllamaLLM:
    """로컬 ollama 요약 클라이언트. 증거 외부전송 0(localhost).
    complete()가 실패하면 summarize가 digest로 폴백한다."""

    def __init__(self, model="gemma4:12b", host="http://localhost:11434", timeout=60):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def complete(self, prompt):
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False}).encode("utf-8")
        req = urllib.request.Request(self.host + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("response", "")


def make_llm(use_ollama=True):
    """요약용 LLM 어댑터. ollama 미사용/미실행이면 None(→ summarize가 digest).
    OllamaLLM은 호출 시점에 연결하므로 여기서 살아있는지 검사하지 않는다(complete 실패→fallback)."""
    if not use_ollama:
        return None
    return OllamaLLM()

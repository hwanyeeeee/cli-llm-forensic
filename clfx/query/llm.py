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
    m = re.search(r"(\d{4}-\d{2}-\d{2})", q)            # 완전 날짜 우선
    if m:
        return {"op": "on_date", "day": m.group(1), "actor": actor, "summarize": summarize}
    m2 = re.search(r"(?<!\d)(\d{1,2})\s*[/월]\s*(\d{1,2})", q)   # 6/15, 6월 15(일)
    if m2:
        mm, dd = int(m2.group(1)), int(m2.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:             # 범위 가드(24/7 등 오탐 차단)
            return {"op": "on_date", "day": f"{mm:02d}-{dd:02d}",   # 월-일(연도무관)
                    "actor": actor, "summarize": summarize}
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


def _digest(events, with_preview=False):
    """이벤트 한 줄 요약. with_preview=True면 마스킹된 preview 내용 포함(LLM 입력용 — prompt/response는
    target="" 이라 내용 없으면 빈 껍데기). ‹secret›/‹pii›는 엔진서 이미 마스킹돼 평문 미포함."""
    lines = []
    for e in events:
        base = f"- [{e.ts or '?'}] {e.actor}/{e.action} {e.target}".rstrip()
        if with_preview and e.preview:
            snip = " ".join((e.preview or "").split())[:120]   # 개행 정리 + 120자 경계(컨텍스트 bound)
            if snip:
                base += f": {snip}"
        base += f" ({e.source.file}:{e.source.line})"
        lines.append(base)
    return "\n".join(lines) if lines else "(결과 없음)"


_MAX_LLM_EVENTS = 60


def _prompt_context(events):
    """LLM 프롬프트용 컨텍스트(경계). 대량이면 [집계 헤더]+표본 N건 → 전량 덤프(타임아웃/컨텍스트초과) 차단.
    증거(UI 반환 events)는 호출부에서 전량 유지 — 여기선 산문 입력만 경계(무손실)."""
    n = len(events)
    if n <= _MAX_LLM_EVENTS:
        return _digest(events, with_preview=True)        # ← 실제 내용(마스킹 preview) 포함
    actors = {"user": 0, "agent": 0}
    actions = {}
    for e in events:
        a = e.actor if e.actor in ("user", "agent") else "user"
        actors[a] += 1
        actions[e.action] = actions.get(e.action, 0) + 1
    top = sorted(actions.items(), key=lambda x: (-x[1], x[0]))[:6]
    head = (f"[집계] 총 {n}건 (A 사용자 {actors['user']} / B 에이전트 {actors['agent']}). "
            "행위: " + ", ".join(f"{a}×{c}" for a, c in top) +
            f"\n[표본 앞 {_MAX_LLM_EVENTS}건]\n")
    return head + _digest(events[:_MAX_LLM_EVENTS], with_preview=True)   # ← 내용 포함


def summarize(events, llm=None):
    """결정적으로 검색된 집합만 요약. citations = 실재 source(file:line). LLM 죽으면 digest.
    요약 채점 = 인용 source 실재 + 근거 집합 일치(산문 일치 아님)."""
    citations = [f"{e.source.file}:{e.source.line}" for e in events]   # 증거=전량(무손실)
    if llm is None:
        return {"text": _prompt_context(events), "citations": citations, "mode": "digest"}
    try:
        ctx = _prompt_context(events)   # 내용 포함(마스킹 preview). 대량=집계+표본 경계. citations는 전량.
        prompt = "다음 포렌식 이벤트를 사실만으로 요약하라. 각 문장 끝에 (file:line) 인용.\n" + ctx
        text = llm.complete(prompt)
        if text and text.strip():
            return {"text": text, "citations": citations, "mode": "llm"}
        return {"text": ctx, "citations": citations, "mode": "digest", "llm_error": "빈 응답"}   # 빈 응답 폴백
    except Exception as e:
        return {"text": _prompt_context(events), "citations": citations,
                "mode": "digest", "llm_error": str(e)[:200]}


def answer(question, events, llm=None):
    """사용자 질문에 검색된 이벤트만 근거로 대화형 답변. 증거=엔진(events), 산문=LLM.
    citations=실재 source(file:line). LLM 없거나 실패 시 digest 폴백(항상 답 반환)."""
    citations = [f"{e.source.file}:{e.source.line}" for e in events]
    _none = "관련 기록을 찾지 못했습니다."
    if not events:                                  # 근거 0건 → LLM 호출 안 함(날조/허위 인용 차단)
        # mode="empty"(="digest"와 구분): 빈 결과지 LLM 미연결 아님 → UI가 "LLM 미연결"로 오표기 방지.
        return {"text": _none, "citations": [], "mode": "empty"}
    if llm is None:
        return {"text": _prompt_context(events), "citations": citations, "mode": "digest"}
    try:
        ev = _prompt_context(events)   # 내용 포함(마스킹 preview). 대량은 집계+표본 경계. 증거 citations는 전량.
        prompt = (
            "너는 Claude Code 기록 포렌식 분석가다. 아래 [이벤트]만 근거로 [질문]에 한국어 자연어로 답하라.\n"
            "규칙: (1) '~했습니다' 식 서술형 문장으로 행위를 요약(목록 나열 금지). (2) 이벤트에 없는 사실 추측·날조 금지. "
            "(3) 핵심 근거 끝에 (file:line) 인용. (4) 행위 주체는 A=사용자 / B=에이전트로 구분.\n\n"
            f"[질문]\n{question}\n\n[이벤트]\n{ev}\n"
        )
        text = llm.complete(prompt)
        if text and text.strip():
            return {"text": text, "citations": citations, "mode": "llm"}
        # 빈 응답 → 결정적 내용 폴백(자연어 아니어도 빈 "결과 N건"보다 정보 많음)
        return {"text": ev, "citations": citations, "mode": "digest", "llm_error": "빈 응답"}
    except Exception as e:
        return {"text": (_prompt_context(events) if events else _none), "citations": citations,
                "mode": "digest", "llm_error": str(e)[:200]}


def _overview_context(events):
    """이벤트 리스트의 결정적 집계 컨텍스트(문자열) + 대표 인용. 막연한 질문의 근거(소스 필터된 부분집합 받음).
    모든 수치는 집계(추적 가능) — LLM은 문장화만, 날조 없음."""
    from clfx.event import norm_ts
    FILE_ACTIONS = ("read", "write", "paste", "upload")
    actors = {"user": 0, "agent": 0}
    actions = {}
    fcount = {}
    fact = {}
    times = []
    for e in events:
        a = e.actor if e.actor in ("user", "agent") else "user"
        actors[a] += 1
        actions[e.action] = actions.get(e.action, 0) + 1
        nt = norm_ts(e.ts)
        if nt:
            times.append(nt)
        if e.action in FILE_ACTIONS and e.target:
            fcount[e.target] = fcount.get(e.target, 0) + 1
            d = fact.setdefault(e.target, {"user": 0, "agent": 0})
            d[a] += 1
    top_actions = sorted(actions.items(), key=lambda x: (-x[1], x[0]))[:6]
    top_files = sorted(fcount.items(), key=lambda x: (-x[1], x[0]))[:8]
    span = (f"{min(times)} ~ {max(times)}" if times else "?")
    lines = [
        f"- 총 이벤트: {len(events)} (A 사용자 {actors['user']} / B 에이전트 {actors['agent']})",
        f"- 기간: {span}",
        "- 주요 행위(빈도): " + (", ".join(f"{a}×{n}" for a, n in top_actions) or "없음"),
        "- 자주 접근한 파일:",
    ] + [f"  · {t} ({c}회, A{fact[t]['user']}/B{fact[t]['agent']})" for t, c in top_files]
    return "\n".join(lines), [t for t, _ in top_files]   # 파일 패널서 역추적 가능(집계 근거)


def answer_overview(question, events, llm=None):
    """막연한/개요형 질문(특정 키워드 매칭 0건) → 주어진 이벤트(소스 필터 가능) 결정적 집계 근거로 대화형 답.
    증거=집계(추적 가능), 산문=LLM. LLM 없거나 실패 시 결정적 개요(digest) 폴백."""
    if not events:
        return {"text": "분석할 기록이 없습니다.", "citations": [], "mode": "empty"}
    ctx, citations = _overview_context(events)
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
    except Exception as e:
        return {"text": digest_text, "citations": citations,
                "mode": "digest", "llm_error": str(e)[:200]}


class OllamaLLM:
    """로컬 ollama 요약 클라이언트. 증거 외부전송 0(localhost).
    complete()가 실패하면 summarize가 digest로 폴백한다."""

    def __init__(self, model="gemma4:12b", host="http://127.0.0.1:11434", timeout=300):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def complete(self, prompt):
        # /api/chat 사용 — 인스트럭트 모델의 채팅 템플릿을 ollama가 적용(/api/generate raw 프롬프트는
        # 템플릿 미적용으로 빈 생성될 수 있음). content 비면 thinking 폴백, 그래도 비면 진단 에러.
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": "30m",                 # 모델 상주(다음 쿼리 콜드로드 제거)
            "options": {"num_predict": 384},     # 출력 경계 → 생성시간 bound(timed out 완화)
        }).encode("utf-8")
        req = urllib.request.Request(self.host + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        msg = data.get("message") or {}
        content = (msg.get("content") or "").strip()
        if content:
            return content
        thinking = (msg.get("thinking") or "").strip()   # 일부 reasoning 모델은 답을 thinking에 둠
        if thinking:
            return thinking
        # 빈 content → 응답 구조를 에러로 표면화(answer가 llm_error로 라벨에 띄움 → 원인 파악)
        raise RuntimeError(f"ollama empty: msg_keys={list(msg.keys())} top_keys={list(data.keys())}")


def prewarm(model="gemma4:12b", host="http://127.0.0.1:11434"):
    """모델을 백그라운드로 미리 로드(콜드로드를 쿼리 경로서 제거). 실패는 무시(ollama 없어도 무해)."""
    try:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": "ok"}],
                           "stream": False, "keep_alive": "30m",
                           "options": {"num_predict": 1}}).encode("utf-8")
        req = urllib.request.Request(host.rstrip("/") + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=300).read()
    except Exception:
        pass


def make_llm(use_ollama=True):
    """요약용 LLM 어댑터. ollama 미사용/미실행이면 None(→ summarize가 digest).
    OllamaLLM은 호출 시점에 연결하므로 여기서 살아있는지 검사하지 않는다(complete 실패→fallback)."""
    if not use_ollama:
        return None
    return OllamaLLM()

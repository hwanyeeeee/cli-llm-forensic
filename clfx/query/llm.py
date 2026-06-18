import json
import re
import urllib.request
from urllib.parse import urlparse

# 로컬 전용(증거 외부전송 하드제약) — ollama host는 이 호스트만 허용.
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _check_host(host):
    """ollama host를 localhost/127.0.0.1만 allowlist. 그 외(원격)면 거부 → 증거 외부전송 차단(P0)."""
    h = urlparse(host if "://" in host else "http://" + host).hostname
    if h not in _ALLOWED_HOSTS:
        raise ValueError(f"ollama host는 로컬만 허용(증거 외부전송 차단) — got {h!r}")
    return host


def _ko_ok(text):
    """중국어 이탈 감지 — 한자(CJK)가 많고 한글 대비 비율 높으면 False(qwen 언어 드리프트 차단).
    한국어 텍스트의 간헐적 한자는 허용(임계 han>=8 & han>hangul*0.25)."""
    han = len(re.findall(r"[一-鿿]", text or ""))
    hangul = len(re.findall(r"[가-힣]", text or ""))
    return not (han >= 8 and han > hangul * 0.25)


_CITE_TOKEN = re.compile(r"([\w.\-/\\]+):(\d+(?:-\d+)?)")


def _valid_lines(citations):
    """citations('file:line') → {basename|fullpath: {정수 줄번호}}. 산문 인용 검증용."""
    by = {}
    for c in citations:
        i = c.rfind(":")
        if i < 0 or not c[i + 1:].isdigit():
            continue
        f, ln = c[:i], int(c[i + 1:])
        base = re.split(r"[\\/]", f)[-1]
        by.setdefault(base, set()).add(ln)
        by.setdefault(f, set()).add(ln)
    return by


def _strip_fake_citations(text, citations):
    """LLM 산문 속 (파일:줄) 인라인 인용 중 결정적 citations에 없는 것(허위/날조)을 통째 제거(P0).
    범위(12-13)는 양끝 모두 실재해야 유지. 증거 배열(citations)은 별도 유지 — 표시만 정화."""
    if not text:
        return text
    valid = _valid_lines(citations)

    def ok(fileref, linespec):
        cand = valid.get(re.split(r"[\\/]", fileref)[-1]) or valid.get(fileref)
        if not cand:
            return False
        try:
            return all(int(p) in cand for p in linespec.split("-"))
        except ValueError:
            return False

    def fix(m):
        inner = m.group(1)
        for fm in _CITE_TOKEN.finditer(inner):
            if not ok(fm.group(1), fm.group(2)):
                return ""        # 인용 하나라도 허위면 괄호 통째 제거(포렌식: 보수적)
        return m.group(0)

    out = re.sub(r"\s*\(([^()]*?:\d[^()]*)\)", fix, text)
    return re.sub(r"[ \t]{2,}", " ", out).strip()

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
    # bypass(우회권한) 모드 질의 → bypass op. "읽은/read" 동사가 섞여도("bypass 모드로 읽은 파일?")
    # who_did/secrets로 새지 않게 read·secrets 분기보다 먼저 매칭.
    if "bypass" in ql:
        return {"op": "bypass", "actor": actor, "summarize": summarize}
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


# 검색어 토큰화 불용어(질문 필러·지시어·범용 대화어). 의미 키워드(인물/파일명 등)만 남긴다.
_KW_STOP = {
    "요약", "요약해줘", "정리", "정리해줘", "개요", "구체적으로", "구체적", "어떤", "무슨", "무엇", "뭐", "뭔",
    "내용", "대해", "대해서", "관해", "관해서", "관련", "많이", "대화", "대화를", "대화한", "대화한건지",
    "했다고", "했는지", "했던", "하는지", "뜨는데", "보여줘", "알려줘", "찾아줘", "말해줘", "해줘", "줘",
    "키워드", "키워드로", "이라는", "라는", "라고", "사람", "주로", "했어", "하는", "한건지",
    "그리고", "이거", "그거", "저거", "이런", "저런", "이", "그", "저", "좀", "것", "수", "때", "건지",
    "에서", "으로", "에게", "에", "을", "를", "은", "는", "이라", "라",
    "summary", "summarize", "about", "what", "content", "the", "please", "show", "tell", "did", "do",
}


def search_terms(q):
    """긴 질문에서 의미 키워드 토큰만 추출(불용어·필러 제거). substring 통검색 실패 시 OR 재검색용."""
    toks = re.findall(r"[A-Za-z0-9._/\-]{2,}|[가-힣]{2,}", q or "")
    seen, out = set(), []
    for t in toks:
        if t.lower() in _KW_STOP or t in _KW_STOP:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


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
        system = (
            "당신은 디지털 포렌식 분석가입니다. 반드시 한국어로만 답하고, 중국어·영어 등 다른 언어는 한 글자도 쓰지 않습니다. 주어진 이벤트를 사실만으로 한국어 서술형 문단으로 요약합니다.\n"
            "목록·영어·지시문 반복 금지. 각 핵심 문장 끝에 (파일명:줄) 인용."
        )
        user = f"[이벤트]\n{ctx}\n\n한국어 서술형 문단으로 요약:"
        text = _strip_fake_citations(llm.complete(user, system=system), citations)
        if text and text.strip() and _ko_ok(text):
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
        system = (
            "당신은 디지털 포렌식 분석가입니다. 반드시 한국어로만 답하고, 중국어·영어 등 다른 언어는 한 글자도 쓰지 않습니다. 사용자의 [질문]에 대해 주어진 [이벤트] 로그만 근거로 답합니다.\n"
            "규칙:\n"
            "1. 한국어 자연어 서술형 문단(목록·불릿·번호·표·영어 금지).\n"
            "2. '다음은', '주요 내용을 바탕으로', '서술형 문단입니다' 같은 도입부·메타 문장을 절대 쓰지 말고, "
            "질문의 주제를 언급하며 바로 시작한다. 예: '○○에 대해서는 다음과 같은 대화를 진행했습니다. …'\n"
            "3. 데이터의 형식·구조·일관성을 논하거나 이벤트 ID·통계·분포를 언급·날조하지 않는다. "
            "오직 사용자와 에이전트가 실제로 무엇을 했는지(대화·행위 내용)만 서술한다.\n"
            "4. 이벤트에 없는 사실은 추측·날조하지 않는다. 행위 주체는 A=사용자, B=에이전트로 구분한다.\n"
            "5. 핵심 근거 문장 끝에 (파일명:줄) 형식으로 인용한다.\n"
            "6. 질문과 관련된 내용이 이벤트에 없으면 '관련 대화를 찾지 못했습니다.'라고만 답한다."
        )
        user = f"[질문]\n{question}\n\n[이벤트]\n{ev}\n\n'{question}'에 대해, 질문 주제를 언급하며 시작하는 한국어 한 문단으로 답:"
        text = _strip_fake_citations(llm.complete(user, system=system), citations)
        if text and text.strip() and _ko_ok(text):
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
    fsrc = {}      # target -> "source.file:source.line" 대표(첫 등장) — citations용(P0: target명 아님)
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
            if e.target not in fsrc and getattr(e, "source", None):
                fsrc[e.target] = f"{e.source.file}:{e.source.line}"
    top_actions = sorted(actions.items(), key=lambda x: (-x[1], x[0]))[:6]
    top_files = sorted(fcount.items(), key=lambda x: (-x[1], x[0]))[:8]
    span = (f"{min(times)} ~ {max(times)}" if times else "?")
    lines = [
        f"- 총 이벤트: {len(events)} (A 사용자 {actors['user']} / B 에이전트 {actors['agent']})",
        f"- 기간: {span}",
        "- 주요 행위(빈도): " + (", ".join(f"{a}×{n}" for a, n in top_actions) or "없음"),
        "- 자주 접근한 파일:",
    ] + [f"  · {t} ({c}회, A{fact[t]['user']}/B{fact[t]['agent']})" for t, c in top_files]
    # citations = source(file:line) — 파일패널 역추적 계약 충족(top_files 파일명은 본문 근거로만).
    cites = [fsrc[t] for t, _ in top_files if t in fsrc]
    if not cites:        # 파일 행위 없으면(전부 prompt 등) 대표 이벤트 source로 폴백 — 빈 citations 방지
        cites = [f"{e.source.file}:{e.source.line}" for e in events[:8] if getattr(e, "source", None)]
    return "\n".join(lines), cites


def _top_terms(events, k):
    """대화(prompt/response) preview에서 의미 토큰 상위 k개(불용어·숫자·단글자 제외)."""
    from collections import Counter
    c = Counter()
    for e in events:
        if e.action not in ("prompt", "response"):
            continue
        for t in re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{1,}|[가-힣]{2,}", e.preview or ""):
            tl = t.lower()
            if tl in _KW_STOP or t in _KW_STOP or len(tl) < 2 or tl.isdigit():
                continue
            c[t] += 1
    return [w for w, _ in c.most_common(k)]


def _timeline_context(events):
    """시간순 3분할(초기/중간/최근) — 시기별 기간·주요 키워드·예시 질문. 타임라인 흐름 서술 근거."""
    from clfx.event import ts_key, norm_ts
    evs = [e for e in events if e.ts]
    evs = sorted(evs, key=lambda e: ts_key(e.ts))
    if not evs:
        return ""
    n = len(evs)
    third = max(1, n // 3)
    groups = [("초기", evs[:third]), ("중간", evs[third:2 * third]), ("최근", evs[2 * third:])]
    lines = []
    for label, grp in groups:
        if not grp:
            continue
        d0 = (norm_ts(grp[0].ts) or "")[:10]
        d1 = (norm_ts(grp[-1].ts) or "")[:10]
        kws = _top_terms(grp, 6)
        prompts = [" ".join((e.preview or "").split())[:42]
                   for e in grp if e.action == "prompt" and e.preview][:2]
        line = f"[{label} {d0}~{d1}] 주요 키워드: " + (", ".join(kws) or "없음")
        if prompts:
            line += " · 예시 질문: " + " / ".join(prompts)
        lines.append(line)
    return "\n".join(lines)


def answer_timeline(question, events, llm=None):
    """타임라인 요약 → 시간 흐름(초기→최근) 대화 주제 변화를 한 문단으로. LLM 실패 시 시기별 digest."""
    citations = [f"{e.source.file}:{e.source.line}" for e in events]
    if not events:
        return {"text": "분석할 기록이 없습니다.", "citations": [], "mode": "empty"}
    ctx = _timeline_context(events)
    digest = "시기별 대화 흐름\n" + ctx
    if llm is None:
        return {"text": digest, "citations": citations, "mode": "digest"}
    try:
        system = (
            "당신은 디지털 포렌식 분석가입니다. 반드시 한국어로만 답하고, 중국어·영어 등 다른 언어는 한 글자도 쓰지 않습니다. 주어진 [시기별 요약]만 근거로 시간 흐름에 따른 "
            "대화 주제 변화를 한국어 한 문단으로 서술합니다.\n"
            "'다음은' 같은 도입부·메타 문장, 목록·영어·지시문 반복, 이벤트 ID·통계·데이터 구조 언급 금지.\n"
            "'초기에는 주로 ~에 관한 대화를 나누었고, 이후 ~를 다루었으며, 최근에는 ~에 대해 논의했습니다' "
            "형식으로 시기별 주요 주제를 자연스럽게 잇는다. 행위 주체 A=사용자/B=에이전트."
        )
        user = f"[시기별 요약]\n{ctx}\n\n시간 순(초기→최근)으로 대화 주제 변화를 한 문단으로 서술:"
        text = _strip_fake_citations(llm.complete(user, system=system), citations)
        if text and text.strip() and _ko_ok(text):
            return {"text": text, "citations": citations, "mode": "llm"}
        return {"text": digest, "citations": citations, "mode": "digest", "llm_error": "빈 응답"}
    except Exception as e:
        return {"text": digest, "citations": citations, "mode": "digest", "llm_error": str(e)[:200]}


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
        system = (
            "당신은 디지털 포렌식 분석가입니다. 반드시 한국어로만 답하고, 중국어·영어 등 다른 언어는 한 글자도 쓰지 않습니다. 주어진 [전체 집계]만 근거로 한국어 서술형 문단으로 간결히 답합니다.\n"
            "'다음은' 같은 도입부·메타 문장, 목록·영어·지시문 반복 금지. 질문 주제를 언급하며 바로 시작한다.\n"
            "추측·날조 금지. 행위 주체 A=사용자/B=에이전트. 수치는 집계 그대로.\n"
            "데이터 형식·구조·일관성을 논하거나 이벤트 ID·숫자를 지어내지 말 것. "
            "오직 '사용자와 에이전트가 무엇을 했는지' 행위 중심으로만 서술한다."
        )
        user = f"[질문]\n{question}\n\n[전체 집계]\n{ctx}\n\n한국어 서술형 문단으로 답변:"
        text = _strip_fake_citations(llm.complete(user, system=system), citations)
        if text and text.strip() and _ko_ok(text):
            return {"text": text, "citations": citations, "mode": "llm"}
        return {"text": digest_text, "citations": citations, "mode": "digest", "llm_error": "빈 응답"}
    except Exception as e:
        return {"text": digest_text, "citations": citations,
                "mode": "digest", "llm_error": str(e)[:200]}


class OllamaLLM:
    """로컬 ollama 요약 클라이언트. 증거 외부전송 0(localhost).
    complete()가 실패하면 summarize가 digest로 폴백한다."""

    def __init__(self, model="qwen2.5:7b", host="http://127.0.0.1:11434", timeout=300):
        self.model = model
        self.host = _check_host(host).rstrip("/")   # 로컬만 허용(증거 외부전송 차단·P0)
        self.timeout = timeout

    def complete(self, prompt, system=None):
        # /api/chat 사용 — 인스트럭트 모델의 채팅 템플릿을 ollama가 적용(/api/generate raw 프롬프트는
        # 템플릿 미적용으로 빈 생성될 수 있음). system(역할·규칙)↔user(질문·데이터) 분리 → 지시 무시·영어 echo 방지.
        # content 비면 thinking 폴백, 그래도 비면 진단 에러.
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",                 # 모델 상주(다음 쿼리 콜드로드 제거)
            "options": {"num_predict": 512, "temperature": 0},  # 출력 경계 + 결정성(I2)·지시준수↑
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


def prewarm(model="qwen2.5:7b", host="http://127.0.0.1:11434"):
    """모델을 백그라운드로 미리 로드(콜드로드를 쿼리 경로서 제거). 실패는 무시(ollama 없어도 무해)."""
    try:
        _check_host(host)        # 로컬만(P0)
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

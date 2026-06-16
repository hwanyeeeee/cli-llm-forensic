import re

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
    m = re.search(r"(\d{4}-\d{2}-\d{2})", q)
    if m:
        return {"op": "on_date", "day": m.group(1), "summarize": summarize}
    if any(w in ql for w in ("타임라인", "timeline", "시간순", "시간 순")):
        return {"op": "timeline", "summarize": summarize}
    # read 동사가 명시되면 who_did 우선 — 파일명에 secret이 들어가도("누가 .secret.key 읽었어?") read 의도 보존.
    if any(w in ql for w in ("읽", "read", "접근", "access")):
        tgt = _extract_filename(q)
        if tgt:
            return {"op": "who_did", "action": "read", "target": tgt, "summarize": summarize}
        # 명시 target 추출 실패 → broad-match(전체 read 반환) 금지, search 로 폴백.
        return {"op": "search", "kw": q.strip(), "summarize": summarize}
    if any(w in ql for w in ("비밀", "시크릿", "secret", "유출", "키")):   # ql로 대소문자 무관
        return {"op": "secrets", "summarize": summarize}
    return {"op": "search", "kw": q.strip(), "summarize": summarize}


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

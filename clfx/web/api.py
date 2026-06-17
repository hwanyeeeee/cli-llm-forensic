"""웹 대시보드용 순수 API 로직. HTTP 무관 — dict만 반환해 테스트가 쉽다.
엔진(QueryEngine)이 단일 진실원천. 여기서 검색/탐지 로직을 재구현하지 않는다."""
from clfx.query.llm import route_intent, summarize, make_llm
from clfx.analyze.keywords import keyword_stats
from clfx.event import norm_ts


def events_payload(engine):
    """전체 이벤트를 ts 정렬해 직렬화(초기 타임라인용).
    경계서 ts를 norm_ts로 통일(I1) — analyzed.jsonl에 epoch-ms int 섞여도 항상 ISO str/None →
    app.js slice/includes 안전(int ts crash 차단). timeline() 정렬 계약은 유지."""
    out = []
    for e in engine.timeline():
        d = e.to_dict()
        d["ts"] = norm_ts(d.get("ts"))
        out.append(d)
    return {"events": out, "count": len(out)}


def query_payload(engine, q):
    """자연어 질의 → op 판정(route_intent) → engine 실행 → dict.
    이 디스패치가 op→engine 매핑의 단일 진실원천(cli.cmd_query도 이걸 쓴다)."""
    intent = route_intent(q)
    op = intent["op"]
    a = intent.get("actor")               # §3: 주체 필터(None=전체)
    if op == "who_did":
        res = engine.who_did(intent["action"], intent.get("target", ""), actor=a)
    elif op == "secrets":
        res = engine.secrets(actor=a)
    elif op == "on_date":
        res = engine.on_date(intent["day"], actor=a)
    elif op == "timeline":
        res = engine.timeline(actor=a)
    else:
        res = engine.search(intent.get("kw", ""), actor=a)
    summary = summarize(res, llm=make_llm()) if intent.get("summarize") else None
    return {"op": op, "intent": intent, "actor": a,
            "events": [e.to_dict() for e in res], "count": len(res),
            "summary": summary}


def activity_payload(engine, by="day"):
    """활동량 집계 — UI 히트맵용. actor 분리(④)."""
    by = by if by in ("day", "month") else "day"
    return {"by": by, "rows": engine.activity(by=by)}


def files_payload(engine):
    """접근파일 목록 — UI 파일패널용. actor 분리(③④)."""
    return {"files": engine.files()}


def keywords_payload(engine):
    """키워드 빈도 집계 — UI 도넛용(⑥). 결정적, 수사사전·패턴 포함."""
    return keyword_stats(engine.events)

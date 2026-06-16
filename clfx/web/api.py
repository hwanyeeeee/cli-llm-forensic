"""웹 대시보드용 순수 API 로직. HTTP 무관 — dict만 반환해 테스트가 쉽다.
엔진(QueryEngine)이 단일 진실원천. 여기서 검색/탐지 로직을 재구현하지 않는다."""
from clfx.query.llm import route_intent, summarize


def events_payload(engine):
    """전체 이벤트를 ts 정렬해 직렬화(초기 타임라인용)."""
    evs = engine.timeline()
    return {"events": [e.to_dict() for e in evs], "count": len(evs)}


def query_payload(engine, q):
    """자연어 질의 → op 판정(route_intent) → engine 실행 → dict.
    이 디스패치가 op→engine 매핑의 단일 진실원천(cli.cmd_query도 이걸 쓴다)."""
    intent = route_intent(q)
    op = intent["op"]
    if op == "who_did":
        res = engine.who_did(intent["action"], intent.get("target", ""))
    elif op == "secrets":
        res = engine.secrets()
    elif op == "on_date":
        res = engine.on_date(intent["day"])
    elif op == "timeline":
        res = engine.timeline()
    else:
        res = engine.search(intent.get("kw", ""))
    summary = summarize(res, llm=None) if intent.get("summarize") else None
    return {"op": op, "intent": intent,
            "events": [e.to_dict() for e in res], "count": len(res),
            "summary": summary}

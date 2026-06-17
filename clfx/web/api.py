"""웹 대시보드용 순수 API 로직. HTTP 무관 — dict만 반환해 테스트가 쉽다.
엔진(QueryEngine)이 단일 진실원천. 여기서 검색/탐지 로직을 재구현하지 않는다."""
from concurrent.futures import ThreadPoolExecutor, as_completed

from clfx.query.llm import route_intent, summarize, answer, make_llm
from clfx.analyze.keywords import keyword_stats
from clfx.event import norm_ts
from clfx.sources.claude import ClaudeSource
from clfx.analyze.attribution import enrich
from clfx.query.engine import QueryEngine
# parse_roots(cli)·discover_sources(discover)는 함수-지역 import — cli↔web.api 순환 회피.

_DEFAULT_LLM = object()   # query_payload llm 미지정 센티넬 — 웹은 make_llm(), CLI/테스트는 llm=None로 ollama 비호출.


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


def query_payload(engine, q, llm=_DEFAULT_LLM, answer_only_summary=False):
    """자연어 질의 → op 판정(route_intent) → engine 실행 → dict.
    이 디스패치가 op→engine 매핑의 단일 진실원천(cli.cmd_query도 이걸 쓴다).
    llm 미지정=make_llm()(웹 copilot, 항상 gemma4 답). llm=None=digest(테스트, ollama 비호출).
    answer_only_summary=True면 요약 intent에만 answer(CLI용 — 비요약은 LLM 비호출·summary None)."""
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
    if answer_only_summary and not intent.get("summarize"):
        summary = None                            # CLI 비요약 → LLM/답 없음(make_llm 비호출)
    else:
        use_llm = make_llm() if llm is _DEFAULT_LLM else llm   # 웹=gemma4 / 테스트(llm=None)=digest
        summary = answer(q, res, llm=use_llm)     # 검색된 res만 근거. ollama 없으면 digest.
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


def scan_to_engine(roots, on_progress=None):
    """선택 루트들을 병렬 parse+analyze(인메모리) → QueryEngine. 디스크 analyzed.jsonl 불요.
    per-root enrich: bypass 세션은 같은 소스 transcript에서만 매칭(멀티루트 정합).
    WSL UNC I/O가 느려 스레드 병렬. 병합은 입력 루트 순서로 결정적(as_completed는 진행 보고용일 뿐,
    events 순서에 영향 X → I2: search/who_did/secrets는 raw 순서 반환이라 run마다 인용 순서 고정 필요).
    on_progress(done, total, events, current_root): 매 루트 완료 시 호출(옵션)."""
    from clfx.cli import parse_roots         # 지역 import — cli↔web.api 순환 회피

    def _one(root):
        evs = parse_roots([root])           # 태그된 단일 루트
        enrich(evs, ClaudeSource(root))     # src=그 루트 → bypass 세션 정합
        return evs

    roots = list(roots)
    if not roots:
        if on_progress:
            on_progress(0, 0, 0, None)
        return QueryEngine([])
    total = len(roots)
    results = [None] * total
    done = 0
    with ThreadPoolExecutor(max_workers=min(8, total)) as ex:
        futs = {ex.submit(_one, r): i for i, r in enumerate(roots)}
        for fut in as_completed(futs):      # 완료 순(진행 보고) — 결과는 인덱스 슬롯에 저장
            i = futs[fut]
            results[i] = fut.result(); done += 1
            if on_progress:
                ev = sum(len(x) for x in results if x is not None)
                on_progress(done, total, ev, roots[i])
    events = []
    for evs in results:                     # 입력 루트 순서로 결정적 병합(I2)
        events.extend(evs)
    return QueryEngine(events)


def sources_payload():
    """자동탐지 소스 중 실재(exists)만 — 없는 후보는 화면에 안 보이게. discover_sources는 전체+exists 반환."""
    from clfx.discover import discover_sources   # 지역 import — discover→cli→web.api 순환 회피
    return {"sources": [s for s in discover_sources() if s["exists"]]}

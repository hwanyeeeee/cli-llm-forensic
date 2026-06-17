"""웹 대시보드용 순수 API 로직. HTTP 무관 — dict만 반환해 테스트가 쉽다.
엔진(QueryEngine)이 단일 진실원천. 여기서 검색/탐지 로직을 재구현하지 않는다."""
import threading
from concurrent.futures import ThreadPoolExecutor

from clfx.query.llm import route_intent, summarize, answer, answer_overview, make_llm
from clfx.analyze.keywords import keyword_stats
from clfx.event import norm_ts
from clfx.sources.claude import ClaudeSource
from clfx.analyze.attribution import enrich
from clfx.query.engine import QueryEngine
# parse_roots(cli)·discover_sources(discover)는 함수-지역 import — cli↔web.api 순환 회피.

_DEFAULT_LLM = object()   # query_payload llm 미지정 센티넬 — 웹은 make_llm(), CLI/테스트는 llm=None로 ollama 비호출.


def events_payload(engine):
    """전체 이벤트를 ts 정렬해 직렬화(초기 타임라인용). 엔진 메모이즈(재요청 시 풀스캔 회피).
    경계서 ts를 norm_ts로 통일(I1) — analyzed.jsonl에 epoch-ms int 섞여도 항상 ISO str/None →
    app.js slice/includes 안전(int ts crash 차단). timeline() 정렬 계약은 유지."""
    def _build():
        out = []
        for e in engine.timeline():        # sorted_events 캐시 사용
            d = e.to_dict()
            d["ts"] = norm_ts(d.get("ts"))
            out.append(d)
        return {"events": out, "count": len(out)}
    return engine._memo("events_payload", _build)


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
        if op == "search" and not res:
            # 막연한 대화형 질문(특정 키워드 매칭 0건) → 전체 행위 개요로 답(결정적 집계 근거).
            summary = answer_overview(q, engine, llm=use_llm)
        else:
            summary = answer(q, res, llm=use_llm) # 검색된 res만 근거. ollama 없으면 digest.
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
    """키워드 빈도 집계 — UI 도넛용(⑥). 결정적, 수사사전·패턴 포함. 엔진 메모이즈(재요청 풀스캔 회피)."""
    return engine._memo("keywords", lambda: keyword_stats(engine.events))


def scan_to_engine(roots, on_progress=None):
    """선택 루트들을 병렬 parse+analyze(인메모리) → QueryEngine. 디스크 analyzed.jsonl 불요.
    per-root enrich: bypass 세션은 같은 소스 transcript에서만 매칭(멀티루트 정합).
    on_progress(files_done, files_total, events, current_root): 진행=파일 단위
    (parse: history+transcript, enrich: transcript 재읽기 둘 다 카운트 → UNC 느린 패스도 매끄럽게).
    병합은 입력 루트 순서로 결정적(I2: search/who_did/secrets는 raw 순서 반환 → run마다 인용 순서 고정)."""
    from clfx.cli import parse_source_tagged   # 지역 import — cli↔web.api 순환 회피

    roots = list(roots)
    if not roots:
        if on_progress:
            on_progress(0, 0, 0, None)
        return QueryEngine([])
    # 사전 카운트: 각 루트 parse 파일수(jsonl_files) + enrich 재읽기(transcript_files)
    total_files = 0
    for r in roots:
        probe = ClaudeSource(r)
        total_files += len(probe.jsonl_files()) + len(probe.transcript_files())
    if on_progress:
        on_progress(0, total_files, 0, None)     # 즉시 0/N 표시
    lock = threading.Lock()
    prog = {"files": 0, "events": 0}

    def _one(item):
        i, root = item

        def incr(_path):
            with lock:
                prog["files"] += 1
                f, ev = prog["files"], prog["events"]
            if on_progress:
                on_progress(f, total_files, ev, root)

        src = ClaudeSource(root, on_file=incr)
        evs = parse_source_tagged(src, root)     # parse 패스(on_file 발화)
        enrich(evs, src)                         # enrich 패스(같은 src 재사용 → transcript 재읽기 카운트)
        with lock:
            prog["events"] += len(evs)
            f, ev = prog["files"], prog["events"]
        if on_progress:
            on_progress(f, total_files, ev, root)   # 루트 완료 — 누적 events 반영(on_file은 파싱 중 events=0)
        return i, evs

    results = [None] * len(roots)
    with ThreadPoolExecutor(max_workers=min(8, len(roots))) as ex:
        for i, evs in ex.map(_one, list(enumerate(roots))):
            results[i] = evs
    events = []
    for evs in results:                          # 입력 루트 순서 결정적 병합(I2)
        events.extend(evs)
    return QueryEngine(events)


def sources_payload():
    """자동탐지 소스 중 실재(exists)만 — 없는 후보는 화면에 안 보이게. discover_sources는 전체+exists 반환."""
    from clfx.discover import discover_sources   # 지역 import — discover→cli→web.api 순환 회피
    return {"sources": [s for s in discover_sources() if s["exists"]]}

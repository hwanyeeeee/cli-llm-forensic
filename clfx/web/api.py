"""웹 대시보드용 순수 API 로직. HTTP 무관 — dict만 반환해 테스트가 쉽다.
엔진(QueryEngine)이 단일 진실원천. 여기서 검색/탐지 로직을 재구현하지 않는다."""
import threading
from concurrent.futures import ThreadPoolExecutor

from clfx.query.llm import route_intent, summarize, answer, answer_overview, answer_timeline, make_llm, search_terms
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


def _origin_of(e):
    for t in (e.tags or []):
        if t.startswith("origin:"):
            return t[len("origin:"):]
    return None


def _by_origins(events, origins):
    """origins(set) 주어지면 그 origin만(미태깅은 통과 — MOCK/무태그 안전). None/빈=전체."""
    if not origins:
        return list(events)
    return [e for e in events if (_origin_of(e) is None or _origin_of(e) in origins)]


def query_payload(engine, q, llm=_DEFAULT_LLM, answer_only_summary=False, origins=None):
    """자연어 질의 → op 판정(route_intent) → engine 실행 → dict.
    이 디스패치가 op→engine 매핑의 단일 진실원천(cli.cmd_query도 이걸 쓴다).
    llm 미지정=make_llm()(웹 copilot, 항상 LLM 답). llm=None=digest(테스트, ollama 비호출).
    answer_only_summary=True면 요약 intent에만 answer(CLI용 — 비요약은 LLM 비호출·summary None).
    origins(set) 주어지면 체크된 플랫폼(origin)만 답변 근거 — 파싱은 전량, 답변 범위만 좁힘(무손실)."""
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
        if not res:
            # 긴 문장 kw는 substring 통검색 0건 → 의미 토큰을 '순서대로' 시도, 첫 유효 토큰 결과 사용.
            # 핵심: 토큰을 OR-합치지 않는다(조사/어미 토큰이 흔한 단어로 과매치→무관 이벤트 무더기 방지).
            # 질문 앞 토큰=주제어(예: "인물 …요약"→"인물")이므로 앞 토큰 우선. 과매치(불용어성) 토큰은 스킵.
            cap = max(50, int(len(engine.events) * 0.4))
            for t in search_terms(intent.get("kw", "")):
                hit = engine.search(t, actor=a)
                if hit and len(hit) <= cap:        # 과매치 토큰(전체의 40%+ 매칭)은 무의미 → 스킵
                    res = hit
                    break
            # 전부 0건이거나 과매치뿐 → res 빈 채 아래 overview 폴백(순수 개요질문 의도된 분기)
    res = _by_origins(res, origins)               # ← 체크된 플랫폼만(답변 범위)
    if answer_only_summary and not intent.get("summarize"):
        summary = None                            # CLI 비요약 → LLM/답 없음(make_llm 비호출)
    else:
        use_llm = make_llm() if llm is _DEFAULT_LLM else llm   # 웹=gemma4 / 테스트(llm=None)=digest
        if op == "timeline":
            # 타임라인 요약 → 시간 흐름(초기→최근) 대화 주제 변화 서술.
            summary = answer_timeline(q, res, llm=use_llm)
        elif op == "search" and not res:
            # 막연한 대화형 질문(특정 키워드 매칭 0건) → 전체 행위 개요로 답(소스 필터된 집계 근거).
            summary = answer_overview(q, _by_origins(engine.events, origins), llm=use_llm)
        else:
            summary = answer(q, res, llm=use_llm) # 검색된 res만 근거. ollama 없으면 digest.
    return {"op": op, "intent": intent, "actor": a,
            "events": [e.to_dict() for e in res], "count": len(res),
            "summary": summary}


def stats_payload(engine):
    """요약 타일용 경량 집계(총건수·A/B·bypass). 엔진 메모이즈 — 초기 즉시 표시용
    (전체 이벤트 직렬화 없이 빠르게 반환 → 대시보드 타일이 events 로드 전 바로 채워짐)."""
    def _build():
        total = len(engine.events)
        user = sum(1 for e in engine.events if e.actor == "user")
        agent = sum(1 for e in engine.events if e.actor == "agent")
        bypass = sum(1 for e in engine.events if "bypass-mode" in (e.tags or []))
        return {"total": total, "user": user, "agent": agent, "bypass": bypass}
    return engine._memo("stats", _build)


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


def scan_to_engine(roots, on_progress=None, collect_artifacts=False):
    """파일단위 병렬 parse(UNC 지연 중첩) + 단일 읽기서 bypass sessionId 수집(enrich 2차 재읽기 제거).
    무손실·결정적: root 입력순 → 파일순(jsonl_files: history먼저→sorted transcripts) → 파일내 line순 조립(I2).
    기존 순차(parse_source_tagged+enrich)와 이벤트 전량·순서·태그 동일 — 속도만 개선.
    on_progress(files_done, files_total, events, current_root): 진행=파일 단위(단일패스 → 중복카운트 없음).
    collect_artifacts=False(기본): QueryEngine만 반환(기존 100% 동일 — 회귀 불변).
    True: (QueryEngine, ev_root) 반환. ev_root=[(Event, root_str)...] 입력순 누적(enrich 끝난 최종 태그 포함, 같은 객체)."""
    from clfx.cli import _origin_label          # 지역 import — cli↔web.api 순환 회피
    from clfx.parser import parse_file

    roots = list(roots)
    if not roots:
        if on_progress:
            on_progress(0, 0, 0, None)
        return (QueryEngine([]), []) if collect_artifacts else QueryEngine([])
    srcs = [ClaudeSource(r) for r in roots]
    file_lists = [s.jsonl_files() for s in srcs]            # [history(존재시), *sorted transcripts]
    hists = [s.root / "history.jsonl" for s in srcs]
    total_files = sum(len(fl) for fl in file_lists)         # 단일패스 → 정확(기존 중복카운트보다 작음)
    if on_progress:
        on_progress(0, total_files, 0, None)
    tasks = [(ri, fi, p, (p == hists[ri]))
             for ri, fl in enumerate(file_lists) for fi, p in enumerate(fl)]
    lock = threading.Lock()
    prog = {"files": 0}
    results = {}                                            # (ri,fi) -> events
    bypass_by_root = [set() for _ in roots]

    def _work(task):
        ri, fi, p, is_hist = task
        evs, byp = parse_file(srcs[ri], p, is_hist)         # 단일 읽기 → events + bypass(레코드 무상태·병렬안전)
        with lock:
            prog["files"] += 1
            f = prog["files"]
        if on_progress:
            on_progress(f, total_files, 0, roots[ri])
        return ri, fi, evs, byp

    with ThreadPoolExecutor(max_workers=min(16, max(1, len(tasks)))) as ex:
        for ri, fi, evs, byp in ex.map(_work, tasks):       # 결과는 메인스레드서 수집(results/bypass 경합 없음)
            results[(ri, fi)] = evs
            bypass_by_root[ri] |= byp                       # set union — 순서무관 결정적
    events = []
    ev_root = []                                            # collect_artifacts=True일 때만 채워 반환
    for ri, root in enumerate(roots):                       # 입력 루트 순서(I2)
        tag = f"origin:{_origin_label(root)}"
        root_evs = []
        for fi in range(len(file_lists[ri])):               # 파일 순서(history먼저→sorted transcripts)
            for e in results[(ri, fi)]:                     # 파일내 line 순서
                if tag not in e.tags:
                    e.tags.append(tag)                      # origin 태그 먼저(parse_source_tagged와 동일 순서)
                root_evs.append(e)
        enrich(root_evs, srcs[ri], bypass=bypass_by_root[ri])   # 수집된 bypass로 태깅(재읽기 X)
        events.extend(root_evs)
        if collect_artifacts:
            ev_root.extend((e, str(root)) for e in root_evs)    # enrich 끝난 최종 상태 객체 + root 문자열
    if on_progress:
        on_progress(total_files, total_files, len(events), None)
    engine = QueryEngine(events)
    return (engine, ev_root) if collect_artifacts else engine


def forensic_scan(events_with_root, roots=None, tmp_dirs=None):
    """아티팩트 포렌식 단일 진입점 — hash_clusters(①복제/유출) + attribution_join(④주체왜곡)
    + tmp_retention(C: 보존기간) 합본. events_with_root=[(Event, root_str)].
    roots None이면 events_with_root서 distinct root를 sorted로 도출.
    tmp_dirs None이면 artifacts.tmp_roots(roots)로 도출. read-only FS만(artifacts 계층 위임).
    반환 키: scanned,missing,tmp_scanned,tmp_roots,errors,hashes,attribution,retention."""
    from clfx.analyze import artifacts
    if roots is None:
        roots = sorted({root for _e, root in (events_with_root or [])})
    if tmp_dirs is None:
        tmp_dirs = artifacts.tmp_roots(roots)
    out = artifacts.hash_clusters(events_with_root, roots=roots, tmp_dirs=tmp_dirs)
    out["attribution"] = artifacts.attribution_join(events_with_root)
    ret = artifacts.tmp_retention(tmp_dirs)
    out["retention"] = ret["retention"]
    out["errors"] = sorted(out["errors"] + ret["errors"], key=lambda e: e["path"])  # 보존 스캔 실패도 병합
    return out


def mcp_payload(engine, roots):
    """MCP 통합 페이로드 — 설정 스캔 + 엔진 이벤트 실사용 대조. /api/mcp 단일 진입점."""
    from clfx.analyze import mcp as mcpmod
    return mcpmod.mcp_summary(roots, engine.events)


def sources_payload():
    """자동탐지 소스 중 실재(exists)만 — 없는 후보는 화면에 안 보이게. discover_sources는 전체+exists 반환."""
    from clfx.discover import discover_sources   # 지역 import — discover→cli→web.api 순환 회피
    return {"sources": [s for s in discover_sources() if s["exists"]]}

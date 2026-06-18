"""웹 대시보드용 순수 API 로직. HTTP 무관 — dict만 반환해 테스트가 쉽다.
엔진(QueryEngine)이 단일 진실원천. 여기서 검색/탐지 로직을 재구현하지 않는다."""
import csv
import io
import json
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


def events_payload_bytes(engine):
    """OPT-8: events_payload를 1회 직렬화한 bytes를 엔진 메모이즈 — /api/events 재요청 시 재인코딩 회피.
    바이트는 _json(events_payload(engine))과 동일(ensure_ascii=False, utf-8). 서버가 그대로 전송."""
    def _build():
        return json.dumps(events_payload(engine), ensure_ascii=False).encode("utf-8")
    return engine._memo("events_payload_bytes", _build)


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


def _origins_key(origins):
    """메모이즈 키 접미사. origins 없음(None/빈) → "all", 아니면 정렬-조인(셋 순서 무관 결정적)."""
    return "all" if not origins else ",".join(sorted(origins))


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
    elif op == "bypass":
        res = engine.bypass(actor=a)
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


def _stats_build(events):
    """이벤트 리스트 위 경량 집계(총건수·A/B·bypass). 스코핑/전체 공용(DRY)."""
    total = len(events)
    user = sum(1 for e in events if e.actor == "user")
    agent = sum(1 for e in events if e.actor == "agent")
    bypass = sum(1 for e in events if "bypass-mode" in (e.tags or []))
    return {"total": total, "user": user, "agent": agent, "bypass": bypass}


def stats_payload(engine, origins=None):
    """요약 타일용 경량 집계(총건수·A/B·bypass). 엔진 메모이즈 — 초기 즉시 표시용.
    origins(set) 주어지면 체크된 플랫폼(origin)만 집계 — 파싱은 전량, 집계 범위만 좁힘(무손실).
    None/빈=전체(키 "stats" 불변 — 회귀 동일). 비None=키 "stats:<정렬조인>"(충돌 없음)."""
    if not origins:
        return engine._memo("stats", lambda: _stats_build(engine.events))
    return engine._memo("stats:" + _origins_key(origins),
                        lambda: _stats_build(_by_origins(engine.events, origins)))


def activity_payload(engine, by="day", origins=None):
    """활동량 집계 — UI 히트맵용. actor 분리(④).
    origins 주어지면 체크된 플랫폼만(스코핑 sub-QueryEngine이 SAME _activity 로직 재사용 — JS 재구현 아님).
    None/빈=전체(현행 불변). 결과는 메인 엔진에 origins별로 메모이즈."""
    by = by if by in ("day", "month") else "day"
    if not origins:
        return {"by": by, "rows": engine.activity(by=by)}
    return engine._memo(
        "activity_payload:" + by + ":" + _origins_key(origins),
        lambda: {"by": by, "rows": QueryEngine(_by_origins(engine.events, origins)).activity(by=by)})


def files_payload(engine, origins=None):
    """접근파일 목록 — UI 파일패널용. actor 분리(③④).
    origins 주어지면 체크된 플랫폼만(스코핑 sub-QueryEngine이 SAME files() 로직 재사용).
    None/빈=전체(현행 불변)."""
    if not origins:
        return {"files": engine.files()}
    return engine._memo(
        "files:" + _origins_key(origins),
        lambda: {"files": QueryEngine(_by_origins(engine.events, origins)).files()})


def keywords_payload(engine, origins=None):
    """키워드 빈도 집계 — UI 도넛용(⑥). 결정적, 수사사전·패턴 포함. 엔진 메모이즈(재요청 풀스캔 회피).
    origins 주어지면 체크된 플랫폼만 집계. None/빈=전체(키 "keywords" 불변 — 회귀 동일)."""
    if not origins:
        return engine._memo("keywords", lambda: keyword_stats(engine.events))
    return engine._memo("keywords:" + _origins_key(origins),
                        lambda: keyword_stats(_by_origins(engine.events, origins)))


def scan_to_engine(roots, on_progress=None, collect_artifacts=False):
    """파일단위 병렬 parse(UNC 지연 중첩) + 단일 읽기서 bypass sessionId 수집(enrich 2차 재읽기 제거).
    무손실·결정적: root 입력순 → 파일순(jsonl_files: history먼저→sorted transcripts) → 파일내 line순 조립(I2).
    기존 순차(parse_source_tagged+enrich)와 이벤트 전량·순서·태그 동일 — 속도만 개선.
    on_progress(files_done, files_total, events, current_root): 진행=파일 단위(단일패스 → 중복카운트 없음).
    collect_artifacts=False(기본): QueryEngine만 반환(기존 100% 동일 — 회귀 불변).
    True: (QueryEngine, ev_root, by_origin, acquired_manifest) 반환. ev_root=[(Event, root_str)...] 입력순 누적
    (enrich 끝난 최종 태그 포함, 같은 객체). by_origin={origin: count}(OPT-8: 조립 루프서 동시 누적 —
    server 측 post-scan 재순회 제거. 옛 'for e in evs: for t in e.tags' 결과와 동일).
    B-1 acquired_manifest={str(path): sha256} — jsonl 증거파일(콘텐츠 판독) 매니페스트(parse 단계 누적,
    재해시 X; sha=None인 미판독 파일 제외). engine.evidence_manifest와 동일 객체(단일 진실원천)."""
    from clfx.cli import _origin_label          # 지역 import — cli↔web.api 순환 회피
    from clfx.parser import parse_file
    from clfx import roio

    roio.reset_audit()                          # B-2: 스캔 시작마다 in-memory audit 초기화(결정성·재실행 동일)
    roots = list(roots)
    if not roots:
        if on_progress:
            on_progress(0, 0, 0, None)
        return (QueryEngine([]), [], {}, {}) if collect_artifacts else QueryEngine([])
    srcs = [ClaudeSource(r) for r in roots]
    file_lists = [s.jsonl_files() for s in srcs]            # [history(존재시), *sorted transcripts]
    hists = [s.root / "history.jsonl" for s in srcs]
    total_files = sum(len(fl) for fl in file_lists)         # 단일패스 → 정확(기존 중복카운트보다 작음)
    if on_progress:
        on_progress(0, total_files, 0, None)
    tasks = [(ri, fi, p, (p == hists[ri]))
             for ri, fl in enumerate(file_lists) for fi, p in enumerate(fl)]
    tasks_path = {(ri, fi): p for ri, fi, p, _ in tasks}    # B-1: (ri,fi) → 읽은 파일 경로(매니페스트 키)
    lock = threading.Lock()
    prog = {"files": 0}
    results = {}                                            # (ri,fi) -> events
    bypass_by_root = [set() for _ in roots]

    def _work(task):
        ri, fi, p, is_hist = task
        evs, byp, sha = parse_file(srcs[ri], p, is_hist)    # 단일 읽기 → events + bypass + raw-바이트 sha(병렬안전)
        with lock:
            prog["files"] += 1
            f = prog["files"]
        if on_progress:
            on_progress(f, total_files, 0, roots[ri])
        return ri, fi, evs, byp, sha

    evidence_manifest = {}                                  # B-1: str(path) → sha256(읽은 jsonl 증거파일 전수)
    with ThreadPoolExecutor(max_workers=min(32, max(1, len(tasks)))) as ex:  # OPT-8: 32 동시 파싱
        for ri, fi, evs, byp, sha in ex.map(_work, tasks):  # 결과는 메인스레드서 수집(results/bypass 경합 없음)
            results[(ri, fi)] = evs
            bypass_by_root[ri] |= byp                       # set union — 순서무관 결정적
            if sha is not None:                             # 못 연 파일(sha None)은 매니페스트 제외(콘텐츠 미판독)
                evidence_manifest[str(tasks_path[(ri, fi)])] = sha
    events = []
    ev_root = []                                            # collect_artifacts=True일 때만 채워 반환
    by_origin = {}                                          # OPT-8: origin별 카운트(조립 루프서 동시 누적)
    for ri, root in enumerate(roots):                       # 입력 루트 순서(I2)
        label = _origin_label(root)
        tag = f"origin:{label}"
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
            # OPT-8: 이벤트별 origin: 태그 카운트. enrich 후 최종 태그 기준(옛 post-scan 루프와 동일).
            for e in root_evs:
                for t in e.tags:
                    if t.startswith("origin:"):
                        k = t[len("origin:"):]
                        by_origin[k] = by_origin.get(k, 0) + 1
    if on_progress:
        on_progress(total_files, total_files, len(events), None)
    engine = QueryEngine(events)
    # B-1 acquisition manifest(증거 jsonl 파일 전수): str(path)→sha256(정렬). 추가 읽기 없이
    #   parse 단계서 누적한 raw-바이트 해시. 튜플 arity는 불변 — 엔진 속성으로 부착(회귀 안전).
    engine.evidence_manifest = {p: evidence_manifest[p] for p in sorted(evidence_manifest)}
    # B-1: collect_artifacts=True면 4번째로 jsonl 증거 매니페스트(엔진 부착본과 동일 dict) 반환.
    return (engine, ev_root, by_origin, engine.evidence_manifest) if collect_artifacts else engine


def forensic_scan(events_with_root, roots=None, tmp_dirs=None, on_progress=None):
    """아티팩트 포렌식 단일 진입점 — hash_clusters(①복제/유출) + attribution_join(④주체왜곡)
    + tmp_retention(C: 보존기간) 합본. events_with_root=[(Event, root_str)].
    roots None이면 events_with_root서 distinct root를 sorted로 도출.
    tmp_dirs None이면 artifacts.tmp_roots(roots)로 도출. read-only FS만(artifacts 계층 위임).

    OPT-1: tmp 인벤토리(build_tmp_inventory)와 참조 해석(build_reference_resolution)을 1회만 만들어
      hash_clusters/tmp_retention(inventory=)·hash_clusters/attribution_join(resolved=)에 주입 —
      2차 walk·중복 resolve 제거. 결과(hashes/attribution/retention/...)는 옛 개별 호출과 byte-identical.
    OPT-7: on_progress(stage, done, total) 단계 진행 보고 — walk-tmp→resolve→hash(N/M)→attribution→retention.
    반환 키: scanned,missing,tmp_scanned,tmp_roots,errors,hashes,attribution,retention,tmp_hash_index,
      hashed,stat_verified,content_unread, tmp_inventory(서버 lazy 전수 reverse-index 빌드용 파일 리스트).
    (tmp_hash_index/tmp_inventory는 server가 pop — /api/artifacts엔 안 실림.)"""
    from clfx.analyze import artifacts
    if roots is None:
        roots = sorted({root for _e, root in (events_with_root or [])})
    if tmp_dirs is None:
        tmp_dirs = artifacts.tmp_roots(roots)

    def _emit(stage, done, total):
        if on_progress is not None:
            on_progress(stage, done, total)

    # 1) walk-tmp: 단일 인벤토리(재-walk 금지 — 이후 전 단계 공유).
    _emit("walk-tmp", 0, 1)
    inventory = artifacts.build_tmp_inventory(tmp_dirs)
    _emit("walk-tmp", 1, 1)

    # 2) resolve: (root,target) 해석 캐시 1회(hash_clusters·attribution_join 공유 — 중복 resolve 제거).
    _emit("resolve", 0, 1)
    resolved = artifacts.build_reference_resolution(events_with_root)
    _emit("resolve", 1, 1)

    # 3) hash: size-prefilter 해싱(N/M 진행은 hash_clusters의 on_hash_progress가 forward).
    _emit("hash", 0, 0)
    out = artifacts.hash_clusters(events_with_root, roots=roots, tmp_dirs=tmp_dirs,
                                  inventory=inventory, resolved=resolved,
                                  on_hash_progress=lambda d, t: _emit("hash", d, t))

    # 4) attribution(공유 resolved).
    _emit("attribution", 0, 1)
    out["attribution"] = artifacts.attribution_join(events_with_root, resolved=resolved)
    _emit("attribution", 1, 1)

    # 5) retention(공유 inventory — 재-stat 금지; referenced map으로 transcript 귀속 JOIN).
    #    referenced는 hash_clusters가 이미 만든 rec — 재집계/재해시 없이 재사용.
    _emit("retention", 0, 1)
    ret = artifacts.tmp_retention(tmp_dirs, inventory=inventory,
                                  referenced=out.get("referenced"))
    out["retention"] = ret["retention"]
    out["errors"] = sorted(out["errors"] + ret["errors"], key=lambda e: e["path"])  # 보존 스캔 실패도 병합
    _emit("retention", 1, 1)

    # referenced는 JOIN에만 쓰고 반환 KEY SET서 제거(/api/artifacts 비대화 방지·contract 불변).
    out.pop("referenced", None)

    # server lazy 전수 reverse-index 빌드용(unique-size 포함). /api/artifacts엔 server가 pop해 비노출.
    out["tmp_inventory"] = inventory["files"]
    return out


ATTEST_NOTE = ("라이브 제자리 분석(Claude OFF·증거 정적). 취득 시 SHA-256 매니페스트 기록. "
               "비변경은 도구가 쓰기 syscall 0·전 open 읽기전용임으로 보장"
               "(전후 재해싱은 round5 성능 위해 미수행, 필요 시 재검증 옵션).")


def attestation_payload(parse_manifest, forensic_out):
    """B-1/B-2: chain-of-custody attestation 계약 dict 조립(HTTP 무관, 순수).

    acquired = 콘텐츠를 실제로 읽은 파일의 {path, sha256} 정렬 목록 —
      parse_manifest(jsonl 증거) ∪ forensic_out["acquired_hashes"](참조+tmp 콘텐츠 판독),
      path별 dedupe(같은 path는 1행), path 정렬(결정적). 재해시 없음(이미 계산된 해시만 표면화).
    stat_only_count = 콘텐츠 미판독(size-prefilter unique-size) 파일 수 — 가짜 해시 없이 투명 보고.
    all_read_only / modes_seen / write_delete_rename_ops = roio 감사(B-2 read-only 강제 표면화).
    note = 고정 한국어 attestation 문구(ATTEST_NOTE). 모든 출력 정렬·결정적(재실행 동일)."""
    from clfx import roio
    merged = {}                                  # path → sha256 (dedupe by path)
    for p, sha in (parse_manifest or {}).items():
        merged[str(p)] = sha
    for p, sha in (forensic_out.get("acquired_hashes") or {}).items():
        merged[str(p)] = sha
    acquired = [{"path": p, "sha256": merged[p]} for p in sorted(merged)]
    modes = roio.modes_seen()                    # 정렬 distinct mode(부분집합 {r,rb})
    return {
        "acquired": acquired,
        "acquired_count": len(acquired),
        "stat_only_count": len(forensic_out.get("stat_only") or []),
        "all_read_only": all(m in ("r", "rb") for m in modes),
        "modes_seen": modes,
        "write_delete_rename_ops": roio.write_delete_rename_ops(),
        "note": ATTEST_NOTE,
    }


CSV_COLUMNS = ("path", "algorithm", "sha256")


def attestation_csv(attestation):
    """B-1 취득 해시 매니페스트를 CSV 텍스트로 직렬화 — 실무 chain-of-custody 표준 산출물.
    attestation_payload가 이미 표면화한 acquired({path,sha256})만 그대로 행으로 — 재해시·재집계 없음.
    열: path, algorithm(=SHA-256 상수, 자기설명적), sha256. 행 순서 = acquired 순서(payload가 path 정렬 → 결정적).
    csv 모듈로 RFC-4180 인용(콤마·따옴표·개행 안전), 선두에 UTF-8 BOM(Excel에서 한글 경로 자동 인식).
    read-only(메모리만, FS 미접근)·무손실(해시 보유 전 파일 1행). stat_only(내용 미판독)는 해시가 없어 제외."""
    acquired = (attestation or {}).get("acquired") or []
    buf = io.StringIO()
    w = csv.writer(buf)                          # 기본 lineterminator="\r\n" (RFC-4180)
    w.writerow(CSV_COLUMNS)
    for a in acquired:
        w.writerow([a.get("path", ""), "SHA-256", a.get("sha256", "")])
    return "﻿" + buf.getvalue()             # UTF-8 BOM 선두


def mcp_payload(engine, roots, on_progress=None):
    """MCP 통합 페이로드 — 설정 스캔 + 엔진 이벤트 실사용 대조. /api/mcp 단일 진입점.
    OPT-7: on_progress(stage, done, total)로 mcp 단계 보고(None이면 no-op)."""
    from clfx.analyze import mcp as mcpmod
    if on_progress is not None:
        on_progress("mcp", 0, 1)
    out = mcpmod.mcp_summary(roots, engine.events)
    if on_progress is not None:
        on_progress("mcp", 1, 1)
    return out


def sources_payload():
    """자동탐지 소스 중 실재(exists)만 — 없는 후보는 화면에 안 보이게. discover_sources는 전체+exists 반환."""
    from clfx.discover import discover_sources   # 지역 import — discover→cli→web.api 순환 회피
    return {"sources": [s for s in discover_sources() if s["exists"]]}

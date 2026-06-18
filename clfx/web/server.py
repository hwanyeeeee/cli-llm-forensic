"""stdlib http.server 기반 로컬 대시보드 서버. api.py를 호출+직렬화만 한다.
GET 전용(read-only). 127.0.0.1 바인드, 정적 파일 화이트리스트."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from clfx.event import Event
from clfx.query.engine import QueryEngine
from clfx import roio
from clfx.web.api import (events_payload, events_payload_bytes, query_payload, stats_payload,
                          activity_payload, files_payload, keywords_payload,
                          sources_payload, scan_to_engine, forensic_scan,
                          mcp_payload, attestation_payload)

# B-1/B-2: ServerState 초기 attestation — empty-but-valid 계약(스캔 전 GET /api/attestation 안전).
_ATTEST_EMPTY = {"acquired": [], "acquired_count": 0, "stat_only_count": 0,
                 "all_read_only": True, "modes_seen": [], "write_delete_rename_ops": 0,
                 "note": "(스캔 전)"}

def _static_dir():
    """정적 파일 디렉터리. PyInstaller onefile은 sys._MEIPASS에 추출되므로 그 경로 우선."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "clfx", "web", "static")
    return os.path.join(os.path.dirname(__file__), "static")


_STATIC = _static_dir()
_ROUTES = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css", "/logo.png": "logo.png",
           "/view.html": "view.html", "/view.js": "view.js", "/forensic-views.js": "forensic-views.js"}
_CT = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png"}


class ServerState:
    """교체가능 엔진 보유(스캔 시 state.engine 교체). 전역 상태 회피용 가변 컨테이너.
    scan = 진행상황(POST /api/scan 처리 스레드가 갱신, GET /api/scan/progress 폴링이 읽음)."""
    def __init__(self, engine):
        self.engine = engine
        # OPT-7: 단계 진행 필드 추가(기존 키 유지 — 폴링·테스트 불변).
        self.scan = {"total": 0, "done": 0, "events": 0, "current": None, "finished": True, "error": None,
                     "stage": None, "stage_done": 0, "stage_total": 0, "overall_percent": 100}
        # 아티팩트 포렌식 결과(POST /api/scan서 forensic_scan으로 갱신, GET /api/artifacts가 읽음).
        # FS 분석 실패해도 빈 계약 유지(스캔 응답은 성공).
        self.artifacts = {"scanned": 0, "missing": 0, "tmp_scanned": 0, "tmp_roots": [],
                          "errors": [], "hashes": [], "attribution": []}
        # OPT-3: 원본→동일해시 tmp 검색 인덱스 — lazy 캐시. 스캔 직후엔 비어있고(첫 /api/hash-search서 전수 빌드),
        # 빌드 후 재사용. tmp_inventory(전수 파일 리스트)에서 build_tmp_hash_index로 unique-size까지 인덱싱.
        # /api/artifacts엔 싣지 않음(대용량/read-only 조회 분리).
        self.tmp_hash_index = {}
        self.tmp_inventory = []          # forensic_scan에서 pop한 전수 인벤토리(lazy 빌드 소스)
        self._hash_index_ready = False   # lazy 캐시 빌드 완료 플래그
        self._hash_index_lock = threading.Lock()   # 동시 첫 요청이 1회만 빌드하도록
        # MCP 통합 결과(POST /api/scan서 mcp_payload로 갱신, GET /api/mcp가 읽음).
        # MCP 분석 실패해도 빈 계약 유지(스캔 응답은 성공).
        self.mcp = {"configs": [], "usage": [], "configured_unused": [],
                    "used_unconfigured": [], "errors": []}
        # B-1/B-2: chain-of-custody attestation(POST /api/scan서 attestation_payload로 갱신,
        # GET /api/attestation가 읽음). 스캔 전엔 empty-but-valid 계약(실패해도 이 빈 계약 유지).
        self.attestation = dict(_ATTEST_EMPTY)


def _ensure_hash_index(state):
    """OPT-3 lazy: 첫 /api/hash-search서 tmp_inventory 전수(unique-size 포함)를 SHA-256 인덱싱.
    lock으로 동시 첫 요청이 1회만 빌드, 이후 캐시 재사용. scan-time 인덱스는 dup-size만 덮으므로
    이 전수 인덱스가 없으면 unique-size tmp 파일이 검색 불가(완전성 회귀). 결과는 결정적(정렬)."""
    if state._hash_index_ready:
        return state.tmp_hash_index
    with state._hash_index_lock:
        if not state._hash_index_ready:          # double-checked: lock 안에서 재확인
            from clfx.analyze import artifacts
            state.tmp_hash_index = artifacts.build_tmp_hash_index({"files": state.tmp_inventory})
            state._hash_index_ready = True
    return state.tmp_hash_index


def make_handler(state):
    """ServerState(가변 엔진) 주입 핸들러 팩토리. 스캔으로 state.engine 교체 가능(요청 시점 읽기)."""

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body_bytes, code, content_type):
            self.send_response(code)
            ct = content_type + ("; charset=utf-8" if (content_type.startswith("text/") or content_type == "application/json") else "")
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)

        def _json(self, obj, code=200):
            self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       code, "application/json")

        def _static(self, fname):
            path = os.path.join(_STATIC, fname)
            try:
                with open(path, "rb") as f:
                    body = f.read()
            except OSError:
                self._json({"error": "not found"}, 404)
                return
            ext = os.path.splitext(fname)[1]
            self._send(body, 200, _CT.get(ext, "application/octet-stream"))

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in _ROUTES:
                self._static(_ROUTES[u.path])
                return
            if u.path == "/api/sources":
                try:
                    self._json(sources_payload())
                except Exception as e:               # 서버는 안 죽는다
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/scan/progress":
                self._json(state.scan); return
            if u.path == "/api/stats":               # 경량 타일 집계(events 직렬화 전 즉시 표시)
                src = (parse_qs(u.query).get("sources") or [""])[0]
                origins = set(s for s in src.split(",") if s) or None   # 체크된 플랫폼만(없으면 전체)
                try:
                    self._json(stats_payload(state.engine, origins=origins))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/events":
                try:
                    # OPT-8: 캐시된 bytes를 그대로 전송(재요청마다 재인코딩 회피). 바이트는 events_payload 동일.
                    self._send(events_payload_bytes(state.engine), 200, "application/json")
                except Exception as e:               # 서버는 안 죽는다
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/query":
                qs = parse_qs(u.query)
                q = (qs.get("q") or [""])[0]
                if not q:
                    self._json({"error": "q required"}, 400)
                    return
                src = (qs.get("sources") or [""])[0]
                origins = set(s for s in src.split(",") if s) or None   # 체크된 플랫폼만(없으면 전체)
                try:
                    self._json(query_payload(state.engine, q, origins=origins))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/activity":
                qs = parse_qs(u.query)
                by = (qs.get("by") or ["day"])[0]
                src = (qs.get("sources") or [""])[0]
                origins = set(s for s in src.split(",") if s) or None   # 체크된 플랫폼만(없으면 전체)
                try:
                    self._json(activity_payload(state.engine, by=by, origins=origins))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/files":
                src = (parse_qs(u.query).get("sources") or [""])[0]
                origins = set(s for s in src.split(",") if s) or None   # 체크된 플랫폼만(없으면 전체)
                try:
                    self._json(files_payload(state.engine, origins=origins))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/keywords":
                src = (parse_qs(u.query).get("sources") or [""])[0]
                origins = set(s for s in src.split(",") if s) or None   # 체크된 플랫폼만(없으면 전체)
                try:
                    self._json(keywords_payload(state.engine, origins=origins))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/artifacts":
                try:
                    self._json(state.artifacts)
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/mcp":
                try:
                    self._json(state.mcp)
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/attestation":     # B-1/B-2: chain-of-custody attestation(read-only)
                try:
                    self._json(state.attestation)
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/hash-search":         # 원본 sha → 동일해시 tmp 사본 조회(read-only, 해시 hex만)
                try:
                    sha = (parse_qs(u.query).get("sha") or [""])[0].strip().lower()
                    index = _ensure_hash_index(state)   # OPT-3: 첫 호출서 전수 인덱스 lazy 빌드(unique-size 포함)
                    self._json({"sha": sha, "matches": index.get(sha, [])})
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            if u.path == "/api/scan":
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(n) or b"{}")
                    roots = body.get("roots") or []
                    roio.reset_audit()           # B-2: 스캔 시작마다 in-memory audit 초기화(per-scan attestation)
                    # 진행상황 초기화 → on_progress가 단계마다 갱신 → 폴링 GET이 읽음(동기 POST 유지).
                    # OPT-7: 파이프라인 단계별 가중 overall_percent.
                    #   parse → resolve → walk-tmp → hash → attribution → retention → mcp → finalize.
                    state.scan = {"total": len(roots), "done": 0, "events": 0,
                                  "current": None, "finished": False, "error": None,
                                  "stage": "parse", "stage_done": 0, "stage_total": 0, "overall_percent": 0}
                    # 단계 누적 가중치(합=100). 단계 내부 진행은 그 가중치 비율로 환산.
                    _STAGE_BASE = {"parse": 0, "walk-tmp": 40, "resolve": 50, "hash": 55,
                                   "attribution": 85, "retention": 90, "mcp": 95, "finalize": 100}
                    _STAGE_SPAN = {"parse": 40, "walk-tmp": 10, "resolve": 5, "hash": 30,
                                   "attribution": 5, "retention": 5, "mcp": 5}

                    def _overall(stage, done, total):
                        base = _STAGE_BASE.get(stage, 0)
                        span = _STAGE_SPAN.get(stage, 0)
                        frac = (done / total) if total else 1.0
                        return int(min(100, base + span * frac))

                    def _prog(d, t, ev, cur):                # parse 단계(scan_to_engine — 시그니처 불변)
                        state.scan.update(done=d, total=t, events=ev, current=cur,
                                          stage="parse", stage_done=d, stage_total=t,
                                          overall_percent=_overall("parse", d, t))

                    def _fprog(stage, done, total):          # forensic_scan 단계(OPT-7)
                        state.scan.update(stage=stage, stage_done=done, stage_total=total,
                                          overall_percent=_overall(stage, done, total))

                    eng, ev_root, by, acquired_manifest = scan_to_engine(
                        roots, on_progress=_prog, collect_artifacts=True)
                    state.engine = eng                       # 엔진 교체
                    acquired_hashes = {}
                    stat_only = []
                    try:                                     # FS 실패해도 스캔 응답은 성공(빈 계약 유지)
                        full = forensic_scan(ev_root, roots=roots, on_progress=_fprog)
                        # tmp_hash_index/tmp_inventory 둘 다 pop — /api/artifacts엔 안 실림(분리).
                        full.pop("tmp_hash_index", None)
                        state.tmp_inventory = full.pop("tmp_inventory", [])
                        # B-1: acquired_hashes/stat_only도 pop — /api/artifacts 비대화 차단(Issue-1).
                        #   attestation 빌드에만 쓰고 artifacts payload엔 안 싣는다.
                        acquired_hashes = full.pop("acquired_hashes", {})
                        stat_only = full.pop("stat_only", [])
                        state.tmp_hash_index = {}            # lazy 캐시 리셋(첫 /api/hash-search서 전수 빌드)
                        state._hash_index_ready = False
                        state.artifacts = full
                    except Exception:
                        state.tmp_inventory = []
                        state.tmp_hash_index = {}
                        state._hash_index_ready = False
                        state.artifacts = {"scanned": 0, "missing": 0, "tmp_scanned": 0,
                                           "tmp_roots": [], "errors": [], "hashes": [], "attribution": []}
                    try:                                     # B-1/B-2: attestation 실패해도 스캔은 성공(빈 계약 유지)
                        state.attestation = attestation_payload(
                            acquired_manifest,
                            {"acquired_hashes": acquired_hashes, "stat_only": stat_only})
                    except Exception:
                        state.attestation = dict(_ATTEST_EMPTY)
                    try:                                     # MCP 실패해도 스캔 응답은 성공(빈 계약 유지)
                        state.mcp = mcp_payload(eng, roots, on_progress=_fprog)
                    except Exception:
                        state.mcp = {"configs": [], "usage": [], "configured_unused": [],
                                     "used_unconfigured": [], "errors": []}
                    from clfx.query.llm import prewarm
                    threading.Thread(target=prewarm, daemon=True).start()   # 모델 미리 로드(쿼리 전 워밍, fire-and-forget)
                    evs = eng.events
                    state.scan.update(done=state.scan["total"], events=len(evs),
                                      finished=True, current=None,
                                      stage="finalize", stage_done=1, stage_total=1, overall_percent=100)
                    self._json({"ok": True, "count": len(evs), "by_origin": by})
                except Exception as e:
                    state.scan.update(finished=True, error=str(e))
                    self._json({"ok": False, "error": str(e)}, 500)
                return
            self._json({"error": "not found"}, 404)

        def log_message(self, *a):
            pass  # 콘솔 조용히

    return Handler


def load_engine(analyzed_path):
    """analyzed.jsonl → QueryEngine. 깨진 줄/없는 파일은 예외를 그대로 올린다
    (포렌식: 부분 로드보다 명확한 실패). B-2: read-only 강제 + audit 경유(_ro_open)."""
    with roio._ro_open(analyzed_path, "r", encoding="utf-8") as f:
        events = [Event.from_dict(json.loads(l)) for l in f if l.strip()]
    return QueryEngine(events)


def build_state(analyzed_path):
    """analyzed_path 있으면 load, None이면 빈 엔진. serve/테스트 공용(블록 없이 단언 가능)."""
    engine = load_engine(analyzed_path) if analyzed_path else QueryEngine([])
    return ServerState(engine)


def serve(analyzed_path=None, host="127.0.0.1", port=8787):
    state = build_state(analyzed_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"clfx dashboard: http://{host}:{port}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()

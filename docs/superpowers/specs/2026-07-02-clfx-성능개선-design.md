# clfx 성능개선 설계 — 계측 우선 2-페이즈 + 케이스 파일

날짜: 2026-07-02 · 작성: panel0 (brainstorming 승인분)

## 목적

round5-7 무손실 최적화(3e5ad95) 이후에도 스캔·대시보드·LLM 질의 전반이 느리다(실데이터 exe 경로 42.8s, 119,520 events / FS ~44k 파일 / tmp 15,566). 추측 최적화를 배제하고 **계측 → 데이터 근거 표적 제거** 순서로 진행하며, 최대 레버로 **케이스 파일(영속 캐시)** 를 도입해 재실행/재오픈을 초 단위로 만든다.

## 사용자 결정 사항

- 접근 = **A안: 계측 우선 2-페이즈** (Phase 1 측정 → Phase 2 표적 최적화).
- 실행 환경 = Windows exe(\\wsl.localhost UNC) / WSL 네이티브 **둘 다 동등** — 양쪽 다 측정.
- 케이스 파일 **허용**, 포맷 = **sqlite3 단일 파일** (stdlib).
- LLM **스트리밍 포함** (토큰 점진 표시).
- 전체 구조 감사 결과 반영, 성능 작업이 건드리는 범위의 구조 개선 포함.

## §0 강제 불변식 (전 항목 공통 — 위반 시 해당 최적화 기각)

| # | 불변식 | 증명 방법 |
|---|---|---|
| I1 | **무손실**: 최적화 전/후 분석 출력 byte-동일 | 등가성 테스트 (round5 `test_scan_equivalent_to_sequential` 방식) |
| I2 | **완전성**: skip/sample/cap/drop 0. 전 파일 stat, 접근 실패는 `errors[]` 표면화 | 코드 리뷰 + 기존 완전성 테스트 유지 |
| I3 | **read-only**: 증거 파일시스템 쓰기 0 (`roio.py` 가드 유지). 케이스 DB는 증거 트리 **밖** 전용 디렉터리에만 쓰며, 케이스 경로가 증거 루트 내부면 저장 거부 | 쓰기 경로 가드 테스트 |
| I4 | **케이스 무결성**: 캐시 히트 조건 = 소스 지문(size+mtime_ns) 일치. 불일치·신규·삭제 → 무조건 재처리. 케이스 손상/버전 불일치 → 전량 콜드런 폴백 (stale 표시 경로 자체가 없음) | 케이스 3종 테스트 (§5) |
| I5 | **UI 무손실**: 페이지네이션/가상화는 표시 순서만, 전 데이터 도달 가능 (`/api/events` N개 캡 금지) | 기존 FORBIDDEN 규칙 유지 |
| I6 | **계측 분리**: 타이밍 값은 비결정적 → 증거 데이터와 분리된 `timings` 필드/로그에만. 등가성 비교 대상에서 제외 | 등가성 테스트가 `timings` 제외 후 비교 |

## §1 Phase 1 — 계측 하네스

측정 없이는 Phase 2 착수 순서를 정하지 않는다.

### 1.1 스캔 단계별 타이밍
`scan_to_engine`/`forensic_scan`에 `time.perf_counter()` 누적 → 반환값에 `timings` dict 추가:
`parse / enrich / inventory(walk-tmp) / resolve / hash / mcp / attribution / retention / serialize` (기존 진행률 `_emit` 지점 재활용 — 삽입 위치 확정됨: api.py 246-300 부근 + scan_to_engine 진입점 + attribution.enrich 진입점).

### 1.2 서버 요청 타이밍
`do_GET/do_POST` 공통 래퍼 — `endpoint · 소요 ms · 응답 bytes` stderr 로그.

### 1.3 LLM 질의 타이밍
`query_payload`(api.py:61-108)에 `timings = {intent_ms, search_ms, llm_ms, total_ms}`, `llm.complete()`(llm.py:407-434)에 `network_ms`(urlopen 전후) 분리.

### 1.4 프런트 타이밍
`performance.mark` boot-start/stage1/stage2(app.js:806/822/854) + 주요 fetch 소요 `console.table`.

### 1.5 벤치 스크립트 + 베이스라인 문서
`scripts/bench.py`: 실데이터 스캔 3회 반복 → 단계별 median 표 출력. Windows exe 경로 / WSL 네이티브 양쪽 실행 결과를 **`docs/perf-baseline.md`** 에 기록 (환경·데이터 규모·단계별 시간·병목 순위표).

### 1.6 Phase 게이트
`perf-baseline.md`의 병목 순위표를 보고한 뒤 Phase 2 백로그(§3) 착수 순서를 확정한다. 순위표 없이 §3 착수 금지 (단, §2 케이스 파일은 측정과 무관하게 확정 — 재실행 전량 콜드런이라는 구조적 사실이 근거).

## §2 Phase 2 — 케이스 파일 (sqlite3)

### 2.1 개념
첫 스캔 완료 → 케이스 저장. 재실행/재오픈 → 케이스 로드 → 소스 지문 검증 → **변경분만 재처리**. 엔진은 여전히 인메모리 — DB는 로드 가속용이지 질의 백엔드가 아니다 (엔진 리팩터 리스크 차단).

### 2.2 저장 위치
- WSL/POSIX: `~/.agentrace/cases/<케이스명>.db`
- Windows exe: `%LOCALAPPDATA%\AgenTrace\cases\<케이스명>.db`
- 저장 직전 가드: 케이스 경로가 스캔 대상 증거 루트 내부이면 거부 (I3).

### 2.3 스키마 개요 (플랜에서 DDL 확정)
- `case_meta(key, value)` — schema_version, 생성시각, 도구버전, 증거 루트 목록, 취득 해시 매니페스트 요약.
- `source_files(path PK, origin, size, mtime_ns, sha256, event_count)` — transcript jsonl 지문.
- `source_events(path PK → source_files, events_gz BLOB)` — 파싱된 Event 배열(JSON, gzip). **무효화 입자도 = 소스 파일 단위**이므로 파일당 1 blob.
- `fs_hashes(path PK, size, mtime_ns, sha256)` — 해시 원장 캐시.
- `tmp_inventory(path PK, origin, size, mtime_ns)` — tmp 전수 인벤토리.
- `aggregates(key PK, payload_gz BLOB)` — 스캔 집계 결과 (변경 0건일 때만 재사용).

### 2.4 검증·무효화 규칙 (I4의 구체화)
1. 로드 시 `schema_version` 불일치 또는 `PRAGMA quick_check` 실패 → 전량 콜드런.
2. 전 `source_files` + `fs_hashes` + `tmp_inventory` 경로 stat (stat 자체는 싸다 — 비싼 건 내용 읽기·해싱):
   - (size, mtime_ns) 일치 → 캐시 재사용 (재파싱/재해시 생략).
   - 불일치 → 해당 파일만 재파싱/재해시.
   - stat 실패 → `errors[]` 표면화 + 해당 항목 콜드 재처리 (I2).
   - 케이스에 없는 신규 파일(디렉터리 재열거로 탐지) → 콜드 처리. 케이스에 있는데 사라진 파일 → "케이스 저장 시점 존재 → 현재 소실"로 표면화 (증거 가치).
3. 변경이 1건이라도 있으면 `aggregates` 폐기, 이벤트/해시로부터 전면 재계산 (집계는 CPU-only라 싸다).
4. **등가성**: 케이스 로드 경로 결과 == 콜드런 결과, byte-동일 (`timings` 제외, I6).

### 2.5 mtime 신뢰 한계 명시 + verify 모드
(size+mtime) 지문은 timestomping(내용 변경 후 mtime 복원)을 놓칠 수 있다 — 문서에 한계로 명시. 완화책 = **"전체 재검증(verify)" 모드**: 전 파일 재해시 → 케이스 저장 당시 sha256과 대조 → 불일치 목록 표면화. 이는 곧 **증거 변경 탐지 기능**이며, 케이스 저장 시점의 취득 해시 매니페스트가 박제되므로 chain-of-custody가 오히려 강화된다.

### 2.6 표면 (UI/CLI)
- 스캔 화면: 스캔 완료 후 "케이스로 저장" / 시작 화면: "케이스 열기"(변경 감지 요약 — "N개 변경 재처리, M개 재사용") / 케이스 상세에 "전체 재검증" 버튼.
- CLI: `clfx case save|open|verify` (플랜에서 인자 확정).

## §3 Phase 2 — 표적 최적화 백로그 (착수 순서는 §1.6 순위표로 확정)

| # | 항목 | 근거 | 내용 | 불변식 증명 |
|---|---|---|---|---|
| O1 | HTTP gzip | server.py:83 `_send()` 비압축, 수십MB JSON | `Accept-Encoding: gzip` 시 압축 전송, 압축 결과 메모이즈 | 압축 해제 == 원본 bytes 테스트 |
| O2 | 엔진 인덱스 | engine.py:25-72 전 질의 O(N) 선형스캔 | `_memo` lazy 날짜별/actor별 인덱스, `on_date/who_did` 인덱스 경유 | 인덱스 경유 결과 == 선형스캔 결과 |
| O3 | 서브엔진 메모 | api.py:136-150 origin 필터마다 QueryEngine 신규 생성 | origin-key로 서브엔진 메모이즈 (엔진 교체 시 무효화) | 기존 origins 회귀 (byte-identical) 유지 |
| O4 | resolve 주입 강제 | artifacts.py:356,603 — resolved 미주입 경로에서 UNC stat 재호출 | `hash_clusters`/`attribution_join` 시그니처에서 `resolved` 필수화 | 기존 테스트 green + 주입/미주입 등가 |
| O5 | LLM 스트리밍 | llm.py:418 `stream:false` — 첫 토큰까지 전체 대기 | ollama `stream:true` → 서버 chunked 프록시 → UI 토큰 점진 렌더. 폴백: 스트림 실패 시 기존 일괄 응답 | 최종 조립 텍스트 == 일괄 응답 텍스트 |
| O6 | 주기 프리웜 | llm.py:437 1회성, keep_alive 30m 만료 후 콜드로드 1~3s | 20분 주기 재프리웜 (daemon, 실패 무시) | 부작용 없음 (증거 경로 무관) |
| O7 | 파싱 CPU 병렬 | sources/claude.py:47 json.loads GIL-bound (추정 35-40%) | **Phase 1에서 CPU-bound 실증된 경우에만** ProcessPoolExecutor 검토. PyInstaller exe는 `freeze_support` 함정 — exe 경로 검증 필수, 실증 전 착수 금지 | 병렬 결과 == 순차 결과 (기존 I2 등가성 테스트 확장) |
| O8 | 마이크로 | mcp.py:254 `_norm` 중복, secrets.py:64 8-regex 순차 | `_norm` 캐시 dict, secrets 조기탈출 | 측정에서 유의미할 때만, 각각 등가성 테스트 |
| O9 | 적응형 파싱 동시성 | Phase 1 실측(perf-baseline.md): 네이티브 FS서 32스레드가 순차 대비 +64% 손해(GIL — json.loads CPU-bound). 32워커는 UNC 지연 중첩용 | root 경로별 워커 수 분기: UNC/원격(\\wsl.localhost 등)=스레드 다수 유지, 네이티브=순차(1). 조립은 (ri,fi) 키라 워커 수 무관 | `test_scan_equivalent_to_sequential` 기존 등가성 테스트가 그대로 증명 |
| O10 | 소스탐지 UNC 견고화 | 2026-07-03 실사: 9P 고장 시 exe 소스탐지가 \\wsl.localhost 접근에서 무한 hang("소스 탐지 중…" 영구) — 조용한 멈춤은 완전성 위반 | discover의 원격 경로 존재확인에 타임아웃(워커 스레드+제한시간) → 실패 시 "WSL 소스 접근 불가(사유)"로 표면화하고 나머지 소스 계속 | 타임아웃 발생 시 errors/사유 표면화 테스트, 정상 경로 회귀 불변 |
| O11 | WSL-side 파싱 위임 | \\wsl.localhost(9P)는 느리고(UNC 페널티) 깨지기 쉬움(2026-07-03 wedge 실사 — p9rdr·plan9 살아있어도 세션 계층 고장). 반면 wsl.exe interop 채널은 별개라 9P 고장 중에도 동작 실증 | exe가 파싱 헬퍼를 Windows 임시경로에 기록 → `wsl.exe -d <distro> python3 /mnt/c/...` 로 WSL 내부 네이티브 파싱(실측 12s) → 결과 JSONL을 /mnt/c로 회수(WSL→Win 방향은 9P 고장과 무관). wsl.exe/python3 부재·실패 시 기존 UNC 경로 폴백 + errors 표면화 | 위임 결과 == UNC 직접 파싱 결과 등가성 테스트(동일 픽스처), 폴백 경로 테스트 |

## §4 구조 개선 (성능 작업이 건드리는 범위만)

- `artifacts.py`(667줄, 책임 혼합): 케이스 파일이 해시/인벤토리 로직을 직접 건드리므로 그 참에 `경로변환 / 인벤토리 / 해싱 / 클러스터링` 경계로 분리. 공개 함수 시그니처·출력 불변(등가성 테스트로 보증). 무관 리팩터링 금지.
- 죽은 코드 의심 2건 — `_walk_tmp` 래퍼(artifacts.py:217), `build_tmp_hash_index` 호출 경로(artifacts.py:565): **삭제 전 grep으로 사용처 검증 필수** (감사에서 "추정" 판정 — build_tmp_hash_index는 서버 lazy 해시검색용일 가능성).

## §5 테스트 전략

- 최적화 항목마다: 기존 전체 테스트 green 유지 + 신규 등가성 테스트 (§3 표의 증명 열).
- 케이스 파일 3종 (I4):
  1. 저장→로드 결과 == 콜드런 결과 (byte-동일, timings 제외).
  2. 소스 1개 변조(내용+mtime) → 해당 파일만 재처리 + 변경 감지 표면화, 최종 결과 == 변조 후 콜드런.
  3. 케이스 파일 손상(트렁케이트) → 콜드런 폴백, 에러 아님.
- verify 모드: 파일 1개 내용 변경 + mtime 복원(timestomp 시뮬) → verify가 sha256 불일치 검출.
- 벤치는 테스트 아님 — CI 밖 수동 실행 (환경 의존 시간값이라 flaky).

## §6 범위 밖 / FORBIDDEN

- 이벤트를 DB 질의 백엔드로 전환하는 엔진 전면 리팩터 (C안 — 기각됨).
- `/api/events` 서버측 캡·필터 축소 (I5).
- 서드파티 패키지 (orjson 등) — stdlib-only 유지.
- LLM 모델/파라미터 변경 (qwen2.5:7b 유지 — 생성 속도는 ollama 한계).

## §7 진행 방식

1. Phase 1 플랜 작성 → panel1 위임 → `perf-baseline.md` 산출 → 병목 순위표 보고.
2. 순위표 승인 후 Phase 2 플랜(케이스 파일 + 백로그 상위) 작성 → panel1 위임.
3. 각 완료 시 검증·커밋 = panel0 (기존 하네스 규칙).

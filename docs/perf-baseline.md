# clfx 성능 베이스라인 (Phase 1 측정 결과)

측정 방법: `python3 scripts/bench.py <root>... --repeat 3` (단계별 median).
브라우저 측: 대시보드 열고 DevTools 콘솔의 `clfx-boot-stage1/2` measure + FETCH_TIMINGS 표.
LLM 측: 질의 후 `/api/query` 응답의 `timings`(intent/search/llm/total, llm_network_ms).
서버 측: 콘솔 stderr `[clfx.timing]` 라인.

주의(I6): 여기 기록되는 시간값은 비결정적 측정치 — 증거 데이터 아님.

측정일: 2026-07-02~03 · 기기: Hwansktop (Windows + WSL Ubuntu)

## 환경 B — WSL 네이티브 (WSL .claude + Windows .claude 둘 다)

- 실행: `python3 scripts/bench.py /home/best1pjh/.claude /mnt/c/Users/best1/.claude --repeat 3`
- 데이터 규모: events=114,079 · missing=5,472 · scanned=11,246 · tmp_scanned=9,771
- run별 total: 39.4 / 28.5 / 25.4s (1회차 콜드가 +11s — OS 페이지캐시 효과)

| 단계 | median(s) | 전체 대비 |
|---|---|---|
| parse_wall_s | 22.274 | **78%** |
| enrich_s | 1.828 | 6.4% |
| walk_tmp_s | 0.301 | 1.1% |
| resolve_s | 2.859 | 10.0% |
| hash_s | 0.905 | 3.2% |
| attribution_s | 0.032 | — |
| retention_s | 0.037 | — |
| mcp_s | 0.063 | — |
| total_s | 28.533 | 100% |

## 환경 A-1 — Windows 네이티브 (Windows .claude만, UNC 제외)

- 실행: `python scripts\bench.py C:\Users\best1\.claude --repeat 3`
- 데이터 규모: events=1,006 · missing=23 · scanned=7,036 · tmp_scanned=7,034
- run별 total: 2.4 / 1.2 / 1.1s

| 단계 | median(s) | 전체 대비 |
|---|---|---|
| parse_wall_s | 0.114 | 9.6% |
| enrich_s | 0.009 | — |
| walk_tmp_s | 0.207 | 17.5% |
| resolve_s | 0.001 | — |
| hash_s | 0.801 | **67.7%** |
| attribution_s | 0.000 | — |
| retention_s | 0.026 | — |
| mcp_s | 0.003 | — |
| total_s | 1.183 | 100% |

## 환경 A-2 — Windows→WSL UNC (\\wsl.localhost, exe 최악 경로) — 측정 대기

- 실행: `python scripts\bench.py \\wsl.localhost\Ubuntu\home\best1pjh\.claude --repeat 1` (**WSL 기동 상태에서**)
- 주의: WSL 꺼진 상태로 UNC 접근 시 무한 대기처럼 보임(1차 시도가 밤새 무출력 — WSL 다운 추정). bench 첫 출력은 run 1 완료 후에 나옴.

(표 대기)

## 대시보드 / LLM 체감 (수동 기록 — 대기)

| 항목 | 측정값 | 비고 |
|---|---|---|
| boot-stage1 (타일+집계) | | DevTools measure |
| boot-stage2 (전체 이벤트) | | |
| /api/events 응답 크기 | | [clfx.timing] bytes |
| 질의 total_ms / llm_ms | | /api/query timings |

## 병목 순위표 (Phase 2 착수 순서 근거 — A-2 확보 시 확정)

| 순위 | 단계 | 환경B(WSL) | 환경A-1(Win) | 판정 | Phase 2 대응 항목 |
|---|---|---|---|---|---|
| 1 | parse | 22.3s (78%) | 0.11s | 데이터량(11.4만 events) 비례 I/O+json.loads. 이벤트 수 113배에 시간 195배 | **케이스 파일**(재실행 재파싱 제거 — §2) + O7(CPU 병렬, WSL서 CPU-bound 여부 A-2와 대조로 판정) |
| 2 | resolve | 2.9s (10%) | 0.001s | 이벤트 수 비례 | O4(resolve 주입 강제) + 케이스 파일 |
| 3 | enrich | 1.8s (6%) | 0.009s | 이벤트 수 비례 CPU | 케이스 파일(이벤트째 캐시로 소멸) |
| 4 | hash | 0.9s | 0.8s (68%) | 데이터량 무관 바닥 비용 존재 — Windows서 지배적 | 케이스 파일 해시원장(fs_hashes) 재사용 |
| — | 서버/대시보드/LLM | 측정 대기 | | | O1(gzip)/O2(인덱스)/O5(스트리밍)는 대시보드 수치 후 |

**중간 결론**: 콜드런 시간의 ~94%(parse+resolve+enrich)가 "이벤트 재구축" 비용 — **케이스 파일(§2)이 1순위 그대로 확정**. 재오픈 시 이 전부가 지문 검증(stat)으로 대체됨. 콜드런 자체 가속(O7 ProcessPool)은 A-2(UNC) 수치로 I/O-bound vs CPU-bound 판정 후 결정.

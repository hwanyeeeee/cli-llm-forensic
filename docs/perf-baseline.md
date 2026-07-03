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

## 환경 A-2 — Windows→WSL UNC (\\wsl.localhost, exe 최악 경로) — **측정 불가(UNC 고장)**

- 측정 시도 결과: 이 기기에서 Windows→WSL 파일공유 자체가 현재 고장 — `\\wsl.localhost\Ubuntu\...`·`\\wsl$\Ubuntu\...` 둘 다 "The specified path is invalid" (2026-07-03, WSL 기동 상태에서도). 6월 실측 당시(exe 42.8s)엔 동작했음 — 그 사이 깨짐.
- 복구: `wsl --shutdown` 후 WSL 재기동(9P 서버 리셋) 또는 Windows 재부팅. **주의: 개발 세션(tmux/Claude)이 WSL에 살아있어 즉시 실행 금지 — 한가할 때.** exe가 WSL 소스를 스캔하려면 어차피 복구 필요(사용자 액션).
- 대체 데이터: 2026-06-18 실측 스모크 — exe 코드경로(UNC 포함) 42.8s / 119,520 events. UNC 페널티 = WSL 네이티브 대비 약 1.5배(42.8 vs 28.5) + 콜드 편차.

## 실험 — parse 스레드 수 대조 (WSL 네이티브, 같은 root·같은 캐시 상태, 2026-07-03)

| 방식 | parse wall | events |
|---|---|---|
| 순차(스레드 1, parse_file 직접 루프) | **12.17s** | 111,601 |
| 현행 ThreadPoolExecutor 32 | **19.93s** | 111,607 |

**판정: 네이티브 FS에서 32스레드는 순차 대비 +64% 손해 — GIL 경합**(json.loads CPU-bound, 스레드는 GIL 직렬화 + 컨텍스트스위치 비용만 추가). 32워커는 UNC 지연 중첩용 설계라 exe(UNC) 경로엔 유효하나 네이티브에선 역효과. → 백로그 **O9(적응형 파싱 동시성)** 신설: root별 UNC/원격=스레드 다수, 네이티브=순차(또는 O7 ProcessPool). 출력 등가성은 (ri,fi) 키 조립이 이미 보장(test_scan_equivalent_to_sequential).

## 대시보드 / LLM 체감 (수동 기록 — 대기)

| 항목 | 측정값 | 비고 |
|---|---|---|
| boot-stage1 (타일+집계) | | DevTools measure |
| boot-stage2 (전체 이벤트) | | |
| /api/events 응답 크기 | | [clfx.timing] bytes |
| 질의 total_ms / llm_ms | | /api/query timings |

## 병목 순위표 (확정 — Phase 2 착수 순서 근거)

| 순위 | 단계 | 환경B(WSL) | 환경A-1(Win) | 판정 | Phase 2 대응 항목 |
|---|---|---|---|---|---|
| 1 | parse | 22.3s (78%) | 0.11s | CPU-bound 확정(스레드 실험: 순차 12.2s < 32스레드 19.9s — GIL). 데이터량(11.4만 events) 비례 | **케이스 파일**(재실행 재파싱 제거 — §2) + **O9 적응형 동시성**(네이티브=순차, 즉효 ~40%) + O7(ProcessPool, 케이스 이후에도 콜드런 남으면) |
| 2 | resolve | 2.9s (10%) | 0.001s | 이벤트 수 비례 | O4(resolve 주입 강제) + 케이스 파일 |
| 3 | enrich | 1.8s (6%) | 0.009s | 이벤트 수 비례 CPU | 케이스 파일(이벤트째 캐시로 소멸) |
| 4 | hash | 0.9s | 0.8s (68%) | 데이터량 무관 바닥 비용 존재 — Windows서 지배적 | 케이스 파일 해시원장(fs_hashes) 재사용 |
| — | 서버/대시보드/LLM | 측정 대기 | | UNC 복구·exe 재빌드 후 수동 기록 | O1(gzip)/O2(인덱스)/O5(스트리밍)는 대시보드 수치 후 |

**결론**: 콜드런의 ~94%(parse+resolve+enrich)가 "이벤트 재구축" 비용. **Phase 2 착수 순서 = ① 케이스 파일(§2 — 재실행 전체 직격) ② O9 적응형 파싱 동시성(콜드런 즉효, 저위험) ③ O1 gzip ④ O2/O4 ⑤ O5/O6(LLM). O7은 ①② 후 재측정으로 필요성 재판단.**

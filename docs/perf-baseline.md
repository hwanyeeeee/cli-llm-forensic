# clfx 성능 베이스라인 (Phase 1 측정 결과)

측정 방법: `python3 scripts/bench.py <root>... --repeat 3` (단계별 median).
브라우저 측: 대시보드 열고 DevTools 콘솔의 `clfx-boot-stage1/2` measure + FETCH_TIMINGS 표.
LLM 측: 질의 후 `/api/query` 응답의 `timings`(intent/search/llm/total, llm_network_ms).
서버 측: 콘솔 stderr `[clfx.timing]` 라인.

주의(I6): 여기 기록되는 시간값은 비결정적 측정치 — 증거 데이터 아님.

## 환경 A — Windows (exe 경로, \\wsl.localhost UNC 포함)

- 실행: `py -3 scripts\bench.py <roots>` (exe와 동일 코드 경로)
- 데이터 규모: (bench 출력 '규모' 줄 붙여넣기)

(bench 마크다운 표 붙여넣기)

## 환경 B — WSL 네이티브

- 실행: `python3 scripts/bench.py <roots>`
- 데이터 규모:

(bench 마크다운 표 붙여넣기)

## 대시보드 / LLM 체감 (수동 기록)

| 항목 | 측정값 | 비고 |
|---|---|---|
| boot-stage1 (타일+집계) | | DevTools measure |
| boot-stage2 (전체 이벤트) | | |
| /api/events 응답 크기 | | [clfx.timing] bytes |
| 질의 total_ms / llm_ms | | /api/query timings |

## 병목 순위표 (Phase 2 착수 순서 근거)

| 순위 | 단계 | 환경A median | 환경B median | 전체 대비 % | Phase 2 대응 항목 |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

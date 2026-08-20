# 개발 상황

## 프로젝트
clfx(AgenTrace) — Codex 아티팩트 지원. 기준서 `docs/codex-지원-엔진스펙.md`(R1~R7 교차검증 확정). read-only·무손실 절대.

## 플랜 단계
- [x] 1단계: actor 정합성 선결(폴백 5곳 → actor_bucket 3버킷) ✓ 420 passed(+7), 리뷰 BLOCK 0
- [x] 2단계: UI unknown 노출(app.js 12지점) ✓ 421 passed, 리뷰 BLOCK 0
- [ ] 3단계: CodexSource + discovery + source registry ← 현재
- [ ] 4단계: 파서 — structural sniffing + legacy/item 2 era
- [ ] 5단계: actor·confidence 귀속 + Event.meta
- [ ] 6단계: SQLite 보조 + attestation
- [ ] 7단계: Codex temp/config + UI 소스 필터
- [ ] 8단계: fixture + 회귀 + real-run

## 현재 작업
- 도구: codex (panel1)
- 위치: 3단계
- 수행 중: 4라운드 BLOCK 3건 해결 확인(439 green). panel0 수동 리뷰 2건 전달
- 비고: 1~2단계 미commit(누적). 리뷰 NIT는 매 라운드 동일(panel0 문서가 diff에 섞임) — 오탐, 무시
- 순서 결정: 1~5단계 → 패널(마감 8/23 23:00) → 6~8단계
- 재시도: 0
- 리뷰라운드: 5 (codex-review.sh rc=126 'Argument list too long' — 누적 미commit diff가 ARG_MAX 초과. panel0 수동 리뷰로 대체)

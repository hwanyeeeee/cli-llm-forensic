# 개발 상황

## 프로젝트
clfx — Claude Code 기록 포렌식 CLI (파싱→분석→질의). 시연: A/B 두 사건 재구성 + actor 규명.

## 플랜 단계
- [x] 1단계: 파싱 (event/sources/paste/parser/CLI parse) ✓ 90e5d39 (36 test, codex RC=0)
- [x] 2단계: 분석 (secrets/attribution/timeline/CLI analyze) ✓ b60b00f (15 test, codex R1→RC=0)
- [x] 3단계: 질의 (engine/llm/CLI query/e2e A·B) ✓ a6a8fd2 (24 test, codex R1~R3→RC=0, cap 1회 연장)
- **MVP 완료** ✓ final-verify real-run OK. 전체 회귀 green.
- [x] 4단계: 웹 대시보드 (뷰 레이어 — 엔진 단일 진실원천 위) ✓ 21ce8ed (13 test, codex R1→RC=0)

## 현재 작업
- 도구: claude (opus·ultracode)
- 위치: 4단계 (UI)
- 위치: 실데이터 hardening (4단계 커밋 21ce8ed 후, final-verify 스모크서 발견)
- 수행 중: 실데이터 검증서 ts 타입 혼재 발견(history=epoch-ms int / transcript=ISO str). timeline 정렬 TypeError → real 데이터(데모 대상) 크래시. event-schema(ts=ISO8601 UTC) 위반. parser ts 정규화 + timeline 방어 지시 송부.
- 재시도: 0
- 리뷰라운드: 0

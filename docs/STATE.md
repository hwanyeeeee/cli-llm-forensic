# 개발 상황

## 프로젝트
clfx — Claude Code 기록 포렌식 CLI (파싱→분석→질의). 시연: A/B 두 사건 재구성 + actor 규명.

## 플랜 단계
- [x] 1단계: 파싱 (event/sources/paste/parser/CLI parse) ✓ 90e5d39 (36 test, codex RC=0)
- [x] 2단계: 분석 (secrets/attribution/timeline/CLI analyze) ✓ b60b00f (15 test, codex R1→RC=0)
- [x] 3단계: 질의 (engine/llm/CLI query/e2e A·B) ✓ a6a8fd2 (24 test, codex R1~R3→RC=0, cap 1회 연장)
- **MVP 완료** ✓ final-verify real-run OK. 전체 회귀 green.
- [x] 4단계: 웹 대시보드 (뷰 레이어 — 엔진 단일 진실원천 위) ✓ 21ce8ed (13 test, codex R1→RC=0)
- [~] 실데이터 hardening: ts 정규화(1b6e3f3) — codex 재리뷰서 timeline 연대순 결함 발견, 수정 중

## 현재 작업
- 도구: claude (opus·ultracode)
- 위치: 실데이터 hardening (codex 정석 재리뷰)
- 수행 중: timeline 연대순 codex 재리뷰 R1~R2 수정·커밋(b699486, ts_key datetime 정렬). 사용자 결정 "푸시 먼저"(UI 틀 급함) → 푸시 진행.
- 후속(푸시 후): ① codex R3 = engine.timeline(start/end) range가 raw ts 비교 → mixed crash(현재 미트리거 경로). ts_key로 수정 필요. ② UI 대폭 수정 = 팀원 담당. ③ 교수님 피드백 8건 spec 작성(9번 Codex 범용화 보류).
- 재시도: 0
- 리뷰라운드: 0 (R3는 후속 분리)

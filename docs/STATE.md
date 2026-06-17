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
- 위치: 피드백 spec brainstorming (+ ts hardening 완결)
- 수행 중: ts 정렬 결함 R1~R3 완결(b699486 ts_key + 27e5936 engine range, codex CLEAN, 92 test). 교수님 피드백 8건 spec brainstorming 중(exe=PyInstaller 단일exe+내장서버 결정). UI 대폭수정=팀원, 9번 범용화 보류.
- 미푸시: b699486 이후(R2 일부)·27e5936(R3) — 다음 푸시 묶음.
- 재시도: 0
- 리뷰라운드: 0

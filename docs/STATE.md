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
- 수행 중: ts 수정을 codex-review.sh로 정석 재리뷰(이전 code-reviewer 폴백 보강). codex R1 BLOCK — timeline.py 정렬키가 혼재 ts에서 크래시는 막지만 연대순 깨짐(str(epoch-ms)가 ISO보다 앞). panel1 수정 지시.
- 재시도: 0
- 리뷰라운드: 1

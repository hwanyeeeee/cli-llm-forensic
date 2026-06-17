# 개발 상황

## 프로젝트
clfx — Claude Code 기록 포렌식 CLI (파싱→분석→질의). 시연: A/B 두 사건 재구성 + actor 규명.

## 플랜 단계
- [x] 1단계: 파싱 (event/sources/paste/parser/CLI parse) ✓ 90e5d39 (36 test, codex RC=0)
- [x] 2단계: 분석 (secrets/attribution/timeline/CLI analyze) ✓ b60b00f (15 test, codex R1→RC=0)
- [x] 3단계: 질의 (engine/llm/CLI query/e2e A·B) ✓ a6a8fd2 (24 test, codex R1~R3→RC=0, cap 1회 연장)
- **MVP 완료** ✓ final-verify real-run OK. 전체 회귀 green.
- [x] 4단계: 웹 대시보드 (뷰 레이어 — 엔진 단일 진실원천 위) ✓ 21ce8ed (13 test, codex R1→RC=0)
- [x] 실데이터 hardening: ts ISO8601 정규화 ✓ b699486+27e5936 (codex CLEAN, 92 test)
- [ ] 5단계: 피드백확장 A (분석·시각화 ③④⑤⑥⑦ + 신규 API) ← 현재

## 현재 작업
- 도구: claude (opus·ultracode)
- 위치: 5단계 피드백확장 A (분석·시각화)
- 수행 중: 피드백 spec(47f3f19) + A단계 plan(37e5570) 완료. 팀원 UI(be9a39b) 머지. panel1에 A단계(Task1~7) 구현 위임. gemma4:e12b 로컬요약, actor분리 집계, 신규 /api/activity·files·keywords.
- 후속 plan: C(MCP ⑧)·B(복구·해시 ①②)·exe 패키징.
- 재시도: 0
- 리뷰라운드: 0

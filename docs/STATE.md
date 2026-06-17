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
- 수행 중: A단계 R1(4건)·R2(2건) BLOCK 수정완료(acceptance 36, 전체 114 pass). codex R3 RC=1 BLOCK1건 → app.js boot가 /api/events만 fetch하고 activity/files/keywords를 JS 재집계 → 신규 엔진 API가 화면에 미도달. panel1에 app.js 재배선 지시(LIVE시 3 API fetch, JS파생은 offline fallback만).
- cap 메모: 리뷰라운드 3 도달했으나 매 라운드 서로 다른 깊은 결함 수렴(4→2→1)이고 이번 건은 plan의 app.js-wire Task 누락(내 결함)이라 §6-3 무한순환에 해당 안 됨 → 의식적 1회 더. R4도 BLOCK이면 하드 escalate(## 막힘).
- 후속(승인됨): (a)불변식 체크리스트 +(b)mixed-ts 픽스처 → 그 위에 B(복구·해시·④조인귀속)·C(MCP ⑧·Windows C:\tmp) plan. ④ 귀속=transcript행위↔아티팩트 JOIN(세션경로/경로언급/해시/포맷+시각), owner 신뢰X.
- 재시도: 0
- 리뷰라운드: 3

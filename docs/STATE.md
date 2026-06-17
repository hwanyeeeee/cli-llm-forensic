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
- 수행 중: R6 3건 수정완료(acceptance 36, 전체 121). codex R7 RC=1 BLOCK2건 = A-plan이 spec §3(route_intent actor질의)·§2/④(키워드 viz actor분리)를 Task화 안 한 누락. 라운드별 공방 대신 **포괄 갭-클로저**(actor질의 end-to-end + 전 시각화 actor분리 self-sweep)로 전환. panel1 위임.
- 후속(승인됨): (a)불변식 체크리스트 +(b)mixed-ts 픽스처 → 그 위에 B(복구·해시·④조인귀속)·C(MCP ⑧·Windows C:\tmp) plan.
- 재시도: 0
- 리뷰라운드: 7 (포괄 갭-클로저)

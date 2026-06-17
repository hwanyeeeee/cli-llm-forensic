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
- [x] 5단계: 피드백확장 A (분석·시각화 ③④⑤⑥⑦ + 신규 API + actor질의) ✓ 0d0382e (전체 134 test, codex R1~R9→폴백 CLEAN, e2e+final-verify OK)
- [x] 후속: multi-root parse + origin 태깅 + UI 소스필터 + (b)mixed-ts 픽스처 ✓ (전체 141)
- [x] 6단계: exe + 인앱 스캔 UX ✓ (Task1~5 + 3.5/4.5/5.1 보강, codex CLEAN, 154 test, final-verify real-run OK). launcher+build-exe.bat(Windows 빌드)·인메모리 스캔·/api/scan·자동탐지(wsl+windows). exe 실제 빌드=사용자가 bat로.

## 현재 작업
- 도구: claude (opus·ultracode)
- 위치: 6단계 완료 → 다음 B plan(복구·해시·④JOIN) 대기
- 수행 중: **6단계 exe+스캔 UX 완료**(Task1~5 + 보강, codex CLEAN, 154 test, final-verify OK). 인자0 실행→브라우저 자동→스캔화면(자동탐지 wsl+windows)→/api/scan 인메모리 parse+analyze→대시보드. exe 빌드는 사용자가 packaging/build-exe.bat(Windows) 실행. 미push(원격 22+ ahead). 다음: B plan(복구·해시 ①② + ④ transcript↔아티팩트 JOIN 귀속) → C plan(MCP ⑧·Windows C:\tmp). 아니면 사용자 브라우저 walkthrough.
- 후속(승인됨): (a)불변식 체크리스트[완료, plan.md] +(b)mixed-ts 픽스처 → 그 위에 B(복구·해시·④조인귀속)·C(MCP ⑧·Windows C:\tmp) plan. ④귀속=transcript↔아티팩트 JOIN, owner 신뢰X.
- 재시도: 0
- 리뷰라운드: 0 (6단계 Task별 codex 리뷰 → 최종 CLEAN)


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
- 위치: P1 서버 perf 캐시 위임 중
- 진행: FE1 타임라인 가상화 완료·커밋(171, 무손실) + 레이아웃 완료·커밋 f072ccf(창채움 maximized+좌/우 패널 resize:vertical, 중앙 타임라인 제외, 171). **사용자 요청: 이후 codex 리뷰 생략(빠른반복) — acceptance+배선만 보고 커밋.** 사용자가 FE1+레이아웃 재빌드·검증 중. **P1 서버캐시 panel1 위임**(엔진 __init__ 1회 정렬+norm 메모이즈, activity/files/keywords/events_payload 결과 캐시, 엔진 교체시 무효화 — UI 무충돌, 무손실). 다음: P2b 전송 페이지네이션(필요시) → B plan.
- 진행: 파일단위 진행률 위임(ClaudeSource on_file 훅+사전 파일수 카운트 parse+enrich 두 패스, scan_to_engine 파일단위 on_progress, UI 경과시간/ETA, cli.parse_source_tagged 분리, 결정적 병합).
- **대기 큐(순서)**: (A)perf 최적화 (B)레이아웃. 둘 다 무손실(파싱/분석 절대 안 줄임 — 사용자 강제약). 진단 완료(서브에이전트):
  - 멈춤 주범=클라가 11.7만 이벤트 DOM 통째 렌더(app.js:268 renderTimeline innerHTML, 필터/클릭마다 전체 재렌더) + /api/events 수십MB JSON 통째.
  - 엔진 질의마다 전량 재정렬·재norm(engine.py, timeline _sort), 집계 매요청 재계산(캐시 없음).
  - **P1 서버**: 엔진 __init__ 1회 정렬+norm_ts/ts_key 메모이즈, activity/files/keywords + events_payload 결과 ServerState 캐시(엔진 교체 시 무효화).
  - **P2 클라+레이아웃**: 타임라인 가상화(날짜 접기, 펼칠때만 카드; 전 데이터 메모리 유지)·renderDetail 부분갱신·target→index Map·/api/events 표시 페이지네이션(전량 도달가능) + 창 채움(.wrap fluid/pywebview resizable) + 패널 resize:vertical.
  - FORBIDDEN: /api/events N개 캡·서버측 이벤트 필터 축소(증거 누락). pywebview 메인스레드/serve 데몬/스캔 워커스레드는 이미 정상.
  - 레이아웃 지시서 준비됨: /tmp/panel1-layout.txt. perf는 P1/P2로 분할 위임 예정.
- 완료·커밋: 진행률 바(on_progress+/api/scan/progress+폴링 % 바, codex R1→CLEAN, 169 green, final-verify OK). **사용자 재빌드 1회로 누적 전부 적용**: GUI 창·WSL탐지(wsl.exe -l -q)·gemma4 대화형(모든질의)·exists 필터·병렬 스캔·진행률 바. 다음: B plan(복구·해시·④JOIN)→C(MCP·tmp). 미push(다수 ahead).
- 수행 중: **GUI+WSL탐지+gemma4 대화형 전부 완료·커밋**(codex R1~R2→CLEAN, 163 green, final-verify OK). 모든 질의 gemma4 대화형(answer_only_summary: 웹=항상, CLI=요약만), 빈결과 LLM스킵, 증거=엔진 불변, localhost ollama. **사용자: build-exe.bat 재빌드 1회 → WSL탐지+대화형 gemma4+빈결과안전 전부 적용.** 스모크는 clfx serve만(launcher.py는 webbrowser.open 폴백→Windows Chrome 팝업, 금지). 다음: B plan(복구·해시·④JOIN)→C(MCP·tmp=\\wsl.localhost\Ubuntu\tmp). 미push(32 ahead).
- 후속(승인됨): (a)불변식 체크리스트[완료, plan.md] +(b)mixed-ts 픽스처 → 그 위에 B(복구·해시·④조인귀속)·C(MCP ⑧·Windows C:\tmp) plan. ④귀속=transcript↔아티팩트 JOIN, owner 신뢰X.
- 재시도: 0
- 리뷰라운드: 진행률 바 R1(2 BLOCK: 비결정병합·버튼stuck)→CLEAN. 커밋, 169 green.


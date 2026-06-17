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
- 위치: 배치5 완료 — 사용자 재빌드·검증 대기
- 진행: batch5 완료·커밋 e1fc240(유연날짜 6/15→on_date 월-일, 소스 체크 origin만 질의답변, answer_overview 이벤트리스트 리팩터, 198 green, JS OK). **재빌드 후 검증**: "6/15 요약해줘"(소스 칩 win만/둘다 조합)→ 그 플랫폼·그 날만 요약. date-scoped라 컨텍스트 작아 gemma4 빠름(+프리웜). 다음(승인대기): B plan(복구·해시·④JOIN)→C plan(MCP·tmp).
- 진행: batch4 완료·커밋 a59a812(순수 idf로 this/be/that 강등, LLM 프리웜+keep_alive+num_predict384+timeout300, 193 green). batch5 위임(/tmp/panel1-batch5.txt): (1)유연 날짜 "6/15"·"6월15일"→on_date 월-일(MM-DD, engine.on_date d[5:10] 매칭). 사용자가 "6/15 요약"으로 작은 컨텍스트 질의 예정. (2)소스 칩 체크된 origin만 질의 답변 — query_payload origins 필터+_by_origins, answer_overview를 이벤트리스트 기반 리팩터, server /api/query?sources= 파싱, app.js ask가 srcActive 동봉. 파싱 전량·답변범위만 체크 origin.
- 진행: batch3 재빌드서 2건 잔존 → batch4 위임(/tmp/panel1-batch4.txt). (1)키워드 be/this/that 여전 — 원인=sklearn 평활 idf의 +1 바닥값이 ubiquitous 토큰 살림 → **순수 idf=ln(N/df)**(df==N→0 강등, N<=1 count폴백). 하드코딩 아님. (2)LLM "timed out"(연결OK 127.0.0.1, refused아님) — 원인=gemma4:12b CPU 콜드로드+느린생성 120s초과 → **프리웜(스캔완료시 백그라운드 모델로드)+keep_alive 30m+num_predict 384+timeout 300**. 둘 다 백엔드(keywords.py/llm.py/server.py).
- 진행: 배치3 완료·커밋 5dccb00(즉시 로딩표시·리사이즈 콘텐츠 flex채움·키워드 TF-IDF+숫자컷·LLM host 127.0.0.1+llm_error표면, 190 green, JS OK). **재빌드 후 검증**: ①빈화면 없이 즉시 "불러오는중" ②패널 늘리면 콘텐츠 채움 ③키워드 observation/2026/this 강등·수사어 상위 ④"타임라인 요약해줘"=gemma4 문장(127.0.0.1 연결). ④ 여전히 digest면 라벨에 사유(timeout/refused) 표시→원인확정. 다음(승인대기): B plan(복구·해시·④JOIN)→C plan(MCP·tmp).
- 진행: 재빌드 검증서 4건 발견 → batch3 위임(/tmp/panel1-batch3.txt). (1)부팅 빈0화면→await전 즉시 로딩표시 (2)리사이즈해도 콘텐츠 원래칸 갇힘→내부 flex:1채움(.files max-height제거) (3)키워드 여전히 노이즈(observation/2026/this/tool)→**TF-IDF**(문서=세션, idf로 ubiquitous 강등=e-discovery 실무표준)+숫자컷 (4)gemma4 진짜 미연결(개요 작은 프롬프트도 digest)=원인 localhost→IPv6 ::1, ollama는 127.0.0.1만→**host 127.0.0.1**+llm_error 표면화. 사용자 요청: 키워드는 실무 알고리즘(TF-IDF) 사용. #1/#2/#4ui=프론트, #3/#4=백엔드.
- 진행: build-exe.bat 견고화 커밋 10cdb94(taskkill+클린 build/dist/spec+--noconfirm+산출물 시각출력 — "재빌드해도 exe 최신화 안됨" 해결: 원인=실행중 락/캐시). 이제 재빌드만 해도 항상 최신. CRLF/ASCII 확인.
- 진행: 백엔드2 완료·커밋 2faf57e(LLM 프롬프트 경계 _prompt_context+timeout120→요약 정상·citations 전량, 키워드 대화한정+불용어+min_count→for/mnt/user 제거, 186 green). **누적 미적용분(재빌드 1회로 전부 적용)**: 프론트4(d6c4bf2 점진부팅·거터·최신순·칩)+백엔드2(2faf57e LLM요약·키워드)+백엔드(7e1e4f9 개요답변, 2d0be63 stats). 검증포인트: ①대시보드 즉시(타임라인만 로딩) ②컬럼 경계 드래그 ③"타임라인 요약해줘"=문장 ④"이 사람 주로 뭐해?"=개요답 ⑤키워드 for/mnt/user 없음 ⑥최신순 ⑦칩 색/취소선. 다음(승인대기): B plan(원본복구·해시대조①②+④transcript↔아티팩트 JOIN귀속)→C plan(MCP⑧·tmp retention). 미push(다수 ahead).
- 진행: 프론트4 완료·커밋 d6c4bf2(점진부팅+/api/stats타일·컬럼거터·타임라인최신순·필터칩 색/취소선, 182 green). ollama 정상 확인(gemma4:12b 떠있음, 코드모델명 일치). **백엔드2 panel1 위임**(/tmp/panel1-backend2.txt): (1)"타임라인 요약해줘"가 로그덤프 — 원인=전체이벤트(1147~11.7만) LLM프롬프트 투입→타임아웃/컨텍스트초과→digest폴백. fix=_prompt_context로 프롬프트 경계(대량=집계헤더+표본60)+timeout120, citations 전량유지(무손실). (2)키워드 for/user/mnt 노이즈 — fix=action prompt/response만 집계+불용어확장+min_count>=2(요구문서 키워드-추출-개선안.md). 둘 다 백엔드(llm.py/keywords.py), 형식 유지. 다음 재빌드 1회로 프론트4+백엔드2 전부 적용.
- 진행: 사용자 피드백 5건. **백엔드(panel0 직접, 커밋완료)**: ①막연한질문→answer_overview(전체 행위 결정적 집계 근거 gemma4 답, 7e1e4f9) ②빈결과 mode "empty"(LLM미연결 오표기 분리) ③GET /api/stats 경량타일(2d0be63, events 직렬화 전 즉시표시). **사용자 지시: 이후 구현은 panel1에 위임(panel0 직접구현 금지).** **프론트4 panel1 위임**(/tmp/panel1-frontend4.txt): (1)점진부팅(stats+집계 먼저, events 백그라운드, 타임라인 로딩표시) (2)컬럼 경계선 거터 드래그(--cl/--cr) (3)타임라인 최신순+최신날 자동펼침 (4)필터칩 색채움/취소선. **미해결 의존: 로컬 LLM 연결 — exe(Windows)에서 ollama localhost:11434 도달 여부 사용자 확인 필요**(도달X면 host 설정/탐지 추가).
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


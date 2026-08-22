# 개발 상황

## 프로젝트
clfx(AgenTrace) — Codex 아티팩트 지원. 기준서 `docs/codex-지원-엔진스펙.md`(R1~R7 교차검증 확정). read-only·무손실 절대.

## 플랜 단계
- [x] 1단계: actor 정합성 선결(폴백 5곳 → actor_bucket 3버킷) ✓ 420 passed(+7), 리뷰 BLOCK 0
- [x] 2단계: UI unknown 노출(app.js 12지점) ✓ 421 passed, 리뷰 BLOCK 0
- [x] 3단계: CodexSource + discovery + source registry ✓ 441 passed, 리뷰 5라운드 BLOCK 14건 해소, 커밋 ed9769b
- [x] 4단계: 파서 — structural sniffing + legacy/item 2 era ✓ 451 passed. 실데이터 351파일 30,232 이벤트, unsupported_schema 0
- [x] 5단계: actor·confidence 귀속 + Event.meta ✓ 456 passed. 실데이터 write 2,091건 전부 medium 재등급, 과계수 0
- [x] 6단계: SQLite 보조 + attestation ✓ 461 passed. 실데이터 DB 6개·threads 348·turns 120·커버리지 경고(353/350/24)·manifest 16파일 해시
- [x] 7단계: Codex temp/config + UI 소스 필터 ✓ 468 passed. 질의 라우터 write/search 매핑 실사용 확인
- [x] 8단계: fixture + 회귀 + real-run ✓ 473 passed, final-verify real-run OK
- [x] 귀속 정정: unknown 151→0, meta.source 키 이름 버그 수정 ✓ 67ea3a8, 474 passed
- [x] 9단계: exe 패키징 검증 ✓ 19.6MB 재빌드, PYZ에 codex_parser·codex_sqlite 프리즈 확인(hidden-import 불필요), 위임 warning 경로 재작성 버그 수정
- [x] 10단계: Codex 정확도 측정 ✓ 3시나리오 각 100건 100.0%, era별 분리 집계, 한계 §5 명시. 측정 중 meta.source merge 소실 버그 발견·수정(2,784→4,038)
- [x] 11~22단계: 유출 시나리오·origin_channel·패널 수치동결·iOS 슬롯·A1 조판·가독성·면적 재배분·최종검수·규정폰트 재빌드 ✓ 515 passed +1 skip, 커밋 c6a1858

## 현재 작업
- 도구: claude (panel1)
- 위치: 24단계 완료 → 25단계 (exe 재빌드 검증)
- 수행 중: panel1=25단계, panel0=검수
- 24단계 검수(2026-08-22): 568 passed. 브라우저 실측 — /api/events 225.4MB→**0.53MB**, 전체 전송 **2.52MB**, JS 힙 570→**12MB**, DOM 26,032→**6,632**. raw 숫자 0. 침묵 절단 없음 — 타임라인·파일목록 '더 보기'가 남은 건수를 정확히 표기(1,778 / 3,515). 상세 패널이 origin_os_candidates 를 '단정 불가 · 후보 android' 로 정확히 렌더. 회수율 12.9% 로 문서 통일
- 23단계 검수(2026-08-22): 562 passed. 브라우저 실측 — bypass 배지 잘림 2,162→**0**, 최대 이벤트 1,612px→**118px**, 마커 3종 실데이터 판독 OK(claude 2종·codex 1종, signal=configured). markers.py 가 규칙을 코드로 강제(휘발성 마커는 none 불가). **잔여 결함**: 새 원격 뷰가 num() 미경유로 숫자 6개 raw(1257·5112·3311·136368·13266) → 24단계에 이월
- panel0 실측 검증(2026-08-22): 파이프라인 전 구간 green — parse 146,048건 25s · analyze 6s · query 20건 530ms · attestation all_read_only=true · actor unknown 0. UI 결함 4건 발견 → ①②④는 23단계 추가분, ③(전량 225MB 전송·힙 570MB)은 24단계로 분리
- 범위 결정(2026-08-22): **패널·포스터 제작은 이 저장소에서 하지 않는다. 도구 개발만 한다.**
- 소유권: `docs/AgenTrace-아티팩트-인계문서.md` 는 **사용자가 직접 관리**한다 — 에이전트 편집 금지(읽기만). `tests/test_panel_numbers.py` 가 이 문서를 읽어 종합문서와 동결값이 일치하는지 검사한다(쓰지는 않는다).
- 범위 결정(2026-08-22): **폰 취득본 파싱은 하지 않는다.** clfx 는 로컬 아티팩트만 읽는다. 원격/로컬 판별은 로컬 파일만으로 서기 때문이다 — Claude=세션 JSONL `promptSource`, Codex=`logs_2.sqlite` `client_name`. 폰은 결속·정황 증거라 도구가 없어도 문서로 다룬다. 인계문서 §5 의 iOS Manifest 메타·DBMessageChunk 재조립 2건은 이 결정으로 **범위 밖**.
- 패널 수치 동결 시각: 2026-08-22 17:20
- 별도 세션: 모바일 원격제어 4시나리오(docs/모바일-원격제어-분석-계획.md)
- 실사용 확인: parse→analyze→query 실데이터 36,894 이벤트, file:line 인용 동작
- 비고: 브랜치 feat/codex-support, HEAD c6a1858. 미push 25커밋 — 사용자 결정 대기.
- 포스터: 이 저장소에서 제작하지 않는다(2026-08-22 결정, panel/ 제거). 발표물은 팀원이 `docs/AgenTrace-아티팩트-인계문서.md` 로 만든다.
- 리뷰방식: 헤드리스 codex exec 리뷰 2회 연속 타임아웃(10분·25분) → panel0 수동리뷰 + 실데이터 전수검증을 1차 게이트로. 8단계 후 panel1에 리뷰어 모드로 최종 교차검토
- 순서 결정: 1~5단계 → 패널(마감 8/23 23:00) → 6~8단계
- 재시도: 0
- 리뷰라운드: 0
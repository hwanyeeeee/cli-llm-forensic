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
- 위치: 22단계 완료 — panel1 대기(idle)
- 수행 중: 없음. 사용자 지시로 panel1 대기 — iOS(S1·S2) 실측 도착 시 투입(fm_remote 레인 · 종합문서 §10.1 · test_panel_numbers iOS skip 해제, 약 30분)
- 패널 수치 동결 시각: 2026-08-22 17:20
- 별도 세션: 모바일 원격제어 4시나리오(docs/모바일-원격제어-분석-계획.md)
- 실사용 확인: parse→analyze→query 실데이터 36,894 이벤트, file:line 인용 동작
- 비고: 브랜치 feat/codex-support, HEAD c6a1858. 미push 25커밋 — 사용자 결정 대기.
- 포스터: panel/draft-a1.{svg,png,jpg} 제출 가능. 검산 위반 0 · 최소 글자 8.0pt · 규정 폰트(나눔스퀘어) · panel/README.md 인계 체크리스트
- 리뷰방식: 헤드리스 codex exec 리뷰 2회 연속 타임아웃(10분·25분) → panel0 수동리뷰 + 실데이터 전수검증을 1차 게이트로. 8단계 후 panel1에 리뷰어 모드로 최종 교차검토
- 순서 결정: 1~5단계 → 패널(마감 8/23 23:00) → 6~8단계
- 재시도: 0
- 리뷰라운드: 0
---
target: cli
build: pip install -e ".[dev]"
test: python3 -m pytest tests/ -q
run: python3 scripts/bench.py tests/fixtures/dot-claude --repeat 1
---

# 플랜 — 성능개선 Phase 2a (취득계층 재설계: O9·O10·O11)

- 상세 플랜: `docs/superpowers/plans/2026-07-03-clfx-성능개선-P2a-취득계층.md` (Task 1~5 TDD, 실코드 포함)
- 스펙: `docs/superpowers/specs/2026-07-02-clfx-성능개선-design.md` §3 O9/O10/O11 · 실측: `docs/perf-baseline.md`
- **절대 원칙**: 무손실(모든 경로 byte-identical — 등가성 테스트)·완전성(위임 실패=폴백+사유 표면화, 탐지 타임아웃=warnings)·read-only(스테이징·출력은 증거 밖 임시디렉터리, 헬퍼 `python3 -B -E -s` 발자국 최소)·결정성(정렬)

## 1단계: O9 적응형 동시성 + O10 탐지 타임아웃 (플랜 Task 1~2)
네이티브 root=순차/원격(`//`·`/mnt/`)=스레드풀 분리 실행((ri,fi) 조립 불변) + 소스탐지 존재확인 타임아웃→warnings 표면화(+UI).

acceptance: python3 -m pytest tests/test_o9_concurrency.py tests/test_discover_timeout.py tests/test_discover.py tests/test_web_app_js.py -q

## 2단계: O11 코어 — wsl_helper + wsl_delegate (플랜 Task 3)
WSL 내부 파싱 헬퍼(같은 parse_file/enrich 코드) + 스테이징(SHA-256)·실행·회수·경로재작성. 핵심 = 직접 파싱과 등가성 테스트(로컬 러너 주입).

acceptance: python3 -m pytest tests/test_wsl_delegate.py -q

## 3단계: O11 통합 + 패키징 (플랜 Task 4~5)
scan_to_engine 위임 분기(Windows+UNC+wsl.exe시)·DelegateError 폴백·engine.delegate_info → attestation 표면화 + exe에 clfx 소스 동봉(--add-data clfx;clfx_src).

acceptance: python3 -m pytest tests/ -q && CLFX_NO_DELEGATE=1 python3 -m pytest tests/test_wsl_delegate.py -q

## 완료 후 (panel0/사용자)
- 전체 회귀 + final-verify → 커밋 검증.
- 사용자: `wsl --shutdown`으로 9P 복구 → exe 재빌드 → WSL 소스 스캔(위임 경로 실측) + A-2 UNC bench 수치 확보 → perf-baseline.md 갱신 → Phase 2b(케이스 파일) 플랜.

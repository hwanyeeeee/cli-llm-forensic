# clfx 교수님 피드백 확장 — 설계 (최종)

날짜: 2026-06-17 · 상태: brainstorming 완료(10+ 문답) + 팀원 UI 개편(be9a39b) 통합.
선행: MVP(parse/analyze/query) + 웹 대시보드 완성. 실측 원리 = `docs/실측-temp-원본보존-원리.md`. 피드백 원문 = `docs/교수님-피드백.md`. UI 변경 = `docs/UI-변경사항.md`.

## 목적

교수님 피드백 8건을 clfx에 반영한다(9번 Codex/Gemini 범용화는 보류). 행위 주체(사람 vs 에이전트) 판별을 중심으로 원본 보존·복구·시각화·외부 흔적까지 확장하고, **Windows 단일 exe**로 배포한다.

## 불변 원칙

- **엔진(결정적)이 단일 진실원천.** 검색·귀속·탐지·집계는 엔진. LLM(로컬 gemma4)은 **요약만**. 증거 주장은 엔진이.
- **UI는 호출·표시만**(`/api/*` fetch). 집계·로직을 JS로 재구현하지 않는다(증거 분기 방지).
- **증거 외부전송 0** — 요약 LLM도 로컬(ollama). 포렌식 데이터가 머신을 떠나지 않는다.
- **정직성** — 시간의존(temp ~30일 소실)·환경의존(n=2 교차확인)을 과장 없이 명시.

## 확정 결정 (brainstorming 2026-06-17)

| # | 항목 | 결정 |
|---|---|---|
| 1 | exe 형태 | PyInstaller `--onefile` + 내장 http.server + `webbrowser.open`. Windows 타겟. |
| 2 | 범위 | 8건 한 spec, 구현 **A→C→B 단계화**. |
| 3 | 플랫폼 | Windows 타겟 + 크로스 코어. 대상 = **단일 PC**(WSL 자료 + Windows 자료 모두, `/mnt/c` 접근). |
| 4 | 복구 원리 | Claude 자체 보존(uploads/file-history+trackedFileBackups/backups) — 실측됨. |
| 5 | 복구 방향 | Claude 아티팩트 **1차** + 디스크 carving **보조**(외부도구/후속). |
| 6 | 주체 왜곡보정 | **모든 집계·시각화 actor 분리**(user/agent). |
| 7 | 프롬프트 요약 | 로컬 ollama **gemma4:e12b**, 미실행 시 digest fallback. |
| 8 | 키워드 | 경량 빈도 + 수사사전(결정적, 의존성 0). |
| 9 | MCP | 흩어진 `.mcp.json` + 글로벌 + transcript MCP 호출 **통합 1차** + Prefetch 상관 2차. |
| 10 | 해시대조 | 수집본(uploads/paste/file-history) sha256 ↔ **사용자 지정 원본**. |

## 아키텍처

```
clfx.exe (PyInstaller --onefile, Windows)
 ├─ 엔진 (parse/analyze/query) ── 결정적 단일 진실원천 (확장)
 ├─ 내장 http.server (web/server.py) ── /api/* 제공 (신규 엔드포인트 추가)
 ├─ static (web/static/) ── 팀원 개편 UI (3컬럼·히트맵·도넛·파일목록·코파일럿)
 └─ 로컬 ollama 클라이언트 (gemma4:e12b, localhost:11434) ── 요약만, fallback digest
실행: clfx.exe analyzed.jsonl → 내장서버 → 브라우저 자동 오픈 → 대시보드
```

## 1. 수집 확장 (parse / 신규 collector)

기존 history·transcript에 더해 실측 원리 기반 신규 소스:

- **`uploads/<session>/<hash>-<원본명>`** → 업로드 원본 파일·메타(①). 원본 그대로 보존됨.
- **`file-history/<id>/<contenthash>@v<N>`** + transcript `file-history-snapshot.trackedFileBackups` 매핑 → 편집 전/후 버전(②, 복구원).
- **`/tmp`·`/tmp/claude-<uid>/<proj>/<session>/tasks`·`shell-snapshots/`** → 에이전트 temp 작업 흔적. `/tmp` 공용이므로 **에이전트 귀속 휴리스틱**(mktemp 패턴·claude-uid·mtime 상관·내용).
- **MCP 설정 통합**(⑧): 프로젝트별 `<proj>/.mcp.json` + 글로벌 `~/.claude.json` mcpServers + transcript의 MCP 도구 호출 → "어느 프로젝트가 어떤 MCP 썼나" 통합.
- **2차/보조**: Prefetch(`/mnt/c/Windows/Prefetch/*.pf`), 디스크 carving(외부도구). → C·B 단계.

**Event 스키마 영향**: 신규 수집이 Event로 들어오면 `action` 값 추가(예: `upload`/`recover`/`mcp`) 또는 별도 레코드 타입 필요. **`docs/event-schema.md` PR로만 변경**(단일 진실원천). 구체 형태는 구현 plan에서 확정.

## 2. 분석 확장 (analyze)

- **actor 분리 집계**(④): 모든 집계·시각화가 user/agent 별도 계열. "에이전트 사용 → 사용자 오인" 왜곡 원천 차단. engine에 actor 필터 추가.
- **키워드 빈도 + 수사사전**(⑥): 결정적. 공백/구두점 분리 + 한국어 불용어·조사 경량 제거 + 수사 위험키워드 사전 매칭. 집중형(특정 시점 몰림)/지속형(장기 분산) 패턴 판정. 의존성 0(형태소기 미사용).
- **sha256 대조**(①): 수집본(uploads/paste 본문/file-history) sha256 계산 → 사용자 지정 "기밀/원본 파일" 해시와 대조. 일치 = "이 파일이 LLM에 올라갔다" 유출 입증. (uploads 앞 8hex는 sha256 아님 → 별도 계산.)
- **복구**(②): Claude 아티팩트 우선 — uploads 원본 + file-history 버전(trackedFileBackups 매핑)으로 편집 전 상태 복원. 디스크 carving은 Claude 미추적분만(외부도구).
- **시크릿**: 엔진 `secret` 태그는 **유지**(무수정, 증거 보존). 표시 정책은 §5.

## 3. 질의 / 요약

- `route_intent`에 **actor 인식**("사용자/에이전트/누가") + on_date·who_did에 actor 필터.
- "X월 X일 사용자 행위 요약해줘" → `on_date(day)` + `actor==user` 필터 → **gemma4:e12b 요약**(인용 source file:line 포함). ⑦
- ollama 미실행/모델 없으면 **digest fallback**(기존 패턴). 증거는 결정적 엔진, 문장만 LLM.

## 4. 대시보드 + 신규 API (팀원 UI 통합)

팀원 UI(`be9a39b`, static 3파일)는 3컬럼 그리드·통계타일(A/B/bypass)·달별 히트맵·키워드 도넛·날짜 아코디언·파일목록·AI 코파일럿으로 개편됨. **현재 `/api/keywords`·`/api/activity`를 클라이언트 집계(placeholder)** 중 → **코어가 신규 API 제공, UI는 fetch만 교체**:

| 엔드포인트 | 내용 | 피드백 |
|---|---|---|
| `GET /api/activity?by=day\|month` | 활동량 집계(actor 분리) — UI 히트맵 | ⑤ |
| `GET /api/keywords` | 키워드 빈도(수사사전·집중/지속 패턴) — UI 도넛 | ⑥ |
| `GET /api/files` | 접근파일 목록(actor 구분·횟수·태그) | ③ |
| `/api/query` summarize (기존) 또는 `/api/prompts/summary` | 프롬프트 요약 | ⑦ |
| `GET /api/hash-compare?ref=<원본해시>` | 해시 대조 결과 — "기밀 파일 일치" 패널 | ① |
| `GET /api/recovery` | 복구 가능 파일(uploads/file-history) | ② |
| `GET /api/mcp` | MCP 통합 목록(프로젝트별 서버) | ⑧ |

- UI ⑤는 막대 대신 **GitHub식 히트맵(달별 색구분)** 으로 구현됨(팀원 결정: "막대는 대량 데이터서 한계").
- 신규 API 응답은 기존 계약과 동일하게 **엔진이 집계한 JSON**. UI는 차트로 그리기만.

## 5. 시크릿 표시 정책 (팀원 결정 채택)

- **엔진 무수정** — `analyze`는 `secret` 태그·`‹secret›` 마스킹을 계속 산출(증거 보존).
- **UI `normalize()`가 표시 단계에서만 `secret` 태그 제거.** 핵심 지표 자리는 **`bypass 모드`(권한 귀속)** 로 대체.
- 근거: 범용 자격증명 정규식 ≠ 기밀 파일 동일성. "유출 판정"은 도구가 단정 못 함(회사별 기밀 기준 상이, 오탐). 진짜 유출 입증 = **해시 대조**(①). 도구는 주체·권한·시각 집계까지, 판정은 사람 몫(발표 §4 금지표 정합).

## 6. 한계 (정직 — 발표·보고서에 명시)

- **temp ~30일 소실**: `/tmp` 흔적은 systemd-tmpfiles cleaner(매일, `D /tmp 30d`)가 30일 경과분 삭제. 접근·재부팅·환경따라 변동. 빠른 수집 필수. paste-cache 35% 소실과 같은 시간의존.
- **환경의존**: `/tmp` 내용·MCP 설정 위치·systemd 활성도 환경별 상이(예 `.wsl-screenshot-cli`는 사용자 설치물, 팀원 머신엔 없음). **n=2 교차확인**(논문대비 §C) + 버전핀(`claude --version`).
- **FAT32 디스크복구·Prefetch 파싱** = 난이도·OS의존 높아 후속/외부도구(B·C 단계).
- **gemma4 MTP 가속**(3배)은 vLLM+NVIDIA 전제 → 현 Intel/ollama 환경 직접 적용 불가. "성능 후보: ollama speculative decoding" 메모, MVP는 e12b 기본.

## 7. 구현 단계화

- **A — 분석·시각화** (③④⑤⑥⑦ + 신규 API + 팀원 UI 연결): 기존 Event 위, 실현 확실·빠름·exe 직결. **우선.**
- **C — MCP** (⑧): `.mcp.json` 통합 + transcript MCP 호출 + Prefetch 상관(보조).
- **B — 복구·해시** (①②): Claude 아티팩트 복원 + sha256 대조 + 디스크 carving(외부).
- **배포** — exe 패키징(PyInstaller `--onefile`, `_MEIPASS` static 경로 보정, `packaging/launcher.py`): 코어 담당. 가이드 `docs/exe-패키징-UI-가이드.md`. 각 단계 green 후 또는 마지막.

각 단계는 자체로 동작·테스트 가능한 단위. TDD·codex 교차리뷰는 기존 하네스 루프 유지.

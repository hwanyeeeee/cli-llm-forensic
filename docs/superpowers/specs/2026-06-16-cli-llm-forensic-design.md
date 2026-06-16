# 설계 명세 — CLI LLM 에이전트 포렌식 도구 (cli-llm-forensic)

날짜: 2026-06-16
대상: 2026-1 네트워크보안 기말평가 (1팀, 2인) + 한국디지털포렌식학회 연계 가능성
상태: 설계 확정 초안 (브레인스토밍 산출물)

> 작업명 `cli-llm-forensic`. 제품명 후보: **AgentTrace / Accomplice / CAFE(CLI Agent Forensic Examiner)** — 팀이 확정.

---

## 0. 한 줄 정의

**Windows/WSL2 환경에서 CLI 코딩 에이전트(Claude Code·Codex CLI·Gemini CLI)가 남긴 아티팩트를 수집·파싱·분석해 보안 사건을 재구성하고, 분석 결과를 AI와 자연어로 질의하는 호스트 포렌식 도구.**

- 복구(carving)가 목적이 아니라 **분석·재구성**이 목적. 단 삭제 증거는 *보조적으로* 복구.
- 메모리 포렌식 아님 — 100% 디스크 아티팩트.
- "AI를 포렌식에 활용"이 아니라 **"AI 사용 흔적(아티팩트)을 포렌식"** — 이 구분이 정체성의 핵심.

---

## 1. 배경·필요성·의의 (= 논문 서론)

### 1.1 문제
CLI 코딩 에이전트(Claude Code 등)는 파일시스템 접근·명령 실행·외부 서비스 연동을 단일 워크플로에 통합한 **에이전틱 시스템**이다. 개발 생산성을 올리지만, 동시에:
- 에이전트가 **읽고 처리한 모든 것이 제3자 LLM 제공자(클라우드)로 전송**된다 (소스·`.env`·키 포함).
- 외부 공격자가 에이전트를 **무기화**하거나(공급망), 에이전트가 **자율로 민감파일을 읽어** 유출하거나, **파괴적 행위**를 수행할 수 있다.

### 1.2 위협이 실재한다는 근거 (실제 사건)
- **Nx "s1ngularity" (2025.8)** — 악성 npm 패키지가 설치된 AI CLI(`claude --dangerously-skip-permissions`, `gemini --yolo`, `q --trust-all-tools`)를 무기화해 파일시스템 시크릿을 스캔·유출. **2,180 계정·7,200 repo·2,349 시크릿** 노출. (Snyk·Wiz·StepSecurity·GitGuardian)
- **Anthropic GTG-1002 (2025.11)** — 국가행위자가 Claude Code를 MCP로 자율 첩보에 사용(벤더 주장, 회의론 병기).
- **Replit 에이전트 운영 DB 삭제 (2025.7)** — 코드 프리즈 중 라이브 DB 삭제.
- **Claude Code의 `.env` 자율 읽기·전송** — GitHub 이슈 #24185·#44868, RyotaK/GMO Flatt CVE(GitHub Action이 `/proc/self/environ` 읽어 CI 시크릿 노출, v1.0.94 수정). Claude `auto` 모드 문서가 *명시적으로* "`.env` 읽어 해당 API에 자격증명 전송"을 기본 허용.
- 참고 선례: 삼성 ChatGPT 소스 유출(2023), Cursor CVE(CurXecute·MCPoison), Copilot CamoLeak, 악성 MCP `postmark-mcp`(첫 ITW).

### 1.3 기존 통제의 사각 (왜 *포렌식*이 필요한가)
- **DLP/CASB**(Purview 등)는 genAI **웹앱·업로드·클립보드** 중심. CLI 에이전트는 **브라우저 밖**에서 allowlist된 API 엔드포인트로 스트리밍 → 브라우저 DLP·클립보드 훅 미발동. → "불가시"가 아니라 **커버리지 갭**.
- **WSL2 사각** — WSL2 안 프로세스는 Windows **EVTX(4688)·EDR가 못 봄**(경량 VM). 호스트 IR의 명백한 블라인드 스팟. ← *이 사각이 우리 도구의 존재 이유를 오히려 강화.*
- **포렌식 도구 부재** — 사건 후 "무엇이·언제·어떻게 샜나/실행됐나"를 조사할 도구가 Windows/WSL2엔 없음.

### 1.4 의의
사건 후, 네트워크·메모리 캡처 없이 **로컬 디스크 아티팩트만으로** CLI 에이전트發 사건을 재구성·증거화한다. AV/DLP/EDR가 놓친 사후 증거를 무결성 보장하에 복원해 **IR·감사·소송·규제 대응**을 지원.

---

## 2. 관련 연구·차별점

| 선행 | 무엇 | 한계/빈틈 |
|---|---|---|
| **Kim & Jeong, "From assistant to accomplice: A forensic framework for CLI coding agents in incident response"** (SKKU, preprint) — SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6725750 | CLI 코딩 에이전트 포렌식 *프레임워크* — 다층 증거모델(Interaction/Operation/Resource/Host)·조사프로세스·재구성등급·3에이전트 아티팩트 비교·케이스(MCP-exfil, Hooks-RCE) | **Ubuntu 한정** · **수동 프레임워크(도구 없음, "자동 상관은 향후과제")** · 시크릿/PII 탐지 없음 · RAG 없음 · 신버전 아티팩트 미반영 |
| Cho 2025 (대화형 AI 포렌식) / Tyagi(모바일) | ChatGPT·Gemini·Copilot·Claude 대화내역 | 클라우드·대화 중심, 에이전트 아님 |
| Jeong 2025 "LangurTrace" | 로컬 LLM *앱* 포렌식 | 데스크톱 앱 한정(CLI 아님) |
| OSS(`coding_agent_session_search`·`claude-history`·`cursor-chat-recovery`) | 세션 검색/뷰 | 단순 열람, 포렌식 분석·복구·무결성 없음 |

### 우리 차별점 (= 위 빈틈을 메움)
1. **Windows/WSL2 호스트 계층** — EVTX 사각·NTFS/ext4(ext4.vhdx) 경계 교차상관 (논문 Ubuntu 미커버).
2. **자동화 도구** — 프레임워크를 구현(수집→분석→리포트 파이프라인).
3. **시크릿/PII 자동 탐지** — transcript·툴출력서 자격증명·키·개인정보 적발.
4. **복구** — `file-history` 체크포인트(편집 전 구버전) + 삭제 세션 카빙(ext4.vhdx JSONL / ChromaDB SQLite).
5. **신버전 신규 아티팩트** — `paste-cache/`·`file-history/`·서브에이전트(`agents/`,`teams/`)·`hooks/`·thinking — 논문 Table2 갱신.
6. **귀속(기제)** — 사람 붙여넣기(`pastedContents`) vs 에이전트 도구실행(`toolUseResult`) 구분.
7. **무결성/custody** — 모든 증거 MD5/SHA256, 분석 전후 무변경 증명.
8. (보조) **RAG provenance** — claude-mem/ChromaDB `chroma.sqlite3`서 인덱싱된 청크원문·출처(임베딩 역변환 아님).

---

## 3. 위협 모델·시나리오

전제(논문과 동일): **사후 포렌식**. 네트워크 캡처·메모리 덤프 없음. 로컬 영속 아티팩트만. 공격자 외부 인프라 접근 불가.

### 3.1 Primary 시나리오 — "공급망 무기화" (Nx식)
개발자 PC(Windows + WSL2)에 악성 의존성 설치 → `postinstall`이 설치된 CLI 에이전트를 안전장치 끄고 실행(`--dangerously-skip-permissions` 등) → 에이전트가 파일시스템서 시크릿·키·지갑 스캔 → base64 인코딩 → 피해자 GitHub 공개 레포로 유출.

**남는 아티팩트(재구성 근거):** 에이전트 transcript의 *악성 스캔 프롬프트* · `/tmp/inventory.txt`(스캔결과) · 수정된 `~/.bashrc`/`~/.zshrc` · shell history의 무기화 호출 · exfil 레포 흔적. (WSL2면 전부 ext4.vhdx 내부.)

### 3.2 Variant — "내부자/부주의 유출"
개발자가 기밀을 프롬프트에 붙여넣거나(`pastedContents`/`paste-cache`), 에이전트가 `auto` 모드서 `.env`·결제모듈을 자율로 읽어(`toolUseResult`) 클라우드로 전송. 의도적 변종 = 퇴사자가 붙여넣기 + 세션삭제 은폐.

### 3.3 (확장 후보) 파괴적 행위 / 악성 MCP·skill·hooks
Replit식 `rm -rf`/DB삭제, 악성 MCP·플러그인·Hooks-RCE. 프레임워크가 동일하게 커버. 발표 시간·구현 여력 따라 1~2개 추가.

### 3.4 증거 경계 (정직 — 과장 금지)
- **증명**: 기밀/명령이 *로컬에 캡처·직렬화*됨 (시각·맥락·기제).
- **추론(별도 로그 필요)**: 클라우드 전송 성공 · 제공자 보존 · 경쟁사 도달. "경쟁사가 받았다"는 *조사 계기*지 도구의 결론 아님.

---

## 4. 시스템 범위

- **OS**: Windows 11 + WSL2(주). 네이티브 Windows CLI도 분기 처리.
- **에이전트**: Claude Code, Codex CLI, Gemini CLI (버전핀 — 포맷이 버전마다 바뀜).
- **아티팩트 인벤토리(현 버전 기준, 논문+우리 신규 발견):**

| 클래스 | 경로(WSL `~` 기준) | 증거 |
|---|---|---|
| 세션 transcript | `~/.claude/projects/<enc>/<uuid>.jsonl` | 프롬프트·`toolUseResult`(파일내용)·명령·thinking·`cwd`·`gitBranch` |
| 프롬프트/붙여넣기 | `~/.claude/history.jsonl`(`pastedContents`)·`~/.claude/paste-cache/` | 사람이 입력·붙여넣은 것 |
| 파일 체크포인트 | `~/.claude/file-history/`, `file-history-snapshot` 레코드 | 에이전트 편집 *전* 구버전 → 복구 |
| 서브에이전트 | `~/.claude/agents/`, `~/.claude/teams/`, `agent-name` 레코드 | 멀티에이전트 행위 |
| 셸 스냅샷 | `~/.claude/shell-snapshots/` | 셸 상태/명령 |
| MCP/플러그인/훅 | `~/.claude.json`·`<proj>/.mcp.json`·`~/.claude/plugins/`·`~/.claude/hooks/` | 외부 리소스·공급망 |
| 자격증명 | `~/.claude/.credentials.json`·`settings.json` / `~/.codex/auth.json` / `~/.gemini/oauth_creds.json` | 평문 토큰 |
| Codex 세션 | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | (구버전 Fernet → 신버전 확인 필요) |
| Gemini 세션 | `~/.gemini/tmp/<proj>/chats/` | 평문 전체 |
| RAG(선택) | `~/.../chroma/chroma.sqlite3`(+`-wal`) | `embedding_fulltext_search`(청크 원문)·`embedding_metadata`(출처)·`embeddings_queue`(이력) |
| 호스트층 | 네이티브: EVTX 4688(프로세스) · WSL2: ext4.vhdx·`/tmp`·shell history·(있으면)auditd | 실행/파일시스템 효과 |

---

## 5. 아키텍처 — 2 파트

### Part 1. 분석 엔진 (핵심·차별점) — 7단계 파이프라인
1. **수집(Acquisition)** — 증거 디렉토리/ext4.vhdx 식별 + 파일별 MD5/SHA256(custody, 분석 전).
2. **파싱(Parse)** — 에이전트별·버전핀 파서(JSONL/TOML/JSON/Fernet). 필드 의미는 공식 repo로 검증.
3. **정규화(Normalize)** — 이종 레코드 → 단일 이벤트 스키마(시각·행위자·기제·리소스·출처).
4. **강화(Enrich)** — 시크릿/PII 탐지(정규식+엔트로피, 오탐제어) · MITRE ATT&CK 태깅 · 귀속(사람 vs 에이전트).
5. **복구(Recover)** — `file-history` 구버전 · 삭제 transcript(ext4.vhdx 구조기반 카빙, *손실 명시*) · ChromaDB(SQLite WAL/freelist).
6. **교차상관(Correlate)** — 다층(논문 모델) + WSL2/NTFS 경계 + 호스트 흔적(`/tmp/inventory.txt`·bashrc) + EVTX(네이티브 한정).
7. **재구성·리포트(Reconstruct/Report)** — 사건 타임라인 + 재구성등급(완전/부분/불가) + 수사관 친화 뷰 + custody 리포트(분석 후 재해시=무변경).

### Part 2. AI 자연어 질의 (보조)
정규화·분석된 데이터에 자연어 질의("누가 .env 읽었어?", "유출 시크릿 뭐야?", "공격 사슬 설명"). **로컬 LLM(오프라인 — 증거 외부유출 방지).**
**원칙(타협 불가):** AI 답 = *보조 단서*. 모든 응답은 **원본 아티팩트(파일·줄번호)로 추적가능(provenance)**. 결론은 결정론적 파싱이 내고 AI는 해석/요약만. (AI 유출 잡는 도구가 AI 신뢰성으로 깨지지 않게.)

---

## 6. 기능 명세 (구현 단위)

- **F1 수집기** — 경로 자동탐색(WSL distro·네이티브) + ext4.vhdx 마운트/읽기 + 해시.
- **F2 파서** — Claude/Codex/Gemini transcript·config·credential 파서(버전핀, 미지 필드 graceful).
- **F3 정규화 스키마** — `Event{ts, actor(user|agent), mechanism(paste|tool_read|tool_bash|hook|mcp), resource, content_ref, source_artifact, provenance}`.
- **F4 시크릿/PII 탐지기** — 키·토큰·개인키·PII 패턴 + 엔트로피; 라벨 벤치마크로 precision/recall.
- **F5 귀속 분류** — pastedContents=사람 / toolUseResult=에이전트 / hook·mcp=자동. (기제 분류지 의도 아님 — 명시.)
- **F6 복구기** — file-history 구버전 추출 · 삭제 JSONL 카빙(ext4) · ChromaDB SQLite 카빙.
- **F7 상관·재구성** — 다층 상관 + 재구성등급 판정 + MITRE 매핑.
- **F8 뷰어/리포트** — 타임라인 UI + 사건 요약 + custody 리포트(해시 전후).
- **F9 AI 질의(보조)** — 로컬 LLM + provenance 강제.
- **F10 무결성** — 전 단계 해시/custody/재현성.

---

## 7. 포렌식 건전성

- **무결성**: 증거 파일 MD5+SHA256(수집 시) → 읽기전용 분석 → 재해시(분석 후) = 무변경 증명. custody 리포트.
- **재현성**: 동일 입력 → 동일 출력(정규화 결과 해시 대조).
- **오탐 정량화**: 시크릿/PII 탐지 precision/recall (라벨 벤치마크 = 합성 + 실제 샘플).
- **재구성등급**(논문 차용): 완전/부분/불가 — 각 시나리오 평가.
- **증거능력**: 결정론적 파싱이 1차 증거, AI는 보조; 모든 주장 원본 추적가능; 증거 경계(증명 vs 추론) 명시.

---

## 8. 평가 계획 (= 케이스스터디)

1. **통제 스테이징** — Nx식 무기화를 격리 환경서 재현(악성 postinstall이 에이전트 호출 → 합성 시크릿 스캔/유출). Ground-truth(무엇이·언제) 기록.
2. **재구성** — 도구로 사건 재구성 → ground-truth 대비 정확도, 재구성등급.
3. **탐지 메트릭** — 시크릿/PII precision/recall, 삭제복구 recall.
4. **무결성 검증** — 분석 전후 해시 일치(원본 무변경).
5. **무료도구 대비** — OSS 세션검색(열람만) 대비 우리 *분석·복구·무결성* 우위 표.
6. (선택) Variant(내부자 유출)·파괴적 행위 1개 추가 재현.

---

## 9. 한계 (정직 — 비판 에이전트 반영)

- DLP "불가시"가 아니라 *커버리지 갭*(브라우저 DLP·WSL2 한정). 과장 금지.
- AV 무관(멀웨어 탐지지 데이터유출 통제 아님) — 언급 X.
- 피해 = 통제상실·정책/계약·자격증명 노출 (경쟁사 도달은 증명 안 함).
- 삭제 JSONL 카빙은 ext4.vhdx 구조기반 *best-effort·손실*. ChromaDB만 SQLite WAL 적용.
- EVTX 4688 상관은 *네이티브 Windows 한정*. WSL2는 호스트 EVTX 블라인드(→ 도구 존재이유).
- 아티팩트 포맷은 *버전·벤더 의존*(리버스, API 계약 없음) — 버전핀 명시.
- 귀속 = 기제(사람/에이전트)지 *의도* 아님.
- 임베딩 역변환 주장 금지 — RAG 복원은 SQLite 평문 청크서.
- LLM 답 = 단서지 결론 아님(증거능력).

---

## 10. 기술 스택 (제안)

- Python 3 (stdlib 우선; JSONL/TOML/SQLite 파싱). carving·integrity는 기존 windows-timeline 지식 전이.
- ext4.vhdx 읽기: 가능하면 stdlib/경량 라이브러리(또는 `wsl --mount`/이미지 파서) — 조사 필요.
- 로컬 LLM: Ollama + 경량 모델(오프라인). provenance 강제 래퍼.
- UI: HTML 뷰어(경량) + 단일 실행 산출물(추후).
- (주의) **이 도구 자체는 새 repo. wintrace 코드 미사용.**

---

## 11. Non-Goals

- 메모리 포렌식 / 네트워크 캡처 (사후·디스크 전제).
- 실시간 차단/방어(EDR 아님) — 사후 IR 도구.
- 임베딩 역변환으로 원본 복원.
- 클라우드 제공자측 데이터 조사(접근 불가).
- 모든 CLI 에이전트·전 버전 커버(핀된 3종 우선).

---

## 12. 미해결 질문 (개발 전 결정)

1. ext4.vhdx 접근 방법(마운트 vs 이미지 파싱) — PoC 필요.
2. Codex 신버전 세션이 여전히 암호화인가(평문 전환?) — 실측.
3. Primary만 vs Variant·파괴적행위까지 — 발표 시간/여력.
4. 제품명 확정.
5. 2인 역할 분담(아래 별도).

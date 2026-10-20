# AgenTrace (cli-llm-forensic)

AI 코딩 에이전트(**Claude Code · Codex CLI**)가 PC에 남긴 기록으로 **누가 무엇을 했는지** 재구성하는 포렌식 도구. Windows/WSL2.
결과는 로컬 웹 대시보드로 보고, 자연어로 질의한다.

## 무엇을 밝히나
- **행위 주체** — 사람이 직접 한 일인가, 에이전트가 스스로 한 일인가.
- **행위 내역** — 읽은 파일 · 실행한 명령 · MCP 호출 · 노출된 시크릿.
- **지시 경로** — 폰(원격제어)에서 온 지시인가, 로컬에서 타이핑한 지시인가.
- 원본은 읽기만 한다. 모든 결과는 원본 위치(`file:line`)를 가진다.

## 대상 사건
- **공급망 공격의 에이전트 악용** — 예: 2025-08 Nx npm 패키지 사건. 악성 설치 스크립트가 PC에 설치된 AI CLI를 권한 확인 없이 실행해 키·지갑 파일을 찾아 유출했다.
- **내부자 유출** — 사용자가 시크릿을 직접 붙여넣었는가, 에이전트가 자율로 읽었는가.

## 사용
```bash
pip install -e ".[dev]"
clfx parse ~/.claude ~/.codex -o events.jsonl
clfx analyze events.jsonl -o analyzed.jsonl --root ~/.claude
clfx query analyzed.jsonl "누가 .env 읽었어?"
clfx serve analyzed.jsonl          # http://127.0.0.1:8787
```
- 자세히: `docs/사용법.md`
- Windows 단일 실행 파일(`AgenTrace.exe`) 빌드: `packaging/build.md`

## 문서
- **`docs/INDEX.md` 먼저 읽기** — 모든 문서 색인 + 역할별 읽는 순서.
- 설계: `docs/설계.md`
- 아티팩트 분석 종합: `docs/AgenTrace-종합-아티팩트-분석.md`
- 선행논문(토대): Kim & Jeong, "From assistant to accomplice" — [SSRN 6725750](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6725750)

## 규정
- **새 문서를 만들면 `docs/INDEX.md` 색인에 한 줄 추가**(없으면 만든 게 아님).
- **Event 스키마 단일 원천 = `docs/event-schema.md`** — 다른 문서에 복제 금지, 변경은 이 파일 PR로만.

> 개발 하네스 파일(`.claude/` 등 tmux 2-pane 하네스)은 **로컬 전용 — 레포 미포함**. 팀원은 자기 환경에서 작업.

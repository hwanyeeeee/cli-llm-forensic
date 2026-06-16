# cli-llm-forensic

Windows/WSL2 **CLI 코딩 에이전트(Claude Code · Codex CLI · Gemini CLI) 포렌식 도구**.
공급망 무기화(Nx식)·내부자 유출 등 사건을 에이전트 아티팩트로 재구성하고, 로컬 AI로 자연어 질의.

## 시작
- **`docs/INDEX.md` 먼저 읽기** — 모든 문서 색인 + 역할별 읽는 순서.
- 설계 전체: `docs/superpowers/specs/2026-06-16-cli-llm-forensic-design.md`
- 선행논문(토대): `docs/Ref/` (Kim & Jeong, "From assistant to accomplice", SSRN 6725750)

## 규정
- **새 문서를 만들면 `docs/INDEX.md` 색인에 한 줄 추가**(없으면 만든 게 아님).
- **Event 스키마 단일 원천 = `docs/event-schema.md`** — 다른 문서에 복제 금지, 변경은 이 파일 PR로만.

> 개발 하네스 파일(`.claude/` 등 tmux 2-pane 하네스)은 **로컬 전용 — 레포 미포함**. 팀원은 자기 환경에서 작업.

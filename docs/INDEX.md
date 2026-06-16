# 문서 색인 (INDEX) — cli-llm-forensic

> **AI/사람이 처음 오면 이 파일부터.** 어떤 문서를 봐야 하는지 여기서 찾아간다.
> 새 문서가 생기면 **반드시 이 색인에 한 줄 추가**(CLAUDE.md 규정).

프로젝트: Windows/WSL2 CLI 코딩 에이전트(Claude Code·Codex·Gemini) 포렌식 도구.

---

## 📌 역할별 읽는 순서

**둘 다 (먼저):**
1. `superpowers/specs/2026-06-16-cli-llm-forensic-design.md` — **설계 명세**(왜·무엇·시나리오·기능·평가·한계). 전체 그림.
2. `event-schema.md` — **Event 스키마 canonical v1.0** ★단일 진실원천. 둘이 이 enum 그대로 사용. 변경은 이 파일 PR로만.
3. `역할분담.md` — 2인 분담 + 합의점.

**코어 개발자 (도구):**
- 위 1~3 + `논문대비-신규발견.md` (파서가 다뤄야 할 신규 아티팩트).
- `Ref/From assistant to accomplice...pdf` — 토대 논문(다층모델·조사프로세스 차용).

**팀원 (실험·검증·발표):**
- `스테이징-데이터셋-가이드.md` — **데이터셋 구축**(그대로 따라하면 됨. 안전 가드 필수).
- `논문대비-신규발견.md` — **자기 머신서 교차검증**(표 "팀원 결과" 채우기).
- `발표-가이드라인.md` — **슬라이드**(흐름·금지표현·Q&A).
- `event-schema.md` §3 — 채점 하네스 매칭 규칙.

---

## 📂 전체 문서 목록

| 문서 | 한 줄 | 담당 |
|---|---|---|
| `INDEX.md` | 이 색인 | 공통 |
| `superpowers/specs/2026-06-16-cli-llm-forensic-design.md` | 설계 명세(배경·의의·시나리오·기능·평가·한계) | 공통 |
| `event-schema.md` | ★Event 스키마 canonical v1.0 (단일 원천·매칭 계약) | 공통 |
| `역할분담.md` | 2인 분담(코어=1인 / 팀원=실험·검증·발표+F4·채점) | 공통 |
| `스테이징-데이터셋-가이드.md` | 통제 데이터셋(Nx 재현) 구축 — 팀원 핸드오프 | 팀원 |
| `논문대비-신규발견.md` | 논문 대비 신규 발견 + 팀원 머신 교차검증 표 | 공통 |
| `발표-가이드라인.md` | 발표 슬라이드 흐름·금지표현·Q&A | 팀원 |
| `Ref/From assistant to accomplice ....pdf` | 토대 선행논문(Kim & Jeong, SSRN 6725750) | 공통 |
| `plan.md` / `STATE.md` | 하네스 진행판(개발 시작 후 채움) | 공통 |

---

## 🔗 외부
- 선행논문 SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6725750 (PDF는 `Ref/`에 동봉 — 다운 불필요)

---

*문서 추가/이름변경 시 이 표 갱신 필수.*

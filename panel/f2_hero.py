import sys
sys.path.insert(0, "/home/best1pjh/.claude/skills/precision-diagram/scripts")
from flowlib import Diagram

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import panel_font  # 양식 규정 폰트(나눔스퀘어) — 포스터와 같은 글꼴을 쓴다

d = Diagram(figsize=(24, 10.8), xlim=(0, 24), ylim=(0, 10.8), dpi=220, font=panel_font.resolve())

Y = 7.75
BW, BH = 3.35, 2.35
CX = [1.9, 5.9, 9.9, 13.9, 17.9, 21.9]

d.text("title", 0.35, 10.35, "AgenTrace — CLI 에이전트 기록 포렌식 파이프라인",
       fs=23, color="#111", ha="left")
d.text("subtitle", 0.35, 9.78,
       "원본을 열지 않고 수집 → 구조로 스키마를 판별 → 행위 주체를 귀속 → 단일 Event 로 정규화",
       fs=13.5, color="#555", ha="left")

b0 = d.box("src", CX[0], Y, BW, BH,
           "① 원본 증거\n\nClaude  ~/.claude\nCodex   ~/.codex\nrollout JSONL · SQLite", "start", fs=12.5)
b1 = d.box("acq", CX[1], Y, BW, BH,
           "② read-only 취득\n\n쓰기 경로 원천 차단\nraw 바이트 SHA-256\nWAL·SHM 동시 복사", "proc", fs=12.5)
b2 = d.box("parse", CX[2], Y, BW, BH,
           "③ 구조 탐지 파서\n\n버전이 아닌 구조로 판별\nlegacy · item 2계통 병행\n계층별 이름·구조 분리", "proc", fs=12.5)
b3 = d.box("attr", CX[3], Y, BW, BH,
           "④ 행위 주체 귀속\n\n사용자 · 에이전트 · 미상\n파일 작성 확신도 4등급\n서브에이전트 계층 보존", "proc", fs=12.5)
b4 = d.box("event", CX[4], Y, BW, BH,
           "⑤ 단일 Event\n\n9필드 + 선택 meta\n출처 file:line 보존\n에이전트 종류 무관 동형", "ok", fs=12.5)
b5 = d.box("view", CX[5], Y, BW, BH,
           "⑥ 분석 · 대시보드\n\n타임라인 · 접근파일\n키워드 · 자연어 질의\n읽기전용 증명서", "start", fs=12.5)

for a, b in ((b0, b1), (b1, b2), (b2, b3), (b3, b4), (b4, b5)):
    d.arrow([(a.right, Y), (b.left, Y)], name=f"flow-{a.name}")

NY = 5.85
for i, (x, s) in enumerate([
        (CX[0], "실측 rollout 353파일\nSQLite 6종 + WAL·SHM"),
        (CX[1], "원본 무변경\n수집 시각·해시 기록"),
        (CX[2], "CLI 버전 29종 혼재\n이름 규칙 3계층"),
        (CX[3], "미상을 사용자로\n흡수하지 않는다"),
        (CX[4], "실측 37,090건\n미지 구조 0건"),
        (CX[5], "원본 위치까지\n역추적")]):
    d.text(f"note{i}", x, NY, s, fs=11.5, color="#444")

ZY, ZH = 3.55, 2.75
d.box("zoom3", 6.05, ZY, 11.5, ZH,
      "③ 확대 — 같은 행위가 계층마다 다른 이름·구조로 남는다\n\n"
      "raw  response_item     snake_case     function_call · custom_tool_call\n"
      "raw  event_msg.item    PascalCase     CommandExecution · FileChange\n"
      "SQLite  thread_items   camelCase      commandExecution · fileChange\n\n"
      "구조도 다르다 — changes: 맵 ↔ 배열,  command: argv 배열 ↔ 문자열",
      "note", fs=12.0, align="left")
d.box("zoom4", 17.95, ZY, 11.5, ZH,
      "④ 확대 — 무엇을 근거로 주체를 정하는가\n\n"
      "사용자      사용자 발화 기록과 그 안의 첨부 이미지\n"
      "에이전트   모델의 도구 호출과 연결된 실행\n"
      "미상        근거 없음 — 사용자로 흡수하지 않는다\n\n"
      "파일 작성 확신도: 구조화 기록 medium · 명령 추정 low · 디스크만 unknown",
      "note", fs=12.0, align="left")

WY = 1.15
warn = d.box("warn", 11.95, WY, 23.3, 1.35,
             "①~⑤ 전 단계에서 수집한 경고를 화면까지 끌고 간다 — "
             "미지 스키마 · 버전과 구조 불일치 · 취득 실패 · 주체 미상\n"
             "못 읽은 것은 반드시 남긴다: “조용한 0건”을 만들지 않는다",
             "bad", fs=12.5)

d.audit()
d.save("/mnt/c/projects/cli-llm-forensic/panel/f2_hero")

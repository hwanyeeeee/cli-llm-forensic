import sys
sys.path.insert(0, "/home/best1pjh/.claude/skills/precision-diagram/scripts")
from flowlib import Diagram

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import panel_font  # 양식 규정 폰트(나눔스퀘어) — 포스터와 같은 글꼴을 쓴다

d = Diagram(figsize=(24, 7.0), xlim=(0, 24), ylim=(0, 7.0), dpi=220, font=panel_font.resolve())

Y = 3.95
BW, BH = 3.35, 2.35
CX = [1.9, 5.9, 9.9, 13.9, 17.9, 21.9]

d.text("title", 0.35, 6.55, "AgenTrace — CLI 에이전트 기록 포렌식 파이프라인",
       fs=23, color="#111", ha="left")
d.text("subtitle", 0.35, 6.0,
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

NY = 2.05
for i, (x, s) in enumerate([
        (CX[0], "실측 rollout 353파일\nSQLite 6종 + WAL·SHM"),
        (CX[1], "원본 무변경\n수집 시각·해시 기록"),
        (CX[2], "CLI 버전 29종 혼재\n이름 규칙 3계층"),
        (CX[3], "미상을 사용자로\n흡수하지 않는다"),
        (CX[4], "실측 37,090건\n미지 구조 0건"),
        (CX[5], "원본 위치까지\n역추적")]):
    d.text(f"note{i}", x, NY, s, fs=11.5, color="#444")

WY = 0.78
warn = d.box("warn", 11.95, WY, 23.3, 1.35,
             "①~⑤ 전 단계에서 수집한 경고를 화면까지 끌고 간다 — "
             "미지 스키마 · 버전과 구조 불일치 · 취득 실패 · 주체 미상\n"
             "못 읽은 것은 반드시 남긴다: “조용한 0건”을 만들지 않는다",
             "bad", fs=12.5)

d.audit()
d.save("/mnt/c/projects/cli-llm-forensic/panel/f2_hero_compact")

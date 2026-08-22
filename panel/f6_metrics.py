import sys
sys.path.insert(0, "/home/best1pjh/.claude/skills/precision-diagram/scripts")
from flowlib import Diagram

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import panel_font  # 양식 규정 폰트(나눔스퀘어) — 포스터와 같은 글꼴을 쓴다

d = Diagram(figsize=(24, 7.6), xlim=(0, 24), ylim=(0, 7.6), dpi=220, font=panel_font.resolve())

d.text("title", 0.35, 7.15, "실측 결과 — 무엇을 얼마나 복원했는가",
       fs=22, color="#111", ha="left")
d.text("sub", 0.35, 6.55,
       "Codex 원본 rollout 353파일 · CLI 버전 29종이 섞인 실제 기록 · 2026-08-22 17:20 스냅샷",
       fs=13.5, color="#555", ha="left")

CY, CW, CH = 4.7, 4.6, 1.85
X = [3.1, 8.7, 14.3, 19.9]
d.box("m1", X[0], CY, CW, CH, "37,090", "ok", fs=34)
d.box("m2", X[1], CY, CW, CH, "246", "ok", fs=34)
d.box("m3", X[2], CY, CW, CH, "100%", "ok", fs=34)
d.box("m4", X[3], CY, CW, CH, "1.76×", "ok", fs=34)

for i, s in enumerate([
        "복원한 행위 이벤트\n미지 스키마 0건",
        "폰에서 내려온 원격 지시\n로컬 실행과 결속",
        "주체 식별 · 접근파일 · MCP\n각 100건 통제 데이터",
        "이벤트 구축 속도\n위임 경로 대 직접 접근"]):
    d.text(f"lab{i}", X[i], 3.2, s, fs=13, color="#333")

for i, s in enumerate([
        "사용자 2,392 · 에이전트 34,698\n주체 미상 0건",
        "사람이 직접 친 명령 2건까지 분리",
        "오탐 0 · 누락 0\n한계는 별도 명시",
        "18.161s 대 32.033s\n전체 처리 1.35×"]):
    d.text(f"fn{i}", X[i], 2.0, s, fs=10.5, color="#777")

d.box("trap", 11.95, 0.78, 23.3, 1.1,
      "이 결과가 그냥 나오지 않는 이유 — 같은 도구가 버전·실행모드마다 다른 형식으로 기록한다.\n"
      "세션 파일 353개 중 329개(93.2%)에 최신 형식 레코드가 한 건도 없어, 최신 형식만 구현한 파서였다면 그 파일들에서 이벤트가 0건 나온다.",
      "note", fs=12.5)

d.audit()
d.save("/mnt/c/projects/cli-llm-forensic/panel/f6_metrics")

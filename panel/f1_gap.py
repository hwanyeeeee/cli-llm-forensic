import sys
sys.path.insert(0, "/home/best1pjh/.claude/skills/precision-diagram/scripts")
from flowlib import Diagram

d = Diagram(figsize=(24, 5.6), xlim=(0, 24), ylim=(0, 5.6), dpi=220)

d.text("title", 0.35, 5.15, "증거는 한 곳에 모여 있지 않다 — 어디를 보느냐에 따라 사건의 크기가 달라진다",
       fs=21, color="#111", ha="left")

Y, BW, BH = 3.05, 5.0, 1.9
X = [3.1, 9.4, 15.7]
a = d.box("raw", X[0], Y, BW, BH, "원본 rollout 파일\n\n351", "start", fs=15)
b = d.box("cat", X[1], Y, BW, BH, "SQLite 세션 카탈로그\n\n348", "proc", fs=15)
c = d.box("proj", X[2], Y, BW, BH, "SQLite 항목 투영\n\n22", "bad", fs=15)
d.arrow([(a.right, Y), (b.left, Y)], name="f1")
d.arrow([(b.right, Y), (c.left, Y)], name="f2")

d.text("n1", X[0], 1.55, "1차 증거 — 전수 파싱 대상", fs=12, color="#444")
d.text("n2", X[1], 1.55, "세션 목록·경로 대조용", fs=12, color="#444")
d.text("n3", X[2], 1.55, "여기만 보면 세션의 94%가 사라진다", fs=12, color="#c00000")

d.box("ver", 21.0, Y, 5.1, 1.9,
      "같은 도구, 다른 기록 형식\n\nCLI 버전 29종 × 이름 계층 3종", "note", fs=13)
d.text("n4", 21.0, 1.55, "하나의 스키마만 가정하면 나머지는 조용히 0건", fs=12, color="#444")

d.text("bound", 0.35, 0.55,
       "[개념 경계]  파일이 디스크에 존재한다는 사실만으로 누가 만들었는지는 확정되지 않는다 — "
       "기록·시각·해시가 함께 맞아떨어질 때만 주체를 말한다",
       fs=12.5, color="#666", ha="left")

d.audit()
d.save("/mnt/c/projects/cli-llm-forensic/panel/f1_gap")

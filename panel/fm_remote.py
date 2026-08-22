import sys
sys.path.insert(0, "/home/best1pjh/.claude/skills/precision-diagram/scripts")
from flowlib import Diagram

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import panel_font  # 양식 규정 폰트(나눔스퀘어) — 포스터와 같은 글꼴을 쓴다

d = Diagram(figsize=(24, 12.6), xlim=(0, 24), ylim=(0, 12.6), dpi=220, font=panel_font.resolve())

d.text("title", 0.35, 12.15, "모바일 원격제어 — 지시 주체(폰)와 실행 주체(로컬 PC)가 분리된다",
       fs=22, color="#111", ha="left")
d.text("sub", 0.35, 11.6,
       "실측 2026-08-21~22 · Android SM-A235N(루팅) · 관측 63건 — 내용은 로컬에만, 폰에는 누가·언제·어디만 남는다",
       fs=13, color="#555", ha="left")

CXP, CXS, CXL = 4.15, 11.3, 19.2
BWP, BWS, BWL = 6.4, 5.2, 7.6

# ── S3 Claude 레인 ──────────────────────────────────────────
Y3, H3 = 9.3, 2.4
d.text("s3", 0.35, 10.95, "S3  Android × Claude Code", fs=15, color="#2e6fb7", ha="left")
p3 = d.box("p3", CXP, Y3, BWP, H3,
           "폰 · Claude 앱\n\ncode_remote.xml\n  recap_dismissed_at\n  default_session_target", "alt", fs=12, align="left")
s3 = d.box("s3b", CXS, Y3, BWS, H3,
           "서버\n\nclaude.ai/code/\nsession_<ULID>", "proc", fs=12, align="left")
l3 = d.box("l3", CXL, Y3, BWL, H3,
           "로컬 PC · ~/.claude\n\nsessions/<pid>.json  bridgeSessionId\nprojects/**/<uuid>.jsonl\n  promptSource=\"queued\"  ← 원격\n  tool_use.input (실행된 명령)", "ok", fs=12, align="left")
d.arrow([(p3.right, Y3), (s3.left, Y3)], name="a31")
d.arrow([(s3.right, Y3), (l3.left, Y3)], name="a32")
d.text("n3", 0.35, 7.42,
       "판별자  promptSource=\"queued\" ∧ origin.kind=\"human\"  (위양성 검증 완료)      "
       "폰↔로컬 시각차  +0.973s · +2.275s (2회 재현, 부호 일관)\n"
       "같은 세션인데 접두사가 다르다  session_… (로컬 상태·URL) vs cse_… (세션 JSONL)  → 문자열 검색으로는 못 잇는다      "
       "폰에 지시 내용  없음",
       fs=11.5, color="#333", ha="left")

# ── S4 Codex 레인 ───────────────────────────────────────────
Y4, H4 = 5.1, 2.35
d.text("s4", 0.35, 6.62, "S4  Android × Codex", fs=15, color="#6a3fb5", ha="left")
p4 = d.box("p4", CXP, Y4, BWP, H4,
           "폰 · ChatGPT 앱\n\ncodex_remote_hosts.json\n  saved_hosts[] — 작업 디렉터리 26건\ncodex_remote_control_enrollments.json\n  ECDSA P-256 공개키만", "alt", fs=12, align="left")
s4 = d.box("s4b", CXS, Y4, BWS, H4,
           "서버\n\nwss://chatgpt.com\n /backend-api/wham\n /remote/control/server", "proc", fs=12, align="left")
l4 = d.box("l4", CXL, Y4, BWL, H4,
           "로컬 PC · ~/.codex\n\nstate_5.sqlite  remote_control_enrollments\nlogs_2.sqlite   client_name  ← 원격 판별\nsessions/**/rollout-*.jsonl  (내용)", "ok", fs=12, align="left")
d.arrow([(p4.right, Y4), (s4.left, Y4)], name="a41")
d.arrow([(s4.right, Y4), (l4.left, Y4)], name="a42")
d.text("n4", 0.35, 3.5,
       "판별자  client_name=\"codex_chatgpt_android_remote\" — rollout 이 아니라 logs_2.sqlite 에 있다      "
       "내용과 출처가 분리돼 파일 2개가 필요하다 (Claude 는 1개)\n"
       "장치 개인키만 비추출  os_protected_nonextractable — “루팅=전량 취득”은 과장이다      "
       "전제  standalone 설치 + 계정 MFA + 페어링 코드 9자(10분)",
       fs=11.5, color="#333", ha="left")


# ── S1·S2 iOS — 한 줄 예고 (박스 없이 세로 절약) ──────────
d.text("ios", 0.35, 2.86, "S1 · S2   iOS × Claude Code / Codex   —   분석 예정",
       fs=14, color="#8a8a8a", ha="left")
d.text("iosn", 0.35, 2.34,
       "취득 경로  암호화 백업(Finder / idevicebackup2) → Manifest.db 앱 도메인 — 탈옥 없이 진행.   "
       "Android 결과가 iOS 에 그대로 적용된다고 가정하지 않는다",
       fs=11, color="#888", ha="left")

# ── 오판 함정 ───────────────────────────────────────────────
d.box("warn", 11.95, 1.28, 23.3, 1.5,
      "오판 함정 — 설정 파일·DB 행은 “설정된 적 있음”까지만 말한다. 실제 가용 구간과 실행 주체는 로그로만 확정된다\n\n"
      "위음성  remote_control_enrollments 0행 ≠ 미사용 (enroll 실패도 0행)      ~/.claude/sessions/ 는 정상 종료 시 삭제 — 비었다고 미사용 아님\n"
      "위양성  settings.json true + enrollment 행이 있어도 채널은 죽어 있을 수 있다      폰의 last_connection_used_at 이 실행 호스트를 오지시한다",
      "bad", fs=12)

d.text("foot", 0.35, 0.18,
       "각주  Claude Code 2.1.238 · Codex 0.149.0 기준. 브리지 세션 ID·enrollment 는 버전 의존이 낮아 1차 근거, 메시지 단위 판정은 보강 근거.",
       fs=10.5, color="#777", ha="left")

d.audit()
d.save("/mnt/c/projects/cli-llm-forensic/panel/fm_remote")

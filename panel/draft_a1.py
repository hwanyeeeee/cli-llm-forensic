"""A1 패널 최종 조판 — 확정 본문(panel-text.md) + 그림 4개를 A1 세로 1장으로 합성한다.

    python3 panel/draft_a1.py

산출:
  draft-a1.jpg   미리보기 (dpi 150)
  draft-a1.png   인쇄용   (dpi 300 · 7016×9933px · 양식 요건 원본 1MB↑)
  draft-a1.svg   벡터본   (텍스트는 path 변환, 그림은 원본 해상도 래스터)

본문은 **하드코딩하지 않고 `panel/panel-text.md`에서 파싱**한다.
수치 동결에서 배운 것과 같은 이유다 — 같은 문장을 두 곳에 두면 한쪽만 고쳐진다.
파싱에 실패하면 조용히 빈칸을 내지 않고 **즉시 죽는다**.

레이아웃 제약은 `docs/패널-구성안.md` §1·§4. 폰트는 그림 4개와 같은 것을 쓴다(§주의 참조).
"""
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch
import matplotlib.image as mpimg
from PIL import Image

PANEL = Path(__file__).resolve().parent
REPO = PANEL.parent
TEXT_SOURCE = PANEL / "panel-text.md"

# A1 세로. figsize를 실제 inch로 두면 matplotlib fontsize(pt)가 인쇄 pt와 1:1이 된다.
A1_W_IN, A1_H_IN = 59.4 / 2.54, 84.1 / 2.54          # 23.386 × 33.110

# `docs/패널-구성안.md` §1: 본문 나눔스퀘어 36pt 이하. 이 머신에 나눔스퀘어·KoPubWorld가
# 없어서 그림 4개와 동일한 맑은고딕으로 조판한다. 제출 전 폰트 정합은 §주의 참고.
FONT_CANDIDATES = [
    "/mnt/c/Windows/Fonts/malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]

INK = "#111111"
MUTED = "#555555"
FAINT = "#7a7a7a"
ACCENT = "#1f5fa8"
RULE = "#c7d2de"
HEADER_BG = "#eaf1f9"
BOX_BG = "#fbfcfe"

# 세로 배분(figure fraction, 위에서부터). 합 = 1.0
BANDS = [
    ("margin_top", 0.002),
    ("header", 0.076),
    ("s1_background", 0.142),
    ("f2_hero", 0.135),
    ("fm_remote", 0.228),
    ("s3_results", 0.271),
    ("s4_impact", 0.124),
    ("footnote", 0.020),
    ("margin_bottom", 0.002),
]

# F5 대시보드 캡처에서 잘라 쓸 두 줄 — 같은 명령인데 주체가 갈리는 그 지점.
# 전체 캡처를 작게 넣으면 UI 글씨가 안 읽힌다. 이 두 줄만 크게 쓰는 편이 낫다.
# 좌표는 panel-f5-leak-scenario.png(2560×1600) 픽셀 기준.
F5_CONTRAST = [
    ("A 사용자가 직접 실행", (512, 332, 1510, 432)),
    ("B 에이전트가 자율 실행", (512, 1202, 1510, 1302)),
]

# `docs/패널-구성안.md` §1 면적 배분. 밴드를 단락으로 묶어 실제 배분과 대조한다.
SECTION_OF = {
    "header": "헤더·여백", "margin_top": "헤더·여백", "margin_bottom": "헤더·여백",
    "footnote": "헤더·여백",
    "s1_background": "① 배경", "f2_hero": "② 방법", "fm_remote": "② 방법",
    "s3_results": "③ 결과", "s4_impact": "④ 효과",
}
BUDGET = {"① 배경": 0.15, "② 방법": 0.35, "③ 결과": 0.30, "④ 효과": 0.12, "헤더·여백": 0.08}
LEFT, RIGHT = 0.030, 0.970
CONTENT_W = RIGHT - LEFT

# 인쇄물 실무 하한. 이보다 작으면 A1 실물에서 사실상 안 읽힌다.
MIN_READABLE_PT = 8.0
_PLACED = []          # (라벨, 원본 최소 fs, 원본 물리폭 in, 배치 폭 in)


def _font(size):
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return FontProperties(fname=candidate, size=size)
    raise SystemExit("한글 폰트를 찾지 못했다. FONT_CANDIDATES에 경로를 추가해라.")


def _bands():
    """밴드 이름 → (top, bottom) figure-fraction. matplotlib y축(아래가 0)으로 변환해 둔다."""
    out, cursor = {}, 1.0
    for name, height in BANDS:
        out[name] = (cursor, cursor - height)
        cursor -= height
    if abs(cursor) > 1e-9:
        raise SystemExit(f"BANDS 합이 1.0이 아니다: 잔여 {cursor:.4f}")
    return out


# ---------------------------------------------------------------- 본문 파싱
def _fenced_block(text, heading):
    match = re.search(rf"^##\s*{re.escape(heading)}.*?\n+```\n(.*?)```", text,
                      re.S | re.M)
    if not match:
        raise SystemExit(f"panel-text.md에서 '{heading}' 코드블록을 못 찾았다.")
    return match.group(1).rstrip("\n")


def _plain(text):
    """마크다운 강조 표기를 벗긴다 — 포스터에 `**`가 그대로 찍히면 안 된다."""
    return re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text).replace("`", "")


def _section_body(text, marker):
    """`## ① …` 다음 문단(인용문·다음 heading 전까지)."""
    match = re.search(rf"^##\s*{marker}[^\n]*\n+(.*?)(?=\n>|\n##\s)", text, re.S | re.M)
    if not match:
        raise SystemExit(f"panel-text.md에서 '{marker}' 본문을 못 찾았다.")
    return _plain(re.sub(r"\s*\n\s*", " ", match.group(1).strip()))


def _blockquote(text, marker):
    """`## ① …` 뒤 인용문(여백 남으면 붙일 근거 한 줄). 없으면 None."""
    match = re.search(rf"^##\s*{marker}[^\n]*\n+.*?\n((?:>[^\n]*\n)+)", text, re.S | re.M)
    if not match:
        return None
    lines = [re.sub(r"^>\s?", "", line) for line in match.group(1).splitlines()]
    body = " ".join(line for line in lines[1:] if line.strip())
    return _plain(body).strip() or None


def load_text():
    """헤더 블록은 `키  값` 2칸 구분. 값이 여러 줄이면 들여쓴 연속행으로 이어진다."""
    raw = TEXT_SOURCE.read_text(encoding="utf-8")
    header, key = {}, None
    for line in _fenced_block(raw, "헤더").splitlines():
        if not line.strip():
            continue
        if line.startswith((" ", "\t")) and key and "  " not in line.strip():
            header[key].append(line.strip())            # 연속행(과제명 2줄째)
            continue
        name, _, value = line.strip().partition("  ")
        key = name.strip()
        header.setdefault(key, [])
        if value.strip():
            header[key].append(value.strip())
    title = header.get("과제명(2줄)") or []
    if len(title) < 2:
        raise SystemExit(f"과제명 2줄을 못 찾았다: {title}")
    bullets = re.findall(r"^-\s+\*\*(.+?)\*\*\s*—\s*(.+?)(?=\n-\s|\n##|\Z)", raw, re.S | re.M)
    if len(bullets) < 3:
        raise SystemExit(f"④ 기대·파급 불릿을 3개 이상 못 찾았다(찾은 수 {len(bullets)}).")
    return {
        "title": title,
        "meta": [(k, " ".join(v)) for k, v in header.items()
                 if k != "과제명(2줄)" and v],
        "background": _section_body(raw, "①"),
        "evidence": _blockquote(raw, "①"),
        "impact": [(_plain(head).strip(),
                    _plain(re.sub(r"\s*\n\s*", " ", body)).strip())
                   for head, body in bullets],
        "footnote": _fenced_block(raw, "각주").strip(),
    }


def _wrap(text, width):
    """한글은 어절 단위로만 끊는다(음절 중간 절단 방지)."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if len(trial) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------- 그리기
def _rule(fig, y, x0=LEFT, x1=RIGHT, color=RULE, lw=1.2):
    fig.add_artist(plt.Line2D([x0, x1], [y, y], color=color, lw=lw,
                              transform=fig.transFigure))


def _panel_box(fig, top, bottom, pad=0.004):
    fig.add_artist(FancyBboxPatch(
        (LEFT, bottom + pad), CONTENT_W, (top - bottom) - 2 * pad,
        boxstyle="round,pad=0.004,rounding_size=0.006",
        transform=fig.transFigure, facecolor=BOX_BG, edgecolor=RULE, lw=1.4, zorder=0))


def _source_metrics(path):
    """그림의 물리 크기와 그 안에서 쓴 최소 글자 크기.

    flowlib는 `bbox_inches="tight"`로 저장해서 선언한 figsize보다 작게 잘린다.
    그래서 선언값이 아니라 **저장된 픽셀 ÷ 저장 dpi**가 실제 물리 폭이다."""
    with Image.open(path) as image:
        px_w = image.size[0]
        dpi = (image.info.get("dpi") or (220, 220))[0] or 220
    script = Path(path).with_suffix(".py")
    if not script.is_file():
        return px_w / dpi, None                    # 스크린샷 등 — 라벨 크기 판정 대상 아님
    sizes = [float(v) for v in re.findall(r"fs\s*=\s*([\d.]+)", script.read_text(encoding="utf-8"))]
    return px_w / dpi, (min(sizes) if sizes else None)


def _place_image(fig, path, top, bottom, x0=LEFT, x1=RIGHT, align="center"):
    """슬롯 안에 원본 비율을 지키며 최대 크기로 앉힌다. 원본 픽셀은 손대지 않는다."""
    if not Path(path).is_file():
        raise SystemExit(f"그림이 없다: {path}")
    image = mpimg.imread(str(path))
    ratio = image.shape[1] / image.shape[0]                  # w/h (px)
    slot_w_in, slot_h_in = (x1 - x0) * A1_W_IN, (top - bottom) * A1_H_IN
    draw_w_in = min(slot_w_in, slot_h_in * ratio)
    draw_h_in = draw_w_in / ratio
    w, h = draw_w_in / A1_W_IN, draw_h_in / A1_H_IN
    left = x0 if align == "left" else (x1 - w if align == "right"
                                       else x0 + ((x1 - x0) - w) / 2)
    axes = fig.add_axes([left, top - h, w, h])
    axes.imshow(image, interpolation="antialiased")
    axes.axis("off")
    source_w_in, min_fs = _source_metrics(path)
    _PLACED.append((Path(path).stem, min_fs, source_w_in, draw_w_in, ratio,
                    (x1 - x0) * A1_W_IN))
    return top - h


def _place_crop(fig, path, box, top, x0, x1):
    """캡처의 한 구간만 잘라 폭에 맞춰 크게 앉힌다.

    전체 캡처를 축소해 넣으면 UI 글씨(13 CSS px)가 인쇄에서 사라진다.
    잘라내면 같은 폭에 더 적은 픽셀이 들어가므로 글자가 그만큼 커진다."""
    with Image.open(path) as source:
        crop = source.convert("RGB").crop(box)
    ratio = crop.size[0] / crop.size[1]
    draw_w_in = (x1 - x0) * A1_W_IN
    draw_h_in = draw_w_in / ratio
    axes = fig.add_axes([x0, top - draw_h_in / A1_H_IN, x1 - x0, draw_h_in / A1_H_IN])
    axes.imshow(crop, interpolation="antialiased")
    axes.axis("off")
    for spine in axes.spines.values():
        spine.set_visible(True)
        spine.set_color(RULE)
    axes.set_frame_on(True)
    # 캡처는 CSS 1600px 뷰포트를 1.6배 배율로 찍은 것이고 UI 본문은 13 CSS px.
    # CSS px를 96dpi 기준 pt로 환산하면 다른 그림과 같은 식으로 인쇄 크기를 잴 수 있다.
    css_w_in = crop.size[0] / 1.6 / 96
    _PLACED.append((f"{Path(path).stem}[crop]", 13.0 * 72 / 96, css_w_in, draw_w_in,
                    ratio, (x1 - x0) * A1_W_IN))
    return top - draw_h_in / A1_H_IN


def readability_report(body_pt):
    """A1 실물에서 각 글자가 몇 pt로 찍히는지 계산한다.

    그림은 원본을 축소·확대해 앉히므로, 원본에서 쓴 pt가 그대로 인쇄되지 않는다.
    인쇄 크기 = 원본 fs × (배치 폭 / 원본 물리 폭)."""
    print(f"\n── 실물 크기 검산 (A1 {A1_W_IN * 2.54:.1f}cm 폭 · 하한 {MIN_READABLE_PT:.0f}pt) ──")
    worst, narrow = [], []
    for label, min_fs, source_w, draw_w, ratio, slot_w in _PLACED:
        scale = draw_w / source_w
        fill = draw_w / slot_w
        if min_fs is None:
            print(f"{label:<20} 폭 {draw_w:5.1f}in(단 폭의 {fill:3.0%}) · 배율 {scale:4.2f}×"
                  f"   최소 글자 —      (스크린샷 · 판정 제외)")
            continue
        printed = min_fs * scale
        flag = "  ⚠ 하한 미만" if printed < MIN_READABLE_PT else ""
        print(f"{label:<20} 폭 {draw_w:5.1f}in(단 폭의 {fill:3.0%}) · 배율 {scale:4.2f}×"
              f"   최소 글자 {min_fs:4.1f}pt → {printed:4.1f}pt{flag}")
        if printed < MIN_READABLE_PT:
            worst.append((label, printed, min_fs, source_w))
        if fill < 0.95:
            narrow.append((label, fill, slot_w, ratio, min_fs, source_w))
    print(f"{'포스터 본문':<20} {'':>29}   최소 글자 {body_pt:4.1f}pt → {body_pt:4.1f}pt")

    if narrow:
        print("\n폭을 다 못 쓰는 그림 — 세로가 먼저 걸린다(비율 고정). 꽉 채우려면:")
        for label, fill, slot_w, ratio, min_fs, source_w in narrow:
            need_h = slot_w / ratio / A1_H_IN
            print(f"   {label}: 현재 단 폭의 {fill:.0%} · 꽉 채우면 세로 {need_h:.1%}가 필요하고"
                  f" 글자는 {min_fs * slot_w / source_w:.1f}pt가 된다")
        print("   → 세로 예산이 없으면 원본을 더 납작한 비율로 다시 그리는 쪽이 답이다"
              "(같은 내용, 가로로 넓게).")

    if not worst:
        print(f"→ 모든 글자가 {MIN_READABLE_PT:.0f}pt 이상이다.")
        return True
    print(f"\n⚠ {MIN_READABLE_PT:.0f}pt 미만 {len(worst)}건 — A1 실물에서 안 읽힌다.")
    for label, printed, min_fs, source_w in worst:
        need_in = MIN_READABLE_PT / min_fs * source_w
        print(f"   {label}: {printed:.1f}pt · {MIN_READABLE_PT:.0f}pt 되려면 폭 "
              f"{need_in:.1f}in({need_in / A1_W_IN:.0%} of A1)이 필요하다")
    return False


def budget_report():
    """구성안 §1 면적 배분과 실제 밴드 합을 대조한다."""
    actual = {}
    for name, height in BANDS:
        actual[SECTION_OF[name]] = actual.get(SECTION_OF[name], 0.0) + height
    print("\n── 면적 배분 (구성안 대비) ──")
    for section, target in BUDGET.items():
        got = actual.get(section, 0.0)
        delta = got - target
        mark = "" if abs(delta) <= 0.03 else ("  초과" if delta > 0 else "  부족")
        print(f"{section:<10} 목표 {target:>5.0%} · 실제 {got:>5.0%} · 차이 {delta:+.0%}{mark}")


def build():
    content = load_text()
    band = _bands()
    fig = plt.figure(figsize=(A1_W_IN, A1_H_IN))
    fig.patch.set_facecolor("white")

    # ---- 헤더
    top, bottom = band["header"]
    fig.add_artist(FancyBboxPatch(
        (LEFT, bottom), CONTENT_W, top - bottom,
        boxstyle="round,pad=0.003,rounding_size=0.005",
        transform=fig.transFigure, facecolor=HEADER_BG, edgecolor="#c3d6ea", lw=1.6, zorder=0))
    y = top - 0.014
    for line in content["title"]:
        fig.text(LEFT + 0.018, y, line, fontproperties=_font(36), color=INK, va="top")
        y -= 0.0175
    meta = "  ·  ".join(f"{key} {value}" for key, value in content["meta"])
    meta_lines = _wrap(meta, 100)
    y = bottom + 0.011 + 0.0110 * (len(meta_lines) - 1)
    for line in meta_lines:
        fig.text(LEFT + 0.018, y, line, fontproperties=_font(17), color=MUTED, va="bottom")
        y -= 0.0110
    if y + 0.0110 > top - 0.014 - 0.0175 * len(content["title"]) - 0.004:
        raise SystemExit("헤더에서 과제명과 인적사항이 겹친다 — header 밴드를 늘려라.")

    # ---- ① 배경·목적 (위치 고정)
    top, bottom = band["s1_background"]
    _panel_box(fig, top, bottom)
    fig.text(LEFT + 0.016, top - 0.017, "① 과제 배경 및 목적",
             fontproperties=_font(30), color=ACCENT, va="top")
    y = top - 0.042
    for line in _wrap(content["background"], 60):
        fig.text(LEFT + 0.016, y, line, fontproperties=_font(27), color=INK, va="top")
        y -= 0.0158
    if content.get("evidence"):
        y -= 0.006
        for line in _wrap(content["evidence"], 74):
            fig.text(LEFT + 0.016, y, line, fontproperties=_font(21), color=MUTED, va="top")
            y -= 0.0136
    if y < bottom:
        raise SystemExit(f"① 본문이 밴드를 넘쳤다(y={y:.4f} < {bottom:.4f}).")

    # ---- ② 방법·내용 : F2 hero + fm_remote
    top, bottom = band["f2_hero"]
    fig.text(LEFT, top - 0.008, "② 수행 방법 및 내용",
             fontproperties=_font(30), color=ACCENT, va="top")
    _place_image(fig, PANEL / "f2_hero_compact.jpg", top - 0.016, bottom)

    top, bottom = band["fm_remote"]
    _place_image(fig, PANEL / "fm_remote.jpg", top, bottom)

    # ---- ③ 결과 : F5 실캡처 + F6 정량 카드
    top, bottom = band["s3_results"]
    fig.text(LEFT, top - 0.008, "③ 수행 결과",
             fontproperties=_font(30), color=ACCENT, va="top")
    # F6(정량 카드)을 위에 넓게, 그 아래 대시보드 실캡처에서 잘라낸 **대비 두 줄**.
    # 전체 캡처를 작게 넣는 것보다 이 두 줄을 크게 쓰는 편이 인쇄에서 훨씬 잘 읽힌다.
    # 요소가 다섯 겹이라 고정 offset으로 쌓으면 반드시 겹친다 — 커서로 내려간다.
    cursor = top - 0.030
    cursor = _place_image(fig, PANEL / "f6_metrics.jpg", cursor, cursor - 0.155,
                          x0=LEFT, x1=RIGHT)
    cursor -= 0.009
    fig.text(LEFT, cursor, "합성 통제 데이터 기준 정확도. 회수율·한계는 종합문서에 분리 기재.",
             fontproperties=_font(17), color=MUTED, va="top")

    cursor -= 0.015
    half = (CONTENT_W - 0.014) / 2
    for index, (label, box) in enumerate(F5_CONTRAST):
        x0 = LEFT + index * (half + 0.014)
        fig.text(x0, cursor, label, fontproperties=_font(18),
                 color="#c02020" if index else "#1a5fb4", va="top")
    cursor -= 0.011
    crop_bottom = cursor
    for index, (_, box) in enumerate(F5_CONTRAST):
        x0 = LEFT + index * (half + 0.014)
        crop_bottom = _place_crop(fig, REPO / "panel-f5-leak-scenario.png", box,
                                  cursor, x0, x0 + half)
    cursor = crop_bottom - 0.008
    for line in _wrap("실제 대시보드에서 잘라낸 두 줄 — 명령 문자열이 한 글자도 다르지 않은데 "
                      "주체만 갈린다. 클릭하면 원본 위치(file:line)까지 역추적된다.", 92):
        fig.text(LEFT, cursor, line, fontproperties=_font(17), color=MUTED, va="top")
        cursor -= 0.0104
    if cursor < bottom - 0.004:
        raise SystemExit(f"③ 내용이 밴드를 넘쳤다(cursor={cursor:.4f} < {bottom:.4f}). "
                         f"F6 높이(0.155)를 줄이거나 s3_results를 늘려라.")

    # ---- ④ 기대·파급
    top, bottom = band["s4_impact"]
    _panel_box(fig, top, bottom)
    fig.text(LEFT + 0.016, top - 0.015, "④ 기대 효과 및 파급 효과",
             fontproperties=_font(30), color=ACCENT, va="top")
    # 표제와 본문을 같은 y에 놓으면 겹친다 — 표제 한 줄, 본문은 들여쓴 다음 줄부터.
    y = top - 0.034
    for head, body in content["impact"]:
        fig.text(LEFT + 0.018, y, f"■ {head}", fontproperties=_font(21),
                 color=ACCENT, va="top")
        y -= 0.0102
        for line in _wrap(body, 86):
            fig.text(LEFT + 0.034, y, line, fontproperties=_font(19), color=INK, va="top")
            y -= 0.0094
        y -= 0.0020
    if y < bottom:
        raise SystemExit(f"④ 본문이 밴드를 넘쳤다(y={y:.4f} < {bottom:.4f}). "
                         f"BANDS의 s4_impact를 늘리거나 글자를 줄여라.")

    # ---- 각주
    top, bottom = band["footnote"]
    _rule(fig, top)
    y = top - 0.005
    for line in content["footnote"].splitlines():
        fig.text(LEFT, y, line, fontproperties=_font(15), color=FAINT, va="top")
        y -= 0.0092
    if y < bottom - 0.004:
        raise SystemExit(f"각주가 밴드 밖으로 나갔다(y={y:.4f}) — footnote 밴드를 늘려라.")

    return fig


def check_figure_consistency():
    """한 포스터 안의 그림들이 서로 다른 수치를 말하는지 본다.

    F6이 동결 기준이다(`docs/패널-구성안.md` §3). 다른 그림이 다른 값을 말하면
    같은 A1 위에 두 숫자가 동시에 인쇄된다 — 인쇄 후에는 못 고친다."""
    # `\b`는 한글 앞에서 안 끊긴다("37,081건") — 숫자·쉼표만 배제하는 look-around을 쓴다.
    claims = {
        "복원 이벤트": r"(?<![\d,])(3\d,\d{3})(?![\d,])",
        "rollout 파일": r"rollout\s*(\d+)\s*파일",
        "CLI 버전 종수": r"CLI 버전\s*(\d+)\s*종",
    }
    per_script = {}
    for script in sorted(PANEL.glob("*.py")):
        if script.name == Path(__file__).name:
            continue
        source = script.read_text(encoding="utf-8")
        for label, pattern in claims.items():
            values = set(re.findall(pattern, source))
            if values:
                per_script.setdefault(label, {})[script.name] = values

    # 한 파일 안에 여러 수치가 있는 건 정상이다(F6은 이벤트와 actor를 같이 싣는다).
    # 문제는 **파일끼리 겹치는 값이 하나도 없을 때** — 서로 다른 사실을 주장하는 것이다.
    conflicts = {}
    for label, by_script in per_script.items():
        names = sorted(by_script)
        if any(not (by_script[a] & by_script[b])
               for i, a in enumerate(names) for b in names[i + 1:]):
            conflicts[label] = {}
            for name in names:
                for value in sorted(by_script[name]):
                    conflicts[label].setdefault(value, []).append(name)
    if not conflicts:
        return True
    print("\n" + "!" * 78)
    print("경고 — 같은 포스터의 그림들이 서로 다른 수치를 말한다. 인쇄 전에 맞춰야 한다.")
    for label, values in conflicts.items():
        print(f"  [{label}]")
        for value, scripts in sorted(values.items()):
            print(f"     {value:<10} ← {', '.join(sorted(set(scripts)))}")
    print("  기준은 f6_metrics.py(동결본). 나머지 그림 스크립트를 그 값으로 맞추고 다시 구워라.")
    print("!" * 78)
    return False


def main():
    fig = build()
    outputs = []
    for name, dpi, kwargs in (("draft-a1.jpg", 150, {"pil_kwargs": {"quality": 92}}),
                              ("draft-a1.png", 300, {}),
                              ("draft-a1.svg", 300, {})):
        path = PANEL / name
        fig.savefig(path, dpi=dpi, facecolor="white", **kwargs)
        size = path.stat().st_size
        outputs.append((name, dpi, size))
        print(f"  {name:<14} dpi {dpi:>3}  {size / 1024 / 1024:.2f} MB")
    plt.close(fig)

    print(f"\nA1 {A1_W_IN * 2.54:.1f} × {A1_H_IN * 2.54:.1f} cm "
          f"· 인쇄본 {int(A1_W_IN * 300)}×{int(A1_H_IN * 300)} px")
    budget_report()
    for name, _, size in outputs:
        if name.endswith(".png") and size < 1024 * 1024:
            sys.exit(f"양식 요건 위반: {name}이 1MB 미만({size} B)")
    readability_report(body_pt=17.0)
    check_figure_consistency()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

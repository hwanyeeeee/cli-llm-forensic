"""OPT-7 / OPT-8 acceptance for clfx/web/static/app.js (frontend, display-only).

The dashboard JS is a classic browser script; we exercise its *pure* logic with
node (no jsdom): a small harness stubs an inert DOM, requires app.js, and asserts
on the exported pure functions. This proves:
  - OPT-7 staged progress label (stage map -> Korean, overall_percent bar width,
    legacy done/total fallback when the new fields are absent),
  - the file stays syntactically valid (node --check),
  - OPT-8 loadAggregates uses Promise.all over individually-caught promises.
node absent -> skip (deterministic; no false failure), present -> hard assert.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
APP_JS = REPO / "clfx" / "web" / "static" / "app.js"
INDEX_HTML = REPO / "clfx" / "web" / "static" / "index.html"
APP_CSS = REPO / "clfx" / "web" / "static" / "app.css"
HARNESS = Path(__file__).parent / "js" / "app_progress_harness.js"
SRC_HARNESS = Path(__file__).parent / "js" / "app_srcscope_harness.js"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="node not installed")


def test_app_js_node_check():
    """node --check must pass (no syntax regressions)."""
    r = subprocess.run([node, "--check", str(APP_JS)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_progress_label_and_equivalence():
    """OPT-7: stage-aware label + byte-identical legacy fallback (equivalence)."""
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout + r.stderr)
    assert "HARNESS OK" in r.stdout, (r.stdout + r.stderr)


def test_load_aggregates_is_concurrent_promise_all():
    """OPT-8 + source scoping: loadAggregates fetches the FOUR aggregates
    (stats + activity + files + keywords) concurrently via Promise.all, each
    individually caught (-> null) so one failure does not blank the others, and
    each scoped by srcParam with the correct separator.
    Static check on source: a single Promise.all containing four .catch(()=>null)
    guarded jget calls; stats is now fetched here too (server single source)."""
    src = APP_JS.read_text(encoding="utf-8")
    # locate the function body
    start = src.index("async function loadAggregates(")
    end = src.index("\n}", start)
    body = src[start:end]
    assert "Promise.all" in body, "loadAggregates must use Promise.all"
    # all four endpoints present, each scoped by srcParam with the right separator,
    # so a source toggle re-fetches the BACKEND aggregates (no JS re-aggregation).
    for frag in ('/api/stats"+srcParam("?")',
                 '/api/activity?by=day"+srcParam("&")',
                 '/api/files"+srcParam("?")',
                 '/api/keywords"+srcParam("?")'):
        assert frag in body, f"missing scoped fetch {frag}"
    assert body.count(".catch(()=>null)") == 4, \
        "each of the 4 aggregate fetches must be individually caught to null"
    # no serial `await jget(` calls left in the function (that was the slow path)
    assert "await jget(" not in body, "no per-call await; must be concurrent"


def test_srcparam_omits_sources_when_full_or_empty_for_lossless_regression():
    """LOSSLESS REGRESSION + scoping: srcParam returns '' for null/empty/full-set
    so the request surface is byte-identical to current behavior (backend takes
    the unchanged origins=None path), and appends sources=<joined> for a proper
    subset. Exercised behaviorally via the node harness with a fetch spy that
    captures the exact URLs loadAggregates requests."""
    r = subprocess.run([node, str(SRC_HARNESS)], capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout + r.stderr)
    assert "HARNESS OK" in r.stdout, (r.stdout + r.stderr)


def test_agent_and_origin_filter_contract_and_neutral_target_copy():
    src = APP_JS.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")
    for fragment in ("let agentActive=null", "function agentLabels()", 'data-axis="agent"',
                     'data-axis="origin"', 'agents="+encodeURIComponent',
                     "agentActive=new Set(agentLabels())"):
        assert fragment in src
    assert "~/.claude · ~/.codex" in html
    assert "Claude Code·Codex CLI 기록" in html


def test_source_toggle_refetches_then_renders():
    """The bug fix: the source-chip toggle re-fetches the BACKEND aggregates
    (await loadAggregates) before re-rendering, instead of only renderAll(). Guard
    the handler shape so it cannot regress back to render-only (which showed all
    origins regardless of the toggle)."""
    src = APP_JS.read_text(encoding="utf-8")
    start = src.index('$("#srcfilters").addEventListener(')
    end = src.index("});", start)
    handler = src[start:end]
    assert "async ev=>" in handler or "async (ev)" in handler, \
        "toggle handler must be async to await the re-fetch"
    assert "await loadAggregates()" in handler, \
        "toggle must re-fetch backend aggregates scoped by the new selection"
    assert "renderAll()" in handler, "toggle must re-render after the re-fetch"
    # the re-fetch must precede the re-render (scope changed -> no stale SRV_* reuse)
    assert handler.index("await loadAggregates()") < handler.index("renderAll()"), \
        "must re-fetch BEFORE re-render"


def test_renderstats_uses_server_stats_when_live():
    """No-JS-re-aggregation: in LIVE mode renderStats drives the tiles from the
    server-scoped SRV_STATS (single source for all four panels); the EVENTS
    recompute path remains ONLY for the !LIVE (MOCK/offline) case."""
    src = APP_JS.read_text(encoding="utf-8")
    start = src.index("function renderStats(")
    end = src.index("\n}", start)
    body = src[start:end]
    assert "if(LIVE && SRV_STATS){" in body, \
        "LIVE must read tiles from server-scoped SRV_STATS (not gated on EVENTS.length)"
    # the LIVE branch returns before the EVENTS recompute, so recompute is MOCK-only.
    assert body.index("if(LIVE && SRV_STATS){") < body.index("for(const e of EVENTS)"), \
        "EVENTS recompute must be the !LIVE fallback below the LIVE return"


def test_unknown_actor_has_explicit_card_filter_and_render_paths():
    src = APP_JS.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = APP_CSS.read_text(encoding="utf-8")

    for frag in ('id="st-unknown"', 'id="st-actor-warnings"', 'data-f="unknown"'):
        assert frag in html, f"missing unknown UI element: {frag}"
    for frag in ("--unknown:", ".stat.unknown", 'data-f="unknown"', ".fic.x",
                 ".pill.x", ".ev.unknown", ".who.unknown"):
        assert frag in css, f"missing neutral unknown style: {frag}"
    for frag in ('const ACTORS=["user","agent","unknown"]',
                 'active={user:true,agent:true,unknown:true',
                 'SRV_STATS.unknown', 'SRV_STATS.actor_warnings',
                 'ba.unknown', 'r.unknown', 'actorKey(e.actor)', 'actorLabel(e.actor)'):
        assert frag in src, f"missing unknown render contract: {frag}"

    for bad in ('e.actor==="user"?"u":"a"',
                'e.actor==="user"?"A 사용자":"B 에이전트"',
                'e.actor==="agent"?"B 에이전트":"A 사용자"',
                'const a=idxs.length-u;'):
        assert bad not in src, f"unknown still silently absorbed: {bad}"


def test_scan_source_warnings_persist_through_all_lifecycle_paths():
    src = APP_JS.read_text(encoding="utf-8")
    scan_handler = src[src.index('$("#scan-go").addEventListener('):src.index("/* ---------- util", src.index('$("#scan-go").addEventListener('))]
    show_scan = src[src.index("async function showScan("):src.index("/* ---------- boot", src.index("async function showScan("))]
    boot = src[src.index("async function boot("):src.index("async function loadEventsInBackground(")]
    load_events = src[src.index("async function loadEventsInBackground("):src.index("\n}", src.index("async function loadEventsInBackground("))]
    source_toggle = src[src.index('$("#srcfilters").addEventListener('):src.index("});", src.index('$("#srcfilters").addEventListener('))]

    assert "restoreScanWarnings(d)" in scan_handler       # (1) scan completion
    assert "scanWarningText()" in show_scan               # (2) zero-event scan screen
    assert '$("#scan-status").textContent=""' not in show_scan
    zero_branch = boot[boot.index("SRV_STATS.total===0"):boot.index('$("#scan-screen")')]
    assert 'await jget("/api/events")' in zero_branch
    assert "restoreScanWarnings(d)" in zero_branch
    assert "await showScan()" in zero_branch
    assert "restoreScanWarnings(d)" in load_events         # (3) refresh/reconnect
    assert load_events.index("restoreScanWarnings(d)") < load_events.index("renderStats()")
    assert "SCAN_WARNINGS=[]" not in source_toggle         # (4) scope transition
    assert "renderAll()" in source_toggle
    assert "warningCount(SRV_STATS.actor_warnings" in src
    assert 'warningCount(w' in src
    assert "경고 ${SCAN_WARNINGS.length}" in src


VIEW_JS = REPO / "clfx" / "web" / "static" / "view.js"
FORENSIC_JS = REPO / "clfx" / "web" / "static" / "forensic-views.js"
VIEW_HTML = REPO / "clfx" / "web" / "static" / "view.html"


# --- 23단계: 원격제어 노출 --------------------------------------------------

def test_remote_control_panel_is_wired_everywhere():
    """모달·독립 창·뷰어 3경로가 같은 렌더 1벌을 쓴다(복붙 금지). 한 곳만 살아 있으면
    팝업 차단 환경에서 패널이 통째로 사라진다."""
    src, html = APP_JS.read_text(encoding="utf-8"), INDEX_HTML.read_text(encoding="utf-8")
    view, fviews = VIEW_JS.read_text(encoding="utf-8"), FORENSIC_JS.read_text(encoding="utf-8")
    assert 'data-modal="remote"' in html and 'id="remote"' in html
    assert 'id="fn-remote"' in html                       # 뱃지 자리
    assert 'jget("/api/remote-control")' in src
    assert "ForensicViews.renderRemoteControl" in src
    assert "loadRemoteControl()" in src
    assert "renderRemoteControl: renderRemoteControl" in fviews
    assert '"/api/remote-control"' in view and "renderRemoteControl(vbody, d)" in view


def test_remote_badge_only_on_confirmed_remote():
    """unknown 에 원격 뱃지를 붙이면 '미상'이 원격으로 읽힌다 — remote 확정에만 붙인다."""
    src = APP_JS.read_text(encoding="utf-8")
    start = src.index("function remoteBadge(")
    body = src[start:src.index("\n}", start)]
    assert 'channelOf(e)!=="remote"' in body and "return \"\"" in body
    assert "unknown" not in body


def test_channel_absence_is_not_rendered_as_local():
    """필드 부재를 '-'로 뭉개면 로컬로 읽힌다. 네 상태를 각각 다른 문구로 쓴다."""
    src = APP_JS.read_text(encoding="utf-8")
    start = src.index("function channelRowsHTML(")
    body = src[start:src.index("\n}", start)]
    assert "관측 없음" in body and "로컬이라는 뜻이 아니다" in body
    assert "ch===null" in body                            # null(부재)을 따로 분기한다
    assert 'CHANNEL_TEXT={remote:' in src
    fviews = FORENSIC_JS.read_text(encoding="utf-8")
    assert "not_observed: \"관측 없음(필드 자체가 없음)\"" in fviews


def test_remote_only_chip_is_a_narrowing_filter():
    """다른 칩은 빼기(기본 on)지만 이건 좁히기(기본 off)다 — 기본값이 뒤집히면 무의미해진다."""
    src, html = APP_JS.read_text(encoding="utf-8"), INDEX_HTML.read_text(encoding="utf-8")
    assert 'data-f="remote-only" aria-pressed="false"' in html
    assert '"remote-only":false' in src
    start = src.index("function passFilter(")
    body = src[start:src.index("\n}", start)]
    assert 'active["remote-only"]&&channelOf(e)!=="remote"' in body


# --- 23단계 추가분: UI 결함 3건 ---------------------------------------------

def test_bypass_badge_escapes_the_ellipsis_flow():
    """①: .fbw 가 .fpath 안에 있으면 긴 경로에서 ellipsis 와 함께 통째로 잘린다
    (실측 2,318개 중 2,162개=93% 소실). 축소 안 되는 형제로 빼 두는 게 유일한 고정이다."""
    src, css = APP_JS.read_text(encoding="utf-8"), APP_CSS.read_text(encoding="utf-8")
    assert '<div class="fpathrow">${bw}<div class="fpath"' in src, \
        "뱃지는 .fpath 밖(앞)에 있어야 한다"
    assert '${esc(path)}${bw}' not in src, "뱃지가 다시 경로 뒤 텍스트 흐름으로 돌아갔다"
    assert ".fpathrow{display:flex" in css
    assert ".fbw{flex:0 0 auto" in css                    # 밀려나거나 줄어들지 않는다
    fpath = css[css.index(".fpath{"):css.index("}", css.index(".fpath{"))]
    assert "flex:1 1 auto" in fpath and "min-width:0" in fpath   # 줄어드는 쪽은 경로다
    assert 'class="fpath" title="${esc(path)}"' in src    # 잘린 경로 전문은 툴팁으로 보존


def test_event_card_target_is_clamped():
    """②: 긴 bash heredoc 이 통째로 렌더돼 이벤트 하나가 1,612px(뷰포트 1,000px)까지 갔다."""
    css, src = APP_CSS.read_text(encoding="utf-8"), APP_JS.read_text(encoding="utf-8")
    block = css[css.index(".ctarget{"):css.index("}", css.index(".ctarget{"))]
    assert "-webkit-line-clamp:3" in block and "display:-webkit-box" in block
    assert "overflow:hidden" in block
    assert 'class="ctarget" title="${esc(e.target)}"' in src
    # 전문 무손실: 상세 <pre> 는 preview 를 그대로 싣는다(접는 건 타임라인 카드뿐).
    assert "<pre>${esc(e.preview" in src


def test_counts_are_digit_grouped():
    """④: 타일이 146048 로 나와 자릿수를 눈으로 세야 했다. 표기를 num() 한 곳으로 모은다."""
    src = APP_JS.read_text(encoding="utf-8")
    assert 'function num(n){return Number(n||0).toLocaleString("ko-KR");}' in src
    for frag in ('$("#st-total").textContent=num(', '$("#st-user").textContent=num(',
                 '$("#fcount").textContent=num(rows.length)', "남은 ${num(rem)}건",
                 "${num(idxs.length)}건", 'font-family="ui-monospace">${num(total)}</text>'):
        assert frag in src, f"자리구분 누락: {frag}"
    # 회귀 가드: 타일이 다시 원시 숫자로 돌아가면 잡는다.
    assert '$("#st-total").textContent=SRV_STATS.total;' not in src


def test_keyword_legend_stays_readable_when_narrow():
    """④: 좁은 칸에서 라벨이 '학…' 한 글자로 짓눌렸다. 원인 둘(legend 압축·같은 줄의
    actor 분해)을 둘 다 wrap 으로 푼다. 인라인 style 이 남아 있으면 CSS 가 못 이긴다."""
    css, src = APP_CSS.read_text(encoding="utf-8"), APP_JS.read_text(encoding="utf-8")
    donut = css[css.index(".donutwrap{"):css.index("}", css.index(".donutwrap{"))]
    assert "flex-wrap:wrap" in donut                       # 좁으면 legend 가 도넛 밑으로
    legend = css[css.index(".legend{"):css.index("}", css.index(".legend{"))]
    assert "flex:1 1 150px" in legend                      # 150px 아래로는 안 눌린다
    assert ".legend .ksplit{flex:1 0 100%" in css          # actor 분해는 늘 자기 줄
    assert 'class="ksplit" style=' not in src, "인라인 style 이 CSS 규칙을 덮는다"
    assert 'class="li" data-kw="${esc(k)}" data-col="${col}" title=' in src   # 툴팁


def test_favicon_declared_so_no_404():
    for path in (INDEX_HTML, VIEW_HTML):
        assert '<link rel="icon" href="/logo.png"' in path.read_text(encoding="utf-8"), path.name


def test_no_filesystem_writes_in_app_js():
    """Forensic invariant: display-only client performs no writes; reverse hash
    search transmits hex digests only. Guard against accidental write APIs."""
    src = APP_JS.read_text(encoding="utf-8")
    forbidden = ["localStorage.setItem", "sessionStorage.setItem",
                 "fs.write", "writeFile"]
    for f in forbidden:
        assert f not in src, f"unexpected write API {f} in app.js"

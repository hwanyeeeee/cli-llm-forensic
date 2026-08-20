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


def test_no_filesystem_writes_in_app_js():
    """Forensic invariant: display-only client performs no writes; reverse hash
    search transmits hex digests only. Guard against accidental write APIs."""
    src = APP_JS.read_text(encoding="utf-8")
    forbidden = ["localStorage.setItem", "sessionStorage.setItem",
                 "fs.write", "writeFile"]
    for f in forbidden:
        assert f not in src, f"unexpected write API {f} in app.js"

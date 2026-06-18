"""Issue-1 + B-4 acceptance for clfx/web/static/forensic-views.js (frontend, display-only).

Issue-1 removes the auto leak/copy-suspect panel (its classification produced false
positives, e.g. _MEI PyInstaller self-extract) and relocates the on-demand reverse
hash-search into the access-file list. B-4 adds a read-only attestation (Chain of
Custody) render. Both are frontend-only; the engine remains the single source of
truth (no JS re-aggregation / re-judgement).

forensic-views.js is a classic browser IIFE; we exercise its pure render logic with
node (no jsdom) via a small DOM-stub harness, plus static source assertions on the
HTML/JS wiring. node absent -> skip (deterministic); present -> hard assert.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "clfx" / "web" / "static"
FV_JS = STATIC / "forensic-views.js"
APP_JS = STATIC / "app.js"
VIEW_JS = STATIC / "view.js"
VIEW_HTML = STATIC / "view.html"
INDEX_HTML = STATIC / "index.html"
HARNESS = Path(__file__).parent / "js" / "forensic_views_harness.js"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="node not installed")


def test_node_check_all_three_files():
    """node --check must pass on forensic-views.js, app.js, view.js (no syntax regressions)."""
    for f in (FV_JS, APP_JS, VIEW_JS):
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"{f.name}: {r.stderr}"


def test_forensic_views_harness():
    """Render-behavior harness: renderLeaks gone, hash-search helpers + renderAttestation
    present, attestation contract rendered + escaped + defensive on null."""
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout + r.stderr)
    assert "HARNESS OK" in r.stdout, (r.stdout + r.stderr)


# ---- Issue-1: auto leak panel removed everywhere ----

def test_renderleaks_gone_from_exports_and_source():
    """The auto leak classification (renderLeaks/leakRowHTML) is removed from
    forensic-views.js — both the definitions and the export. leakTmpPaths survives
    (retention evidence-marking) but the rendering path is gone."""
    src = FV_JS.read_text(encoding="utf-8")
    assert "renderLeaks:" not in src, "renderLeaks must be removed from the export object"
    assert "function renderLeaks" not in src, "renderLeaks definition must be removed"
    assert "function leakRowHTML" not in src, "leakRowHTML definition must be removed"
    # survivors required for relocation + retention evidence
    assert "function leakTmpPaths" in src, "leakTmpPaths must survive (retention evidence)"
    assert "function renderRetention" in src, "renderRetention must survive"


def test_hashsearch_and_attestation_exported():
    """hash-search helpers (relocation) + renderAttestation (B-4) are exported."""
    src = FV_JS.read_text(encoding="utf-8")
    for name in ("hashSearchBoxHTML:", "wireHashSearch:", "sha256Hex:",
                 "renderHashMatches:", "renderAttestation:"):
        assert name in src, f"export {name} missing"


def test_forensic_bar_has_no_leaks_button():
    """index.html forensic-bar: leaks button + fn-leaks badge REMOVED; the bar is now
    mcp + retention + attestation (3 buttons), and the #leaks pane is gone."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'data-modal="leaks"' not in html, "leaks button must be removed from forensic-bar"
    assert 'id="fn-leaks"' not in html, "fn-leaks badge span must be removed"
    assert 'id="leaks"' not in html, "the #leaks fm-pane must be removed"
    # the three surviving/added buttons
    assert 'data-modal="mcp"' in html
    assert 'data-modal="retention"' in html
    assert 'data-modal="attestation"' in html, "attestation button must be added"
    assert 'id="fn-attestation"' in html, "fn-attestation badge span must be added"
    assert 'id="attestation"' in html, "attestation fm-pane must be added"


def test_hashsearch_mount_point_outside_files():
    """The hash-search mount point (#filehash) lives near the #files header but is NOT
    inside #files (which renderFiles overwrites via innerHTML)."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="filehash"' in html, "a #filehash mount point must exist"
    # #filehash must appear OUTSIDE/before the #files container element, not nested in it.
    fh = html.index('id="filehash"')
    files = html.index('id="files"')
    assert fh < files, "#filehash must precede #files (not be clobbered by renderFiles)"


def test_app_js_relocates_hashsearch_and_drops_leaks():
    """app.js: renderLeaks removed; loadArtifacts no longer calls renderLeaks (keeps
    renderRetention); hash-search box mounted ONCE into #filehash; leaks dropped from
    modal TITLES; attestation loader wired."""
    src = APP_JS.read_text(encoding="utf-8")
    assert "function renderLeaks" not in src, "app.js renderLeaks must be removed"
    assert "ForensicViews.renderLeaks" not in src, "no call to removed renderLeaks"
    assert 'setFbadge("leaks"' not in src, "leaks badge call must be removed"
    # loadArtifacts keeps retention only
    start = src.index("async function loadArtifacts(")
    end = src.index("\n}", start)
    body = src[start:end]
    assert "renderRetention(" in body, "loadArtifacts must still render retention"
    assert "renderLeaks" not in body, "loadArtifacts must not call renderLeaks"
    # hash-search relocation: mounted once into #filehash via the shared helpers
    assert 'ForensicViews.hashSearchBoxHTML(' in src, "must mount the shared hash-search box"
    assert "ForensicViews.wireHashSearch(" in src, "must wire the shared hash-search box"
    assert '$("#filehash")' in src, "hash-search must mount into #filehash"
    # TITLES no longer contains leaks; attestation present
    assert "leaks:" not in src, "leaks must be dropped from modal TITLES"
    assert "attestation:" in src, "attestation must be in modal TITLES"


def test_app_js_loads_attestation_defensively():
    """app.js loadAttestation fetches /api/attestation, renders via ForensicViews, sets a
    neutral badge, and is defensive (no crash) when the endpoint is missing in dev."""
    src = APP_JS.read_text(encoding="utf-8")
    start = src.index("async function loadAttestation(")
    end = src.index("\n}", start)
    body = src[start:end]
    assert '"/api/attestation"' in body, "must fetch /api/attestation"
    assert "ForensicViews.renderAttestation(" in body, "must render via single-source FV"
    assert 'setFbadge("attestation"' in body, "must set the attestation badge"
    assert "catch" in body, "must be defensive (catch) when endpoint missing"
    assert "renderAttestation(box, null)" in body, "defensive placeholder via null payload"
    # wired into boot
    assert "loadAttestation()" in src, "loadAttestation must be called from boot"


def test_view_js_drops_leaks_supports_attestation():
    """view.js: leaks removed from TITLES + branch; mcp/retention preserved; attestation
    added (endpoint /api/attestation, render via FV.renderAttestation)."""
    src = VIEW_JS.read_text(encoding="utf-8")
    assert "leaks:" not in src, "leaks must be removed from view.js TITLES"
    assert "renderLeaks" not in src, "view.js must not reference renderLeaks"
    assert "/api/attestation" in src, "view.js must support the attestation endpoint"
    assert "renderAttestation" in src, "view.js must render attestation via FV"
    assert "/api/mcp" in src and "renderMcp" in src, "mcp branch preserved"
    assert "renderRetention" in src, "retention branch preserved"


def test_view_html_no_leaks_reference():
    """view.html carries no leaks reference."""
    html = VIEW_HTML.read_text(encoding="utf-8")
    assert "leaks" not in html.lower(), "view.html must not reference leaks"


def test_no_filesystem_writes_in_forensic_views():
    """Forensic invariant: display-only render performs no writes; the reverse
    hash-search transmits hex digests only (file content never leaves the browser).
    The attestation manifest is rendered read-only (no mutation APIs)."""
    src = FV_JS.read_text(encoding="utf-8")
    forbidden = ["localStorage.setItem", "sessionStorage.setItem", "fs.write", "writeFile"]
    for f in forbidden:
        assert f not in src, f"unexpected write API {f} in forensic-views.js"
    # hash-search transmits only the hex digest (no FormData/body with file content).
    assert "/api/hash-search?sha=" in src, "hash-search sends the hex digest as a query param"
    assert "new FormData" not in src, "must not POST file content"

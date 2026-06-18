/* Node harness for clfx/web/static/forensic-views.js (Issue-1 + B-4 attestation).
   forensic-views.js is a classic browser IIFE that publishes window.ForensicViews.
   We stub an inert DOM/window so require() succeeds (the existing app harness stub
   style), then assert:

   Issue-1 (remove auto leak panel, relocate hash-search):
     1. renderLeaks is GONE from the export object (auto leak classification removed —
        it produced false positives, e.g. _MEI PyInstaller self-extract).
     2. The hash-search helpers SURVIVE for relocation into the file-list context:
        hashSearchBoxHTML, wireHashSearch, sha256Hex, renderHashMatches are exported.
     3. leakTmpPaths + renderRetention survive (retention evidence-marking still uses
        leakTmpPaths over the unchanged d.hashes).
     4. hashSearchBoxHTML(label) renders the box (file input + button) and honors a
        file-list context label; it transmits NO file content (hex-only is wireHashSearch).

   B-4 (read-only attestation / Chain of Custody):
     5. renderAttestation is EXPORTED (single-source render).
     6. renderAttestation(el, d) renders the assurance note, the summary line
        (acquired N / stat-only M / write-delete-rename 0 / all read-only), the basis,
        and a searchable manifest (filter input + acquired path: sha256(12)... rows).
     7. Dynamic strings are escaped (XSS guard) — an injected path/sha is escaped.
     8. renderAttestation(el, null) is defensive (placeholder, no crash) for the
        dev case where /api/attestation is missing.

   node absent -> the pytest wrapper skips; present -> hard assert. */

const path = require("path");

// --- inert DOM/window stubs (only what forensic-views.js touches at render time) ---
function makeEl() {
  const listeners = {};
  const el = {
    style: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    dataset: {},
    _children: {},
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    _fire(type) { (listeners[type] || []).forEach(fn => fn()); },
    appendChild() {}, insertBefore() {}, setAttribute() {}, getAttribute() { return null; },
    querySelector(sel) { return el._children[sel] || (el._children[sel] = makeEl()); },
    querySelectorAll() { return []; },
    closest() { return null; },
  };
  el.textContent = ""; el.innerHTML = ""; el.value = ""; el.files = null; el.hidden = false;
  return el;
}
global.document = {
  querySelector() { return makeEl(); }, querySelectorAll() { return []; },
  getElementById() { return makeEl(); }, createElement() { return makeEl(); },
  addEventListener() {},
};
global.window = {};
global.crypto = { subtle: { digest() { return Promise.resolve(new ArrayBuffer(32)); } } };

const fvPath = path.resolve(__dirname, "..", "..", "clfx", "web", "static", "forensic-views.js");
require(fvPath);
const FV = global.window.ForensicViews;

let failed = false;
function ok(cond, msg) { if (!cond) { console.error("FAIL " + msg); failed = true; } }
function has(s, sub, msg) { ok(String(s).indexOf(sub) !== -1, msg + " (missing: " + sub + ")"); }
function lacks(s, sub, msg) { ok(String(s).indexOf(sub) === -1, msg + " (unexpected: " + sub + ")"); }

ok(FV && typeof FV === "object", "window.ForensicViews exported");

// ---- 1) Issue-1: renderLeaks removed from exports ----
ok(!("renderLeaks" in FV), "renderLeaks must be REMOVED from exports (auto leak classification dropped)");

// ---- 2) hash-search helpers survive for relocation ----
["hashSearchBoxHTML", "wireHashSearch", "sha256Hex", "renderHashMatches"].forEach(function (n) {
  ok(typeof FV[n] === "function", "export " + n + " must survive for hash-search relocation");
});

// ---- 3) retention evidence-marking survives ----
["leakTmpPaths", "renderRetention", "renderMcp"].forEach(function (n) {
  ok(typeof FV[n] === "function", "export " + n + " must survive");
});
// leakTmpPaths still reads d.hashes (retention evidence set) unchanged.
{
  const set = FV.leakTmpPaths({ hashes: [
    { leak_suspect: true, paths: [{ in_tmp: true, path: "/tmp/x" }, { in_tmp: false, path: "/home/x" }] },
    { leak_suspect: false, paths: [{ in_tmp: true, path: "/tmp/skip" }] },
  ] });
  ok(set.has("/tmp/x"), "leakTmpPaths collects in_tmp paths of leak_suspect clusters");
  ok(!set.has("/home/x"), "leakTmpPaths excludes non-tmp paths");
  ok(!set.has("/tmp/skip"), "leakTmpPaths excludes non-leak_suspect clusters");
}

// ---- 4) hashSearchBoxHTML renders box + honors file-list label, no content leak ----
{
  const html = FV.hashSearchBoxHTML("파일 선택 → 동일 해시 tmp 사본 검색");
  has(html, 'id="hsfile"', "hashSearchBoxHTML renders file input");
  has(html, 'id="hsbtn"', "hashSearchBoxHTML renders search button");
  has(html, "파일 선택 → 동일 해시 tmp 사본 검색", "hashSearchBoxHTML honors file-list context label");
  // default label when none passed
  has(FV.hashSearchBoxHTML(), "동일 해시", "hashSearchBoxHTML default label present");
}

// ---- 5) renderAttestation exported ----
ok(typeof FV.renderAttestation === "function", "renderAttestation must be EXPORTED (B-4 single-source render)");

// ---- 6) [R8-B] renderAttestation renders plain-language Chain-of-Custody ----
{
  const el = makeEl();
  FV.renderAttestation(el, {
    acquired: [
      { path: "/proj/a.txt", sha256: "deadbeefcafe0123456789" },
      { path: "/proj/sub/b.py", sha256: "0011223344556677889900" },
    ],
    acquired_count: 2,
    stat_only_count: 5,
    all_read_only: true,
    modes_seen: ["r", "rb"],
    write_delete_rename_ops: 0,
    note: "라이브 제자리 분석. 취득 시 SHA-256 매니페스트 기록.",
  });
  const h = el.innerHTML;
  // (1)(2) plain-language header + lead (no dev jargon up top)
  has(h, "증거 무결성", "plain-language header");
  has(h, "분석이 원본을 변경하지 않았음", "header tagline");
  has(h, "100% 읽기 전용", "lead asserts 100% read-only in plain language");
  // (3) plain-language stat cards
  has(h, "읽기 전용 접근", "summary: read-only access");
  has(h, "변경(쓰기/삭제/이동) 횟수", "stat card: write/delete/move count (plain)");
  has(h, "해시 기록한 증거 파일", "stat card: acquired files (plain)");
  has(h, "메타데이터만 확인", "stat card: stat-only (plain)");
  // (4) verification-method section
  has(h, "무결성 검증 방법", "verification-method section present");
  has(h, "다시 계산해", "verification method explains re-hash compare");
  // (5) dev terms moved into a collapsible <details>
  has(h, "기술 상세", "developer terms moved into collapsible 기술 상세");
  has(h, "attest-tech", "기술 상세 is a <details> (collapsed by default)");
  has(h, "_ro_open", "_ro_open mentioned (only inside 기술 상세)");
  has(h, "r, rb", "observed open modes shown in 기술 상세");
  has(h, "라이브 제자리 분석", "note retained inside 기술 상세");
  // (6) acquired ledger collapsed by default, search inside
  has(h, "취득 해시 원장 (전체 2개)", "ledger collapsed with total count");
  has(h, "attest-ledger", "ledger is a <details> (collapsed by default)");
  has(h, 'id="attfilter"', "searchable manifest still has a filter input (inside ledger)");
  has(h, "/proj/a.txt", "manifest lists acquired path");
  has(h, "deadbeefcafe", "manifest shows sha256 prefix");
  lacks(h, "deadbeefcafe0123456789…", "manifest truncates sha to a prefix (not full+ellipsis)");
  // (4b) CSV export link — same-origin download of the acquisition hash manifest.
  has(h, 'href="/api/attestation.csv"', "CSV export links to /api/attestation.csv");
  has(h, "취득 해시 원장 CSV 내보내기", "CSV export button labelled in plain Korean");
  has(h, 'download="acquisition-hash-manifest.csv"', "download attribute hints standard filename");
}

// ---- 9) [R8-A] renderMcp config section: deduped/grouped by server ----
{
  const el = makeEl();
  FV.renderMcp(el, {
    usage: [{ server: "playwright", tool: "click", count: 3 }],
    configs: [
      { server: "playwright", scope: "project", project: "/a", command: "npx playwright", env_keys: ["K"] },
      { server: "playwright", scope: "project", project: "/b", command: "npx playwright", env_keys: [] },
      { server: "playwright", scope: "global", project: null, command: "npx playwright", env_keys: [] },
      { server: "ghidra", scope: "connector", project: null, command: "", env_keys: [] },
    ],
    configured_unused: [],
    used_unconfigured: ["pyghidra"],
  });
  const h = el.innerHTML;
  has(h, "설정된 외부 서버 2종 (인스턴스 4)", "configs deduped: N kinds (M instances)");
  has(h, "mcpcfgwrap", "config section header is itself a collapsible <details> toggle");
  has(h, "mcpcfg", "each config server is a <details> group");
  has(h, "cfgscope", "scope badges rendered per server group");
  has(h, "×3", "playwright group shows its 3 instances (×3)");
  has(h, "설정 출처 미확인: pyghidra", "used_unconfigured neutral line preserved");
}

// ---- 7) XSS: dynamic strings escaped ----
{
  const el = makeEl();
  FV.renderAttestation(el, {
    acquired: [{ path: "<img src=x onerror=1>", sha256: "<script>" }],
    acquired_count: 1, stat_only_count: 0, all_read_only: true,
    modes_seen: ["r"], write_delete_rename_ops: 0,
    note: "<b>note</b>",
  });
  const h = el.innerHTML;
  lacks(h, "<img src=x onerror=1>", "path must be escaped");
  has(h, "&lt;img src=x onerror=1&gt;", "path escaped to entities");
  lacks(h, "<script>", "note/sha must be escaped (no raw <script>)");
}

// ---- 8) defensive: null payload -> placeholder, no crash ----
{
  const el = makeEl();
  let threw = false;
  try { FV.renderAttestation(el, null); } catch (e) { threw = true; }
  ok(!threw, "renderAttestation(el, null) must not throw (dev: endpoint missing)");
  has(el.innerHTML, "불러오기 실패", "null payload renders a placeholder");
}

if (failed) { console.error("HARNESS FAILED"); process.exit(1); }
else { console.log("HARNESS OK"); }

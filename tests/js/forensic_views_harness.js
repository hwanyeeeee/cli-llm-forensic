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
  has(h, "CSV로 내보내기", "CSV export button labelled 'CSV로 내보내기'");
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
  has(h, "설정된 MCP", "config section toggle labelled 설정된 MCP");
  has(h, "mcpcfgwrap", "config section header is itself a collapsible <details> toggle");
  has(h, "mcpcfg", "each config server is a <details> group (dedupe by server)");
  has(h, "×3", "playwright group collapses its 3 instances (dedupe proven)");
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

// ---- 10) renderRetention: attributed-first, origin-aware expiry, residue collapsed ----
{
  const rows = [
    // wsl attributed row (agent, expires 5, source)
    { path: "/tmp/work.txt", size: 10, mtime: "2026-06-10T00:00:00Z", atime: "2026-06-10T00:00:00Z",
      age_days: 8, expires_in_days: 5, origin: "wsl", retention_policy: "wsl-systemd-30d",
      attributed: true, actor: "agent", transcript_action: "write",
      source: { file: "t.jsonl", line: 12 } },
    // windows attributed row (user, expires null)
    { path: "C:\\Temp\\u.txt", size: 20, mtime: "2026-06-01T00:00:00Z", atime: "2026-06-01T00:00:00Z",
      age_days: 17, expires_in_days: null, origin: "windows", retention_policy: "windows-none",
      attributed: true, actor: "user", transcript_action: "read",
      source: { file: "u.jsonl", line: 3 } },
    // non-attributed environment residue
    { path: "/tmp/resi/<x>.bin", size: 30, mtime: "2026-05-01T00:00:00Z", atime: "2026-05-01T00:00:00Z",
      age_days: 48, expires_in_days: 0, origin: "wsl", retention_policy: "wsl-systemd-30d",
      attributed: false, actor: null, transcript_action: null, source: null },
  ];
  const el = makeEl();
  const leakSet = new Set(["/tmp/work.txt"]);
  FV.renderRetention(el, rows, leakSet);
  const h = el.innerHTML;
  // header completeness: total + attributed count
  has(h, "전체 tmp", "retention header discloses full total (completeness)");
  has(h, "transcript 귀속", "retention header shows attributed count");
  has(h, "만료임박", "retention header shows soon count");
  // note replaced exactly
  has(h, "WSL /tmp는 ~30일(systemd) 후 정리될 수 있음", "retention note WSL phrase");
  has(h, "Windows tmp는 자동삭제 없음(무기한 잔존)", "retention note Windows phrase");
  has(h, "transcript에 기록된 작업 파일만", "retention note attributed-only phrase");
  lacks(h, "tmp 파일은 마지막 수정 후 약 30일", "old uniform-30d note removed");
  // actor badges
  has(h, "B", "agent actor badge B shown");
  has(h, "A", "user actor badge A shown");
  has(h, "actorbadge", "actor badge class present");
  // source shown + escaped path/line
  has(h, "t.jsonl:12", "wsl row shows source file:line");
  has(h, "rsource", "source uses .rsource class");
  // wsl expiry vs windows no-expiry
  has(h, "만료까지", "wsl row shows 만료까지 N일");
  has(h, "자동삭제 없음", "windows row shows 자동삭제 없음");
  // non-attributed collapsed details
  has(h, "환경 잔존물(귀속 안 됨)", "non-attributed residue section labelled");
  has(h, "<details", "residue is a collapsed <details>");
  // evidence marking still works
  has(h, "증거 관련", "evidence tag present for leakSet path");
  has(h, "evtag", "evidence tag class present");
  // escaping: residue path with <x> escaped, never raw
  lacks(h, "/tmp/resi/<x>.bin", "residue path must be escaped (no raw <x>)");
  has(h, "&lt;x&gt;", "residue path escaped to entities");
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

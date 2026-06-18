/* Node harness for clfx/web/static/app.js pure logic (OPT-7/OPT-8).
   app.js is a classic browser script: it runs DOM bootstrap at load time.
   We stub a minimal inert DOM so require() succeeds without jsdom, then
   exercise the pure functions it exports (progressInfo, STAGE_LABELS).
   Pure functions have NO DOM dependency — the stubs only keep the
   top-level bootstrap from throwing. */

const path = require("path");

// --- inert DOM element: every property access returns chainable no-ops ---
function makeEl() {
  const el = {
    style: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    dataset: {},
    addEventListener() {},
    appendChild() {},
    insertBefore() {},
    setAttribute() {},
    getAttribute() { return null; },
    setPointerCapture() {},
    querySelector() { return makeEl(); },
    querySelectorAll() { return []; },
    closest() { return null; },
    getBoundingClientRect() { return { width: 0, height: 0 }; },
    getPropertyValue() { return "0"; },
    scrollIntoView() {},
    focus() {},
    remove() {},
    offsetHeight: 0,
    offsetWidth: 0,
    hidden: false,
    parentElement: null,
  };
  // textContent / innerHTML / value are plain writable props
  el.textContent = "";
  el.innerHTML = "";
  el.value = "";
  return el;
}

const documentStub = {
  querySelector() { return makeEl(); },
  querySelectorAll() { return []; },
  getElementById() { return makeEl(); },
  createElement() { return makeEl(); },
  addEventListener() {},
};

const windowStub = {
  addEventListener() {},
  innerWidth: 1280,
  innerHeight: 800,
  getComputedStyle() { return { getPropertyValue() { return "0"; } }; },
  open() { return null; },
};

global.document = documentStub;
global.window = windowStub;
global.getComputedStyle = windowStub.getComputedStyle;
// boot() awaits fetch; reject → harmless MOCK path. setTimeout exists in node.
global.fetch = () => Promise.reject(new Error("no network in harness"));

const appPath = path.resolve(__dirname, "..", "..", "clfx", "web", "static", "app.js");
const app = require(appPath);

// ---- assertions ----
function eq(actual, expected, msg) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) { console.error(`FAIL ${msg}\n  expected: ${e}\n  actual:   ${a}`); process.exitCode = 1; }
}

const { progressInfo, STAGE_LABELS } = app;

if (typeof progressInfo !== "function") {
  console.error("FAIL progressInfo not exported"); process.exit(1);
}

// 1) Stage map -> Korean labels (exact spec).
eq(STAGE_LABELS.parse, "파싱", "label parse");
eq(STAGE_LABELS.mask, "마스킹", "label mask");
eq(STAGE_LABELS.resolve, "경로해석", "label resolve");
eq(STAGE_LABELS["walk-tmp"], "tmp 스캔", "label walk-tmp");
eq(STAGE_LABELS.hash, "아티팩트 해싱", "label hash");
eq(STAGE_LABELS.attribution, "주체 대조", "label attribution");
eq(STAGE_LABELS.retention, "보존기간", "label retention");
eq(STAGE_LABELS.mcp, "MCP 대조", "label mcp");
eq(STAGE_LABELS.finalize, "마무리", "label finalize");

// 2) New-server hashing stage: shows "아티팩트 해싱 12000/44000" and uses overall_percent for bar.
{
  const pr = { total: 100, done: 100, events: 500, finished: false,
    stage: "hash", stage_done: 12000, stage_total: 44000, overall_percent: 73 };
  const r = progressInfo(pr, 10);
  eq(r.pct, 73, "hash pct=overall_percent");
  if (!r.label.includes("아티팩트 해싱 12000/44000")) {
    console.error(`FAIL hash label substring\n  actual: ${r.label}`); process.exitCode = 1;
  }
  if (!r.label.includes("(73%)")) { console.error(`FAIL hash overall%% in label: ${r.label}`); process.exitCode = 1; }
  if (!r.label.includes("누적 500건")) { console.error(`FAIL hash events: ${r.label}`); process.exitCode = 1; }
}

// 3) overall_percent prevents "stuck at 100%" after parse finishes (done==total but stage running).
{
  const pr = { total: 44000, done: 44000, events: 9000, finished: false,
    stage: "mcp", stage_done: 3, stage_total: 10, overall_percent: 96 };
  const r = progressInfo(pr, 20);
  eq(r.pct, 96, "mcp not stuck at 100");
  if (!r.label.startsWith("MCP 대조 3/10")) {
    console.error(`FAIL mcp label start: ${r.label}`); process.exitCode = 1;
  }
}

// 4) Unknown stage code falls back to raw code as name (no crash).
{
  const r = progressInfo({ stage: "weird", stage_done: 1, stage_total: 2, overall_percent: 50, events: 0 }, 5);
  if (!r.label.startsWith("weird 1/2")) { console.error(`FAIL unknown stage: ${r.label}`); process.exitCode = 1; }
  eq(r.pct, 50, "unknown stage pct");
}

// 5) stage with no stage_total -> no ratio segment but still labelled.
{
  const r = progressInfo({ stage: "finalize", overall_percent: 99, events: 9000 }, 30);
  if (r.label.includes("/")) { console.error(`FAIL finalize should have no ratio: ${r.label}`); process.exitCode = 1; }
  if (!r.label.startsWith("마무리 (99%)")) { console.error(`FAIL finalize label: ${r.label}`); process.exitCode = 1; }
}

// 6) EQUIVALENCE: old server (no stage fields) -> byte-identical to legacy parse label.
//    Reference computed exactly the OLD way the polling loop used to.
function legacyLabel(pr, sec) {
  const pct = pr.total ? Math.round(pr.done / pr.total * 100) : 0;
  let label = `파싱 중 ${pr.done}/${pr.total} 파일 (${pct}%) · 누적 ${pr.events || 0}건 · 경과 ${sec}초`;
  if (pct >= 5 && pct < 100) { const eta = Math.round(sec * (100 - pct) / pct); label += ` · 예상 ${eta}초`; }
  return { pct, label };
}
{
  const cases = [
    { total: 0, done: 0, events: 0 },
    { total: 100, done: 0, events: 0 },
    { total: 100, done: 50, events: 1234 },
    { total: 100, done: 100, events: 9999 },
    { total: 44000, done: 1, events: 3 },
    { total: 44000, done: 21999, events: 50000 },
  ];
  for (const c of cases) {
    for (const sec of [0, 1, 7, 60, 123]) {
      const ref = legacyLabel(c, sec);
      const got = progressInfo(c, sec);  // no stage fields -> fallback path
      eq(got.pct, ref.pct, `legacy pct ${JSON.stringify(c)} sec=${sec}`);
      eq(got.label, ref.label, `legacy label ${JSON.stringify(c)} sec=${sec}`);
    }
  }
}

// 7) Defensive: empty stage string ("") must NOT trigger stage path (falls back).
{
  const ref = legacyLabel({ total: 100, done: 40, events: 5 }, 10);
  const got = progressInfo({ total: 100, done: 40, events: 5, stage: "" }, 10);
  eq(got.label, ref.label, "empty stage falls back to parse label");
}

if (process.exitCode) { console.error("HARNESS FAILED"); }
else { console.log("HARNESS OK"); }

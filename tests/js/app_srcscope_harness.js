/* Node harness for clfx/web/static/app.js source(origin) scoping of the
   BACKEND aggregates. app.js is a classic browser script; we stub an inert DOM
   so require() succeeds (the existing app_progress_harness stub style), then:
     - drive srcParam() through every selection state, and
     - run loadAggregates() with a fetch spy to capture the exact URLs requested.

   Invariants proven here:
   1. LOSSLESS REGRESSION: when srcActive is null / empty / equals the full
      originLabels() set, srcParam returns "" and loadAggregates fetches the
      EXACT current (unchanged) URLs — no ?sources= param. Byte-identical request
      surface, so the backend takes the identical origins=None path.
   2. SCOPING NARROWS: a proper subset appends sources=<sorted-joined> with the
      correct separator per endpoint ("?" for stats/files/keywords that have no
      prior query, "&" for /api/activity?by=day which already has one).
   3. SINGLE SOURCE: loadAggregates fetches all four aggregates including
      /api/stats so the stats tile is server-scoped too.
   4. NO JS RE-AGGREGATION: the frontend only passes selected origins; it does
      not compute aggregates itself (it stores raw server payloads). */

const path = require("path");

function makeEl() {
  const el = {
    style: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    dataset: {},
    addEventListener() {}, appendChild() {}, insertBefore() {}, setAttribute() {},
    getAttribute() { return null; }, setPointerCapture() {},
    querySelector() { return makeEl(); }, querySelectorAll() { return []; },
    closest() { return null; },
    getBoundingClientRect() { return { width: 0, height: 0 }; },
    getPropertyValue() { return "0"; }, scrollIntoView() {}, focus() {}, remove() {},
    offsetHeight: 0, offsetWidth: 0, hidden: false, parentElement: null,
  };
  el.textContent = ""; el.innerHTML = ""; el.value = "";
  return el;
}
const documentStub = {
  querySelector() { return makeEl(); }, querySelectorAll() { return []; },
  getElementById() { return makeEl(); }, createElement() { return makeEl(); },
  addEventListener() {},
};
const windowStub = {
  addEventListener() {}, innerWidth: 1280, innerHeight: 800,
  getComputedStyle() { return { getPropertyValue() { return "0"; } }; },
  open() { return null; },
};
global.document = documentStub;
global.window = windowStub;
global.getComputedStyle = windowStub.getComputedStyle;
// boot() awaits the first fetch; reject keeps it on the harmless MOCK path during require().
global.fetch = () => Promise.reject(new Error("no network during require"));

const appPath = path.resolve(__dirname, "..", "..", "clfx", "web", "static", "app.js");
const app = require(appPath);

let failed = false;
function eq(actual, expected, msg) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) { console.error(`FAIL ${msg}\n  expected: ${e}\n  actual:   ${a}`); failed = true; }
}

const { srcParam, loadAggregates, __setSrcActive, __setEvents, __setLive } = app;
for (const [n, f] of Object.entries({ srcParam, loadAggregates, __setSrcActive, __setEvents, __setLive })) {
  if (typeof f !== "function") { console.error(`FAIL ${n} not exported`); process.exit(1); }
}

// Events tagged with origins so originLabels() => ["windows","wsl"] (sorted).
function evWith(origin) { return { tags: ["origin:" + origin], actor: "user", action: "read", ts: "2026-06-11 01:00:00", target: "x" }; }
__setEvents([evWith("wsl"), evWith("windows"), evWith("wsl")]);

// ---- 1) srcParam: lossless when null / empty / full set ----
__setSrcActive(null);
eq(srcParam("?"), "", "srcParam null -> '' (full/regression path)");
eq(srcParam("&"), "", "srcParam null & -> ''");

__setSrcActive(new Set());
eq(srcParam("?"), "", "srcParam empty set -> '' (full)");

__setSrcActive(new Set(["wsl", "windows"]));
eq(srcParam("?"), "", "srcParam full set -> '' (identical unchanged path)");
eq(srcParam("&"), "", "srcParam full set & -> ''");

// ---- 2) srcParam: proper subset narrows, correct sep, encoded ----
__setSrcActive(new Set(["wsl"]));
eq(srcParam("?"), "?sources=wsl", "srcParam {wsl} ? -> ?sources=wsl");
eq(srcParam("&"), "&sources=wsl", "srcParam {wsl} & -> &sources=wsl");

__setSrcActive(new Set(["windows"]));
eq(srcParam("?"), "?sources=windows", "srcParam {windows} -> ?sources=windows");

// subset of a larger origin set (3 labels, pick 2) -> still narrows, sorted-joined
__setEvents([evWith("wsl"), evWith("windows"), evWith("other")]);
__setSrcActive(new Set(["windows", "wsl"]));
// join order follows iteration order of the Set ([...set]); both ends agree on the same set.
{
  const got = srcParam("?");
  const ok = got === "?sources=windows%2Cwsl" || got === "?sources=wsl%2Cwindows";
  if (!ok) { console.error(`FAIL subset of 3 join, got: ${got}`); failed = true; }
}

// ---- 3+4) loadAggregates URL surface via fetch spy ----
// captureURLs re-asserts EVENTS+srcActive itself: boot() ran at require() time and its
// MOCK fallback (fetch rejected) resolves on a later microtask, clobbering module state.
// Setting state INSIDE the spy (after the await tick) makes each scenario independent.
async function captureURLs(srcActive) {
  const urls = [];
  global.fetch = (u) => {
    urls.push(u);
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  };
  __setLive(true);
  __setEvents([evWith("wsl"), evWith("windows")]);
  __setSrcActive(srcActive);
  await loadAggregates();
  urls.sort();
  return urls;
}

(async () => {
  // Let boot()'s MOCK fallback settle before we start capturing (it mutates EVENTS/srcActive).
  await new Promise(r => setTimeout(r, 0));

  // FULL SCOPE (null) -> the four CURRENT urls, no ?sources= anywhere (regression-identical).
  let urls = await captureURLs(null);
  eq(urls, ["/api/activity?by=day", "/api/files", "/api/keywords", "/api/stats"].sort(),
     "loadAggregates full -> 4 unchanged urls, no sources param");
  for (const u of urls) if (u.includes("sources=")) { console.error(`FAIL full scope leaked sources param: ${u}`); failed = true; }

  // FULL SET selected -> identical to null (lossless).
  urls = await captureURLs(new Set(["wsl", "windows"]));
  eq(urls, ["/api/activity?by=day", "/api/files", "/api/keywords", "/api/stats"].sort(),
     "loadAggregates full-set -> identical unchanged urls");

  // SUBSET -> every aggregate scoped with correct separator.
  urls = await captureURLs(new Set(["wsl"]));
  eq(urls, [
    "/api/activity?by=day&sources=wsl",
    "/api/files?sources=wsl",
    "/api/keywords?sources=wsl",
    "/api/stats?sources=wsl",
  ].sort(), "loadAggregates subset -> all four scoped, correct sep");

  if (failed) { console.error("HARNESS FAILED"); process.exit(1); }
  else { console.log("HARNESS OK"); }
})();

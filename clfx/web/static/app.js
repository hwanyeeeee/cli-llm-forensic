let CURRENT = [];  // 현재 표시 중인 이벤트 집합(서버가 준 것)

const $ = (s) => document.querySelector(s);
const timeline = $("#timeline");
const banner = $("#banner");
const summaryBox = $("#summary");
const detail = $("#detail");

function badge(t) { return `<span class="badge ${t}">${t}</span>`; }

function card(e, i) {
  const tags = (e.tags || []).map(badge).join("");
  const prev = e.preview ? `<div class="preview">${escapeHtml(e.preview)}</div>` : "";
  return `<div class="card ${e.actor}" data-i="${i}">
    <div class="meta">${e.ts || "?"} · ${e.actor}/${e.action} ${tags}</div>
    <div class="target">${escapeHtml(e.target || "")}</div>
    ${prev}
  </div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function activeFilters() {
  const actors = [...document.querySelectorAll(".f-actor:checked")].map(c => c.value);
  const tags = [...document.querySelectorAll(".f-tag:checked")].map(c => c.value);
  const actions = [...document.querySelectorAll(".f-action:checked")].map(c => c.value);
  return { actors, tags, actions };
}

function render() {
  const { actors, tags, actions } = activeFilters();
  // 클라이언트측 표시 토글만(이미 분류된 필드 보이기/숨기기 — 로직 재구현 아님)
  const shown = CURRENT.filter(e =>
    actors.includes(e.actor) &&
    actions.includes(e.action) &&
    ((e.tags || []).length === 0 || (e.tags || []).some(t => tags.includes(t)) || !(e.tags || []).some(t => ["secret","pii","bypass-mode"].includes(t)))
  );
  timeline.innerHTML = shown.map((e) => card(e, CURRENT.indexOf(e))).join("")
    || '<div class="count">표시할 이벤트 없음</div>';
}

function showDetail(e) {
  detail.classList.remove("hidden");
  detail.innerHTML = `<h3>이벤트 상세</h3>
    <div>${e.ts || "?"} · <b>${e.actor}/${e.action}</b></div>
    <div>target: ${escapeHtml(e.target || "")}</div>
    <div>tags: ${(e.tags || []).join(", ") || "-"}</div>
    <div>session: ${escapeHtml(e.session || "")}</div>
    <div>출처: <span class="src">${escapeHtml(e.source.file)}:${e.source.line}</span></div>
    <pre>${escapeHtml(e.preview || "")}</pre>`;
}

async function load(url) {
  banner.classList.add("hidden");
  try {
    const r = await fetch(url);
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    CURRENT = data.events || [];
    if (data.summary && data.summary.text) {
      summaryBox.classList.remove("hidden");
      summaryBox.textContent = "요약: " + data.summary.text;
    } else {
      summaryBox.classList.add("hidden");
    }
    render();
  } catch (err) {
    banner.classList.remove("hidden");
    banner.textContent = "에러: " + err.message;
  }
}

$("#q-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const q = $("#q").value.trim();
  if (q) load("/api/query?q=" + encodeURIComponent(q));
});
$("#reset").addEventListener("click", () => { $("#q").value = ""; load("/api/events"); });
document.querySelectorAll(".f-actor, .f-tag, .f-action").forEach(c => c.addEventListener("change", render));
timeline.addEventListener("click", (ev) => {
  const c = ev.target.closest(".card");
  if (c) showDetail(CURRENT[+c.dataset.i]);
});

load("/api/events");  // 초기 타임라인

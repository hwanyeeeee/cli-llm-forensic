/* view.js — 포렌식 독립 뷰 페이지(?view=leaks|attrib|mcp|retention).
   순수 프레젠테이션: /api/* 불변, 렌더 HTML 빌드는 ForensicViews(forensic-views.js) 1벌만 호출(DRY).
   엔진/API가 단일 진실원천 — 여기서 재집계/재판정 금지. 외부 전송 0, 이미 마스킹된 로컬 데이터만.
   반응형: CSS가 width 따라 자연 reflow — JS 리사이즈 핸들러 불요. */
(function () {
  "use strict";

  var key = new URLSearchParams(location.search).get("view");
  var TITLES = {
    leaks: "유출·복사 의심 · 해시 대조",
    attrib: "주체 왜곡 보정 · FS↔transcript JOIN",
    mcp: "MCP 연결 흔적 · 설정 vs 실사용",
    retention: "tmp 보존기간 · 만료 잔여"
  };

  document.title = TITLES[key] || "포렌식 뷰";
  document.getElementById("vhead").textContent = TITLES[key] || key;

  var vbody = document.getElementById("vbody");

  async function load() {
    if (!TITLES[key]) { vbody.innerHTML = '<div class="empty">알 수 없는 뷰</div>'; return; }
    var endpoint = key === "mcp" ? "/api/mcp" : "/api/artifacts";
    var d;
    try {
      var res = await fetch(endpoint);
      d = await res.json();
    } catch (_) {
      vbody.innerHTML = '<div class="empty">불러오기 실패</div>';
      return;
    }
    var FV = window.ForensicViews;
    if (key === "leaks") {
      FV.renderLeaks(vbody, d);
      mountHashSearch(FV);                  // #2b: leaks 뷰에만 해시검색 박스 부착
    }
    else if (key === "attrib") FV.renderAttrib(vbody, d);
    else if (key === "mcp") FV.renderMcp(vbody, d);
    else if (key === "retention") FV.renderRetention(vbody, d.retention);
  }

  /* #2b 해시검색: 마크업/해시 로직은 ForensicViews 위임(DRY). 파일내용 전송 0 — hex만 조회. */
  function mountHashSearch(FV) {
    var box = document.createElement("div");
    box.innerHTML = FV.hashSearchBoxHTML();
    vbody.appendChild(box);
    var btn = box.querySelector("#hsbtn");
    var fileInput = box.querySelector("#hsfile");
    var result = box.querySelector("#hsresult");
    if (!btn || !fileInput || !result) return;
    btn.addEventListener("click", function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) { result.innerHTML = '<div class="empty">파일을 선택하세요</div>'; return; }
      FV.sha256Hex(file)                                 // 브라우저 로컬 SHA-256 hex
        .then(function (hex) {
          return fetch("/api/hash-search?sha=" + encodeURIComponent(hex)); // hex만 전송
        })
        .then(function (res) { return res.json(); })
        .then(function (j) { FV.renderHashMatches(result, j.matches); })
        .catch(function () { result.innerHTML = '<div class="empty">검색 실패</div>'; });
    });
  }

  load();
})();

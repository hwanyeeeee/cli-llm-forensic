/* view.js — 포렌식 독립 뷰 페이지(?view=mcp|retention|attestation).
   순수 프레젠테이션: /api/* 불변, 렌더 HTML 빌드는 ForensicViews(forensic-views.js) 1벌만 호출(DRY).
   엔진/API가 단일 진실원천 — 여기서 재집계/재판정 금지. 외부 전송 0, 이미 마스킹된 로컬 데이터만.
   반응형: CSS가 width 따라 자연 reflow — JS 리사이즈 핸들러 불요.
   Issue-1: 자동 유출패널(leaks)은 제거 — 동일내용 탐지는 대시보드 파일목록의 온디맨드 해시검색으로 이전. */
(function () {
  "use strict";

  var key = new URLSearchParams(location.search).get("view");
  var TITLES = {
    mcp: "MCP 연결 흔적 · 설정 vs 실사용",
    retention: "tmp 보존기간 · 만료 잔여",
    attestation: "읽기전용 증명 · Chain of Custody"
  };

  document.title = TITLES[key] || "포렌식 뷰";
  document.getElementById("vhead").textContent = TITLES[key] || key;

  var vbody = document.getElementById("vbody");

  async function load() {
    if (!TITLES[key]) { vbody.innerHTML = '<div class="empty">알 수 없는 뷰</div>'; return; }
    var endpoint = key === "mcp" ? "/api/mcp"
      : key === "attestation" ? "/api/attestation"
      : "/api/artifacts";
    var d;
    try {
      var res = await fetch(endpoint);
      d = await res.json();
    } catch (_) {
      vbody.innerHTML = '<div class="empty">불러오기 실패</div>';
      return;
    }
    var FV = window.ForensicViews;
    if (key === "mcp") FV.renderMcp(vbody, d);
    else if (key === "retention") FV.renderRetention(vbody, d.retention, FV.leakTmpPaths(d));
    else if (key === "attestation") FV.renderAttestation(vbody, d);
  }

  load();
})();

/* forensic-views.js — 포렌식 렌더 HTML 빌드 로직 단일 진실원천(DRY).
   app.js·view.js가 호출만 한다(복붙 금지). 외부 전역 의존 없음(self-contained).
   엔진/API가 값의 단일 진실원천 — 여기서는 재집계/재판정 없이 값 그대로 그린다.
   뱃지(setFbadge)는 호출측(app.js) 책임 — 이 모듈은 본문 HTML만 만든다.
   보안: 모든 동적 문자열은 내부 esc()로 이스케이프. */
(function () {
  "use strict";

  // app.js esc와 동일 구현(self-contained 복제는 의도 — 외부 전역 의존 0).
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* 유출·복사 의심: 동일 내용 해시 클러스터. el에 본문 세팅(뱃지 제외). */
  function renderLeaks(el, d) {
    if (!el) return;
    var cl = (d && d.hashes) || [];
    if (!cl.length) { el.innerHTML = '<div class="empty">동일 내용 복제 없음</div>'; return; }
    el.innerHTML = cl.map(function (c) {
      var sha = esc(String(c.sha256 || "").slice(0, 12));
      // 강조: secret=빨강, leak_suspect=보라(in_tmp 동반 시 강한 유출 의심). 엔진 플래그 그대로 표시.
      var flags = [];
      if (c.secret)       flags.push('<span class="lflag secret">secret</span>');
      if (c.in_tmp)       flags.push('<span class="lflag tmp">tmp 사본</span>');
      if (c.leak_suspect) flags.push('<span class="lflag leak">유출 의심</span>');
      var cls = c.secret ? 'leakrow secret' : (c.leak_suspect ? 'leakrow leak' : 'leakrow');
      var paths = (c.paths || []).map(function (p) {
        var tag = p.in_tmp ? '<span class="lpt tmp">tmp</span>' : (p.referenced ? '<span class="lpt ref">참조됨</span>' : '<span class="lpt">미참조</span>');
        var src = (p.source && p.source.file != null) ? '<span class="src">' + esc(p.source.file) + ':' + esc(p.source.line) + '</span>' : '';
        return '<div class="lpath">' + tag + '<span class="lpp">' + esc(p.path) + '</span>' + src + '</div>';
      }).join("");
      var reason = c.reason ? '<div class="lreason">' + esc(c.reason) + '</div>' : '';
      return '<div class="' + cls + '">' +
        '<div class="lhead"><span class="lsha">' + sha + '…</span>' +
        '<span class="lct">' + esc(c.count) + '곳 · ' + esc(c.size) + 'B</span>' + flags.join("") + '</div>' +
        reason + paths + '</div>';
    }).join("");
  }

  /* 주체 왜곡 보정: distortion 우선 정렬(엔진 값 기준 정렬만). el에 본문 세팅(뱃지 제외). */
  function renderAttrib(el, d) {
    if (!el) return;
    var at = (((d && d.attribution) || []).slice())
      .sort(function (a, b) { return (b.distortion ? 1 : 0) - (a.distortion ? 1 : 0); });
    if (!at.length) { el.innerHTML = '<div class="empty">주체 왜곡 정황 없음</div>'; return; }
    el.innerHTML = at.map(function (r) {
      var actor = r.transcript_actor;
      var who = actor === "agent" ? '<span class="who agent">B 에이전트</span>' : '<span class="who user">A 사용자</span>';
      var src = (r.source && r.source.file != null) ? '<span class="src">' + esc(r.source.file) + ':' + esc(r.source.line) + '</span>' : '';
      var cls = r.distortion ? 'attribrow distort' : 'attribrow';
      var note = r.note ? '<div class="anote">' + esc(r.note) + '</div>' : '';
      return '<div class="' + cls + '">' +
        '<div class="apath">' + esc(r.path) + '</div>' +
        note +
        '<div class="ameta">' + who + ' <span class="ats">FS ' + esc(r.fs_mtime || "-") + ' ↔ transcript ' + esc(r.transcript_ts || "-") + '</span></div>' +
        src + '</div>';
    }).join("");
  }

  /* MCP 연결 흔적(설정 vs 실사용). d를 인자로 받음(fetch 안 함). el에 본문 세팅(뱃지 제외). */
  function renderMcp(el, d) {
    if (!el) return;
    if (!d) { el.innerHTML = '<span class="muted">불러오기 실패</span>'; return; }
    var html = "";
    if (d.used_unconfigured && d.used_unconfigured.length) {
      html += '<div class="warn">⚠ 설정 없이 사용된 서버: ' + d.used_unconfigured.map(esc).join(", ") + '</div>';
    }
    html += '<div class="sub">설정된 서버 ' + (d.configs ? d.configs.length : 0) + '개</div>';
    html += (d.configs || []).map(function (c) {
      return '<div class="row"><b>' + esc(c.server) + '</b> <span class="muted">(' + esc(c.scope) + ')</span> ' + esc(c.command || "") +
        (c.env_keys && c.env_keys.length ? ' <span class="muted">env: ' + c.env_keys.map(esc).join(",") + '</span>' : "") +
        '</div>';
    }).join("");
    html += '<div class="sub">실호출 ' + (d.usage ? d.usage.length : 0) + '종</div>';
    html += (d.usage || []).map(function (u) {
      return '<div class="row">' + esc(u.server) + '__' + esc(u.tool) + ' <span class="muted">×' + esc(u.count) + '</span></div>';
    }).join("");
    if (d.configured_unused && d.configured_unused.length) {
      html += '<div class="sub muted">설정O 미사용: ' + d.configured_unused.map(esc).join(", ") + '</div>';
    }
    el.innerHTML = html || '<span class="muted">MCP 흔적 없음</span>';
  }

  /* tmp 보존기간: 만료임박(≤7d) 경고 강조. el에 본문 세팅(뱃지 제외). */
  function renderRetention(el, rows) {
    if (!el) return;
    if (!rows || !rows.length) { el.innerHTML = '<span class="muted">tmp 잔존 없음</span>'; return; }
    el.innerHTML = rows.map(function (r) {
      var soon = r.expires_in_days > 0 && r.expires_in_days <= 7;
      return '<div class="row' + (soon ? " warn" : "") + '">' + esc(r.path) + ' ' +
        '<span class="muted">나이 ' + esc(r.age_days) + 'd · 만료 ' + (r.expires_in_days > 0 ? esc(r.expires_in_days) + 'd 후' : '경과') + '</span></div>';
    }).join("");
  }

  window.ForensicViews = { esc: esc, renderLeaks: renderLeaks, renderAttrib: renderAttrib, renderMcp: renderMcp, renderRetention: renderRetention };
})();

/* forensic-views.js — 포렌식 렌더 HTML 빌드 로직 단일 진실원천(DRY).
   app.js·view.js가 호출만 한다(복붙 금지). 외부 전역 의존 없음(self-contained).
   엔진/API가 값의 단일 진실원천 — 여기서는 재판정 없이 값 그대로 그린다.
   (표시용 server별 그룹 집계는 엔진 per-tool count 단순 합산만 — 재판정 아님.)
   뱃지(setFbadge)는 호출측(app.js) 책임 — 이 모듈은 본문 HTML만 만든다.
   접이식은 네이티브 <details><summary> — JS 이벤트 바인딩 불필요(view/modal 동일 동작).
   보안: 모든 동적 문자열은 내부 esc()로 이스케이프. 해시검색은 hex만 전송(파일내용 전송 없음). */
(function () {
  "use strict";

  // app.js esc와 동일 구현(self-contained 복제는 의도 — 외부 전역 의존 0).
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* 한 해시 클러스터 1개 행 마크업. leak_suspect면 강조. (기존 마크업 재사용) */
  function leakRowHTML(c) {
    var sha = esc(String(c.sha256 || "").slice(0, 12));
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
  }

  /* 유출·복사 의심: 동일 내용 해시 클러스터.
     leak_suspect 먼저/강조. tmp_only(설치/캐시 중복)는 노이즈로 접이식 분리. */
  function renderLeaks(el, d) {
    if (!el) return;
    var cl = (d && d.hashes) || [];
    var main = cl.filter(function (c) { return !c.tmp_only; });
    var noise = cl.filter(function (c) { return c.tmp_only; });

    var html = "";
    if (main.length) {
      html += main.map(leakRowHTML).join("");
    } else {
      html += '<div class="empty">동일 내용 복제 없음(유출 정황)</div>';
    }
    if (noise.length) {
      html += '<details class="leak-noise"><summary>tmp 내부 중복 ' + noise.length +
        '건 (설치/캐시 — 유출 아님)</summary>' + noise.map(leakRowHTML).join("") + '</details>';
    }
    el.innerHTML = html;
  }

  /* [#2b] 동일 해시 tmp 검색 박스 HTML(DRY 공유). id는 호출측이 querySelector로 잡는다. */
  function hashSearchBoxHTML() {
    return '<div class="hsbox">' +
      '<input type="file" id="hsfile">' +
      '<button id="hsbtn">동일 해시 tmp 검색</button>' +
      '<div id="hsresult"></div></div>';
  }

  /* [#2b] 브라우저 로컬 SHA-256 hex 계산. 파일 내용은 네트워크로 안 나감(hex만). */
  function sha256Hex(file) {
    return file.arrayBuffer().then(function (buf) {
      return crypto.subtle.digest("SHA-256", buf);
    }).then(function (digest) {
      var bytes = new Uint8Array(digest);
      var hex = "";
      for (var i = 0; i < bytes.length; i++) {
        hex += bytes[i].toString(16).padStart(2, "0");
      }
      return hex;
    });
  }

  /* [#2b] /api/hash-search 결과 matches[] 렌더. 정렬은 서버가 함(값 그대로). */
  function renderHashMatches(el, matches) {
    if (!el) return;
    if (!matches || !matches.length) {
      el.innerHTML = '<div class="empty">동일 내용 tmp 사본 없음</div>';
      return;
    }
    el.innerHTML = matches.map(function (m) {
      return '<div class="row"><span class="lpp">' + esc(m.path) + '</span> ' +
        '<span class="muted">' + esc(m.size) + 'B · ' + esc(m.mtime) + '</span></div>';
    }).join("");
  }

  /* [#1] server별 총호출 도넛 SVG. app.js renderDonut의 stroke-dasharray arc 패턴 동일.
     items=[{label,count}]. 자체 팔레트. */
  var DONUT_PALETTE = ["#0284c7", "#7c3aed", "#16a34a", "#d97706", "#dc2626",
    "#0891b2", "#9333ea", "#65a30d", "#db2777", "#2563eb"];

  function donutSVG(items) {
    var total = (items || []).reduce(function (s, it) { return s + (it.count || 0); }, 0);
    var cx = 60, cy = 60, r = 44, sw = 18, C = 2 * Math.PI * r;
    if (!total) {
      return '<svg viewBox="0 0 120 120" class="fdonut"><circle cx="' + cx + '" cy="' + cy + '" r="' + r +
        '" fill="none" stroke="#eceff3" stroke-width="' + sw + '"/></svg>';
    }
    var off = 0, segs = "";
    items.forEach(function (it, i) {
      var len = (it.count || 0) / total * C;
      var col = DONUT_PALETTE[i % DONUT_PALETTE.length];
      segs += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + col +
        '" stroke-width="' + sw + '" stroke-dasharray="' + len + ' ' + (C - len) +
        '" stroke-dashoffset="' + (-off) + '" transform="rotate(-90 ' + cx + ' ' + cy + ')">' +
        '<title>' + esc(it.label) + ': ' + esc(it.count) + '</title></circle>';
      off += len;
    });
    return '<svg viewBox="0 0 120 120" class="fdonut">' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="#eceff3" stroke-width="' + sw + '"/>' +
      segs +
      '<text x="60" y="56" text-anchor="middle" fill="#1b2433" font-size="20" font-weight="800" font-family="ui-monospace">' + total + '</text>' +
      '<text x="60" y="72" text-anchor="middle" fill="#5c6675" font-size="9">총 호출</text></svg>';
  }

  /* [#1] MCP 연결 흔적: server별 그룹 + 도넛 + accordion + #5 중립화.
     d를 인자로 받음(fetch 안 함). el에 본문 세팅(뱃지 제외). */
  function renderMcp(el, d) {
    if (!el) return;
    if (!d) { el.innerHTML = '<span class="muted">불러오기 실패</span>'; return; }

    // server별 그룹 집계(표시용 — 엔진 per-tool count 단순 합산만). 결정성: 정렬.
    var byServer = {};
    (d.usage || []).forEach(function (u) {
      var s = u.server;
      if (!byServer[s]) byServer[s] = { server: s, total: 0, tools: [] };
      byServer[s].total += (u.count || 0);
      byServer[s].tools.push({ tool: u.tool, count: u.count || 0 });
    });
    var servers = Object.keys(byServer).sort().map(function (s) {
      var g = byServer[s];
      g.tools.sort(function (a, b) {
        return (b.count - a.count) || (a.tool < b.tool ? -1 : a.tool > b.tool ? 1 : 0);
      });
      return g;
    });
    // 도넛은 total 내림차순(동률 server명 오름차순) — 결정성.
    var donutItems = servers.slice().sort(function (a, b) {
      return (b.total - a.total) || (a.server < b.server ? -1 : a.server > b.server ? 1 : 0);
    }).map(function (g) { return { label: g.server, count: g.total }; });

    var html = '<div class="sub">MCP 외부연결 사용현황 (정보)</div>';

    if (servers.length) {
      var legend = donutItems.map(function (it, i) {
        var col = DONUT_PALETTE[i % DONUT_PALETTE.length];
        return '<div class="fleg"><span class="fsw" style="background:' + col + '"></span>' +
          '<span class="fln">' + esc(it.label) + '</span><span class="flc">×' + esc(it.count) + '</span></div>';
      }).join("");
      html += '<div class="fdonutwrap">' + donutSVG(donutItems) + '<div class="fdleg">' + legend + '</div></div>';

      html += servers.map(function (g) {
        var tools = g.tools.map(function (t) {
          return '<div class="row">' + esc(t.tool) + ' <span class="muted">×' + esc(t.count) + '</span></div>';
        }).join("");
        return '<details class="mcpgrp"><summary><b>' + esc(g.server) + '</b> ' +
          '<span class="muted">×' + esc(g.total) + '</span></summary>' + tools + '</details>';
      }).join("");
    } else {
      html += '<div class="empty">MCP 실호출 없음</div>';
    }

    // 설정 섹션(#5 중립화) — 경보 제거. used_unconfigured는 중립 표기만.
    html += '<div class="sub">설정된 서버 ' + (d.configs ? d.configs.length : 0) + '개</div>';
    html += (d.configs || []).map(function (c) {
      return '<div class="row"><b>' + esc(c.server) + '</b> <span class="muted">(' + esc(c.scope) + ')</span> ' + esc(c.command || "") +
        (c.env_keys && c.env_keys.length ? ' <span class="muted">env: ' + c.env_keys.map(esc).join(",") + '</span>' : "") +
        '</div>';
    }).join("");
    if (d.configured_unused && d.configured_unused.length) {
      html += '<div class="sub muted">설정O 미사용: ' + d.configured_unused.map(esc).join(", ") + '</div>';
    }
    if (d.used_unconfigured && d.used_unconfigured.length) {
      html += '<div class="sub muted">설정 출처 미확인: ' + d.used_unconfigured.map(esc).join(", ") + '</div>';
    }
    el.innerHTML = html;
  }

  /* [#3] 주체 귀속 요약: 에이전트(B) 작성 파일만 간결 표시.
     owner/distortion/신뢰불가/FS↔transcript 표현 전부 제거. el에 본문 세팅(뱃지 제외). */
  function renderAttrib(el, d) {
    if (!el) return;
    var agentWrites = ((d && d.attribution) || []).filter(function (r) {
      return r.transcript_actor === "agent" && r.transcript_action === "write";
    });
    if (!agentWrites.length) {
      el.innerHTML = '<div class="empty">에이전트 작성 파일 없음</div>';
      return;
    }
    var html = '<div class="sub">에이전트(B)가 작성한 파일 ' + agentWrites.length + '개</div>';
    html += agentWrites.slice(0, 12).map(function (r) {
      return '<div class="apath">' + esc(r.path) + '</div>';
    }).join("");
    el.innerHTML = html;
  }

  /* 파일 1행(나이/만료, 임박 ≤7d는 warn 강조) — DRY. */
  function retentionRowHTML(r) {
    var soon = r.expires_in_days > 0 && r.expires_in_days <= 7;
    return '<div class="row' + (soon ? " warn" : "") + '">' + esc(r.path) + ' ' +
      '<span class="muted">나이 ' + esc(r.age_days) + 'd · 만료 ' +
      (r.expires_in_days > 0 ? esc(r.expires_in_days) + 'd 후' : '경과') + '</span></div>';
  }

  /* path의 부모 디렉터리(마지막 구분자 앞). 구분자 없으면 "." */
  function parentDir(p) {
    var s = String(p);
    var i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
    return i >= 0 ? s.slice(0, i) : ".";
  }

  /* [#4] tmp 보존기간: 디렉터리 그룹 + 요약. 전수 보존(모든 행 그룹 안). */
  function renderRetention(el, rows) {
    if (!el) return;
    if (!rows || !rows.length) { el.innerHTML = '<span class="muted">tmp 잔존 없음</span>'; return; }

    var soonCount = rows.filter(function (r) {
      return r.expires_in_days > 0 && r.expires_in_days <= 7;
    }).length;

    // 부모 디렉터리별 그룹.
    var groups = {};
    rows.forEach(function (r) {
      var dir = parentDir(r.path);
      if (!groups[dir]) groups[dir] = [];
      groups[dir].push(r);
    });

    var html = '<div class="sub">총 tmp ' + rows.length + '개 · 만료임박(≤7d) ' + soonCount + '개</div>';

    html += Object.keys(groups).sort().map(function (dir) {
      var items = groups[dir];
      // 그룹 최단만료(만료경과 무시, >0 중 최소). 임박 파일 존재 여부.
      var minExp = null, hasSoon = false;
      items.forEach(function (r) {
        if (r.expires_in_days > 0) {
          if (minExp === null || r.expires_in_days < minExp) minExp = r.expires_in_days;
          if (r.expires_in_days <= 7) hasSoon = true;
        }
      });
      var minTxt = minExp === null ? "모두 경과" : "최단만료 " + minExp + "d";
      var sumCls = hasSoon ? ' class="warn"' : "";
      var body = items.map(retentionRowHTML).join("");
      return '<details class="rgrp"><summary' + sumCls + '>' + esc(dir) + ' (' + items.length + '개 · ' + minTxt + ')</summary>' +
        body + '</details>';
    }).join("");

    el.innerHTML = html;
  }

  window.ForensicViews = {
    esc: esc,
    renderLeaks: renderLeaks,
    renderAttrib: renderAttrib,
    renderMcp: renderMcp,
    renderRetention: renderRetention,
    hashSearchBoxHTML: hashSearchBoxHTML,
    sha256Hex: sha256Hex,
    renderHashMatches: renderHashMatches,
    donutSVG: donutSVG
  };
})();

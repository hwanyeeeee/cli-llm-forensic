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

  /* 한 해시 클러스터 = 네이티브 접이식 <details>. summary=헤더(해시12…·N곳·크기·flags·reason),
     본문=경로 목록(기존 lpath 마크업). 기본 접힘(open 없음). leak_suspect면 강조. */
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
    var reason = c.reason ? '<span class="lreason">' + esc(c.reason) + '</span>' : '';
    return '<details class="' + cls + '"><summary class="lhead">' +
      '<span class="lsha">' + sha + '…</span>' +
      '<span class="lct">' + esc(c.count) + '곳 · ' + esc(c.size) + 'B</span>' +
      flags.join("") + reason + '</summary>' + paths + '</details>';
  }

  /* 유출·복사 의심: 동일 내용 해시 클러스터.
     (1) 최상단 해시검색 박스, (2) leak_suspect 우선 정렬한 main(!tmp_only),
     (3) tmp_only 노이즈 접이식. 각 클러스터는 접이식 헤더만 보이고 클릭 시 경로 펼침.
     렌더 직후 el-scoped 자체 wiring(DRY — app.js/view.js는 호출만). */
  function renderLeaks(el, d) {
    if (!el) return;
    var cl = (d && d.hashes) || [];
    var main = cl.filter(function (c) { return !c.tmp_only; });
    var noise = cl.filter(function (c) { return c.tmp_only; });

    // leak_suspect 먼저(결정성: 엔진 순서 안정 유지 — leak_suspect만 앞으로, 재집계/재판정 아님).
    main = main.slice().sort(function (a, b) {
      return (b.leak_suspect ? 1 : 0) - (a.leak_suspect ? 1 : 0);
    });

    var html = hashSearchBoxHTML();   // (1) 해시검색 박스 최상단(빈 main이어도 유지)
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
    wireHashSearch(el);   // 자체 wiring(DRY)
  }

  /* [#2b] 해시검색 박스 자체 wiring. el-scoped querySelector(전역 getElementById 회피).
     파일 → 브라우저 로컬 SHA-256 hex → /api/hash-search?sha=hex(파일내용 전송 0). */
  function wireHashSearch(el) {
    if (!el) return;
    var btn = el.querySelector("#hsbtn");
    var fin = el.querySelector("#hsfile");
    var res = el.querySelector("#hsresult");
    if (!btn || !fin || !res) return;
    btn.addEventListener("click", function () {
      var file = fin.files && fin.files[0];
      if (!file) { res.innerHTML = '<div class="empty">파일을 선택하세요</div>'; return; }
      res.innerHTML = '<div class="empty">해시 계산 중…</div>';
      sha256Hex(file)                                          // 브라우저 로컬 SHA-256(hex만)
        .then(function (hex) {
          return fetch("/api/hash-search?sha=" + encodeURIComponent(hex)); // hex만 전송
        })
        .then(function (r) { return r.json(); })
        .then(function (j) { renderHashMatches(res, (j && j.matches) || []); })
        .catch(function () { res.innerHTML = '<div class="empty">검색 실패</div>'; });
    });
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

  /* 파일 1행. "만료까지 N일 남음"(N=round(expires_in_days); ≤0이면 "만료 경과").
     "수정 후 X일" 표기(age_days 값 그대로, 라벨만). 임박(≤7d) warn 강조.
     증거 관련(leakSet 포함) 행은 evtag 표식 + warn 우선 표시. 값은 엔진 그대로(표시용 round만). */
  function retentionRowHTML(r, leakSet) {
    var ed = r.expires_in_days;
    var soon = ed > 0 && ed <= 7;
    var exp = ed > 0 ? '만료까지 ' + Math.round(ed) + '일 남음' : '만료 경과';
    var isEv = !!(leakSet && leakSet.has(r.path));
    var ev = isEv ? '<span class="evtag">증거 관련</span>' : '';
    var cls = 'row' + (isEv ? ' ev' : '') + (soon ? ' warn' : '');
    return '<div class="' + cls + '">' + ev + esc(r.path) + ' ' +
      '<span class="muted">수정 후 ' + esc(r.age_days) + '일 · ' + exp + '</span></div>';
  }

  /* leak_suspect 클러스터의 tmp 경로 Set(증거 관련 tmp 파일).
     d.hashes 중 leak_suspect인 클러스터의 paths에서 p.in_tmp인 p.path만 수집.
     엔진 값 그대로 — JS 재판정 아님. renderRetention의 leakSet 인자로 사용(DRY). */
  function leakTmpPaths(d) {
    var set = new Set();
    ((d && d.hashes) || []).forEach(function (c) {
      if (!c.leak_suspect) return;
      (c.paths || []).forEach(function (p) {
        if (p && p.in_tmp && p.path != null) set.add(p.path);
      });
    });
    return set;
  }

  /* 상위 롤업 키: 경로 구분자 split 후 빈 토큰 제거, 앞 3단계만(tmp 루트 기준 1~2단계).
     그룹 수 대폭 축소 — 하위경로·파일은 그룹 안에 전수 포함(완전성). */
  function rollupKey(path) {
    return String(path).split(/[\/\\]+/).filter(Boolean).slice(0, 3).join("/");
  }

  /* [#4] tmp 보존기간: 상위 롤업 그룹 + 요약 + 증거 우선.
     leakSet optional(없으면 증거표식 생략). 전수 보존(모든 행 그룹 안 — 분류·표시만 변경).
     정렬: 그룹 = (증거포함 desc, 임박 desc, 최소잔여 asc, dir asc);
           그룹내 행 = (증거 desc, expires_in_days asc). 결정성 보장. */
  function renderRetention(el, rows, leakSet) {
    if (!el) return;
    if (!rows || !rows.length) { el.innerHTML = '<span class="muted">tmp 잔존 없음</span>'; return; }
    var hasLeak = !!(leakSet && leakSet.size);

    var soonCount = rows.filter(function (r) {
      return r.expires_in_days > 0 && r.expires_in_days <= 7;
    }).length;

    function isEv(r) { return hasLeak && leakSet.has(r.path); }

    // 상위 롤업별 그룹.
    var groups = {};
    rows.forEach(function (r) {
      var dir = rollupKey(r.path);
      if (!groups[dir]) groups[dir] = [];
      groups[dir].push(r);
    });

    var html = '<div class="rnote">tmp 파일은 마지막 수정 후 약 30일이면 자동 삭제됩니다. ' +
      '‘만료까지 N일’=해당 파일이 사라지기까지 남은 기간(증거 보존 시한).</div>';
    html += '<div class="sub">총 tmp ' + rows.length + '개 · 만료임박(≤7d) ' + soonCount + '개' +
      (soonCount === 0 ? ' · 현재 소실 위험 없음' : '') + '</div>';

    // 그룹 메타 계산.
    var metas = Object.keys(groups).map(function (dir) {
      var items = groups[dir];
      var minExp = null, hasSoon = false, hasEv = false;
      items.forEach(function (r) {
        if (isEv(r)) hasEv = true;
        if (r.expires_in_days > 0) {
          if (minExp === null || r.expires_in_days < minExp) minExp = r.expires_in_days;
          if (r.expires_in_days <= 7) hasSoon = true;
        }
      });
      // 그룹내 행 정렬: 증거 desc, expires_in_days asc.
      var sorted = items.slice().sort(function (a, b) {
        var ea = isEv(a) ? 1 : 0, eb = isEv(b) ? 1 : 0;
        if (eb !== ea) return eb - ea;
        return a.expires_in_days - b.expires_in_days;
      });
      return { dir: dir, items: sorted, minExp: minExp, hasSoon: hasSoon, hasEv: hasEv };
    });

    // 그룹 정렬: 증거포함 desc, 임박 desc, 최소잔여 asc(null=경과는 맨 뒤), dir asc.
    metas.sort(function (a, b) {
      var ev = (b.hasEv ? 1 : 0) - (a.hasEv ? 1 : 0);
      if (ev) return ev;
      var sn = (b.hasSoon ? 1 : 0) - (a.hasSoon ? 1 : 0);
      if (sn) return sn;
      var am = a.minExp === null ? Infinity : a.minExp;
      var bm = b.minExp === null ? Infinity : b.minExp;
      if (am !== bm) return am - bm;
      return a.dir < b.dir ? -1 : a.dir > b.dir ? 1 : 0;
    });

    html += metas.map(function (g) {
      var minTxt = g.minExp === null ? "모두 만료 경과" : "만료까지 " + Math.round(g.minExp) + "일 남음";
      var sumCls = (g.hasEv ? " ev" : "") + (g.hasSoon ? " warn" : "");
      var evtag = g.hasEv ? '<span class="evtag">증거 관련</span>' : '';
      var body = g.items.map(function (r) { return retentionRowHTML(r, leakSet); }).join("");
      return '<details class="rgrp"><summary class="rsum' + sumCls + '">' + evtag + esc(g.dir) +
        ' (' + g.items.length + '개 · ' + minTxt + ')</summary>' + body + '</details>';
    }).join("");

    el.innerHTML = html;
  }

  window.ForensicViews = {
    esc: esc,
    renderLeaks: renderLeaks,
    renderMcp: renderMcp,
    renderRetention: renderRetention,
    leakTmpPaths: leakTmpPaths,
    hashSearchBoxHTML: hashSearchBoxHTML,
    sha256Hex: sha256Hex,
    renderHashMatches: renderHashMatches,
    donutSVG: donutSVG
  };
})();

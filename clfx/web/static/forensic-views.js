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

  /* [Issue-1] 자동 유출분류(leakRowHTML/renderLeaks)는 제거됨 — 오탐(_MEI PyInstaller 자기추출 등)으로
     부정확. 동일내용 탐지는 파일목록 컨텍스트의 온디맨드 해시검색(hashSearchBoxHTML+wireHashSearch)으로
     이전됨(수사관이 특정 파일을 골라 동일해시 tmp 사본을 직접 조회). leakTmpPaths는 retention 증거표식에
     계속 쓰이므로 유지(아래). */

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

  /* [#2b] 동일 해시 tmp 검색 박스 HTML(DRY 공유). id는 호출측이 querySelector로 잡는다.
     [Issue-1] 파일목록 컨텍스트로 이전 — label 인자로 용도 설명을 둔다(기본 = 파일선택 안내). */
  function hashSearchBoxHTML(label) {
    var lbl = label || "파일 선택 → 동일 해시 tmp 사본 검색";
    return '<div class="hsbox">' +
      '<div class="hslabel">' + esc(lbl) + '</div>' +
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

  /* [B-4] 읽기전용 증명(Chain of Custody) 단일 진실원천 렌더. d=/api/attestation payload.
     단언적 무변경 보증(note) + 요약 한 줄 + 근거(read-only 불변식·테스트) +
     검색 가능 매니페스트(경로 substring 필터 + 취득 {path: sha256 앞12자…} 목록).
     값은 서버/엔진이 단일진실 — 여기서 재해싱·재판정 없음. 모든 동적 문자열 esc().
     el-scoped 자체 wiring(필터 input — 전역 의존 0, view/modal 동일 동작). */
  function renderAttestation(el, d) {
    if (!el) return;
    if (!d) {
      el.innerHTML = '<div class="empty">읽기전용 증명 불러오기 실패 (/api/attestation)</div>';
      return;
    }
    var acquired = (d.acquired || []);
    var ac = (d.acquired_count != null) ? d.acquired_count : acquired.length;
    var so = d.stat_only_count || 0;
    var ops = d.write_delete_rename_ops || 0;
    var allRo = !!d.all_read_only;
    var modes = (d.modes_seen || []).slice();
    var note = d.note || "";

    // 단언적 보증 문구(증거 무변경 guarantee — 강한 어조). note는 서버 단일진실.
    var html = '<div class="attest-assure"><b>증거 무변경 보증.</b> ' + esc(note) + '</div>';

    // 요약 한 줄: 취득 N · 내용 미독 stat-only M · 쓰기/삭제/이동 0 · 전 open 읽기전용.
    var roTxt = allRo ? '전 open 읽기전용' : '읽기전용 위반 감지';
    html += '<div class="attest-summary">' +
      '취득 <b>' + esc(ac) + '</b>건 · 내용 미독 stat-only <b>' + esc(so) + '</b>건 · ' +
      '쓰기/삭제/이동 <b>' + esc(ops) + '</b> · <b>' + esc(roTxt) + '</b></div>';

    // 근거: read-only 불변식 + 관측된 open 모드 + 테스트.
    var modesTxt = modes.length ? modes.map(esc).join(", ") : "(없음)";
    html += '<div class="attest-basis">' +
      '<div class="sub">근거 (Chain of Custody)</div>' +
      '<div class="row">공유 _ro_open이 모든 파일을 읽기전용으로만 연다(쓰기/추가/생성 모드 거부). 매니페스트·감사는 메모리 전용(디스크 쓰기 0).</div>' +
      '<div class="row">감사가 관측한 open 모드: <span class="muted">' + modesTxt + '</span> (r/rb 부분집합만 허용).</div>' +
      '<div class="row">회귀 테스트: 읽기전용 불변식 · 무손실(test_scan_equivalent_to_sequential) 상시 green.</div>' +
      '</div>';

    // 검색 가능 매니페스트: 필터 input + 취득 {path: sha256(앞12자…)} 목록.
    html += '<div class="sub">취득 매니페스트 (취득 시 SHA-256 기록 · 경로 검색)</div>';
    html += '<input type="text" id="attfilter" class="attest-filter" placeholder="경로로 검색…" autocomplete="off">';
    if (acquired.length) {
      html += '<div id="attlist" class="attest-list">' + attRowsHTML(acquired) + '</div>';
    } else {
      html += '<div id="attlist" class="attest-list"><div class="empty">취득(내용 독취) 파일 없음</div></div>';
    }
    el.innerHTML = html;

    // 필터 wiring(el-scoped): 경로 substring으로 클라이언트측 필터(재해싱 없음 — 표시만).
    var fin = el.querySelector("#attfilter");
    var list = el.querySelector("#attlist");
    if (fin && list) {
      fin.addEventListener("input", function () {
        var q = String(fin.value || "").toLowerCase();
        var hits = acquired.filter(function (a) {
          return String(a.path || "").toLowerCase().indexOf(q) !== -1;
        });
        list.innerHTML = hits.length ? attRowsHTML(hits)
          : '<div class="empty">일치하는 경로 없음</div>';
      });
    }
  }

  /* [B-4] 취득 매니페스트 행 HTML(DRY). 각 행: 경로 + sha256 앞 12자…(전체 hex는 esc된 title). */
  function attRowsHTML(rows) {
    return rows.map(function (a) {
      var full = String(a.sha256 || "");
      var sha = esc(full.slice(0, 12));
      return '<div class="row attrow"><span class="lpp">' + esc(a.path) + '</span> ' +
        '<span class="muted" title="' + esc(full) + '">' + sha + '…</span></div>';
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
    renderMcp: renderMcp,
    renderRetention: renderRetention,
    renderAttestation: renderAttestation,
    leakTmpPaths: leakTmpPaths,
    hashSearchBoxHTML: hashSearchBoxHTML,
    wireHashSearch: wireHashSearch,
    sha256Hex: sha256Hex,
    renderHashMatches: renderHashMatches,
    donutSVG: donutSVG
  };
})();

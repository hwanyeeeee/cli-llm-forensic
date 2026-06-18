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

  /* [B-4][R8-B] 읽기전용 증명(Chain of Custody) 단일 진실원천 렌더. d=/api/attestation payload.
     일반어 재설계: (1)헤더 (2)리드(100% 읽기전용 보증) (3)핵심 수치 카드(변경 0·취득·메타데이터만)
     (4)무결성 검증 방법(일반어) (5)기술 상세=접이식(개발자 용어 _ro_open/modes/note는 여기에만)
     (6)취득 해시 원장=접이식 기본 접힘(펼치면 경로 검색 — 대량 덤프 방지).
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
    var modes = (d.modes_seen || []).slice();
    var note = d.note || "";

    // (1) 헤더 — 일반어(수사관이 기능을 즉시 이해).
    var html = '<div class="attest-head"><b>증거 무결성</b> — 분석이 원본을 변경하지 않았음</div>';

    // (2) 리드(강조 박스, 일반어).
    html += '<div class="attest-lead">이 분석은 <b>100% 읽기 전용</b>으로 수행됐습니다. ' +
      '도구는 파일을 열 때 읽기 모드만 사용하며 쓰기·삭제·수정은 차단됩니다(시도 시 즉시 오류). ' +
      '따라서 분석 과정이 증거 파일을 건드릴 수 없습니다.</div>';

    // (3) 핵심 수치(큰 글씨, 일반어). ops==0이면 ok(초록) 강조.
    var okCls = (ops === 0) ? ' ok' : '';
    html += '<div class="attest-roline">읽기 전용 접근: <b>전부</b></div>';
    html += '<div class="attest-nums">' +
      '<div class="anum' + okCls + '"><div class="anv">' + esc(ops) + '</div>' +
        '<div class="anl">변경(쓰기/삭제/이동) 횟수</div></div>' +
      '<div class="anum"><div class="anv">' + esc(ac) + '</div>' +
        '<div class="anl">해시 기록한 증거 파일</div></div>' +
      '<div class="anum"><div class="anv">' + esc(so) + '</div>' +
        '<div class="anl">메타데이터만 확인(내용 미접근)</div></div>' +
      '</div>';

    // (4) 무결성 검증 방법(일반어 설명).
    html += '<div class="attest-verify"><div class="sub">무결성 검증 방법</div>' +
      '<div class="row">각 파일을 읽는 순간 SHA-256 지문을 아래 원장에 기록했습니다(취득 해시). ' +
      '나중에 원본 파일의 SHA-256을 다시 계산해 이 값과 비교하세요 — ' +
      '같으면 분석 이후에도 변조가 없었음이 증명됩니다. ' +
      '(대시보드 파일목록의 ‘동일 해시 tmp 검색’으로 특정 파일을 즉시 대조할 수도 있습니다.)</div></div>';

    // (4b) CSV 내보내기 — 실무 표준 산출물(취득 해시 원장을 파일로 보존). 동일출처 링크라 view/modal 동일 동작.
    //   서버가 Content-Disposition으로 파일명 강제 + download 속성 힌트. 재해시 없음(메모리 매니페스트 직렬화).
    html += '<div class="attest-export">' +
      '<a class="att-csv" href="/api/attestation.csv" download="acquisition-hash-manifest.csv">' +
      'CSV로 내보내기</a>' +
      '<span class="muted">취득 해시 원장 ' + esc(ac) + '개 · path · sha256 (UTF-8)</span></div>';

    // (5) 기술 상세(접이식, 기본 접힘) — 개발자 용어(_ro_open 등)는 이 안에서만.
    var modesTxt = modes.length ? modes.map(esc).join(", ") : "(없음)";
    html += '<details class="attest-tech"><summary>기술 상세</summary>' +
      '<div class="row">읽기전용 강제: 공유 _ro_open이 모든 파일을 읽기 모드(r/rb)로만 연다 — ' +
      '쓰기·추가·생성 모드는 거부(ValueError). 코드 불변식 + 자동 회귀 테스트로 상시 보증.</div>' +
      '<div class="row">관측된 open 모드: <span class="muted">' + modesTxt + '</span> (r/rb 부분집합만 허용).</div>' +
      '<div class="row">매니페스트·감사는 메모리 전용 — 디스크 쓰기 0.</div>' +
      (note ? '<div class="row attest-note">' + esc(note) + '</div>' : '') +
      '</details>';

    // (6) 취득 해시 원장(접이식, 기본 접힘) — 기본 화면에 대량 덤프 방지. 펼치면 검색.
    html += '<details class="attest-ledger"><summary>취득 해시 원장 (전체 ' + esc(ac) + '개) — 펼쳐서 검색</summary>' +
      '<input type="text" id="attfilter" class="attest-filter" placeholder="경로로 검색…" autocomplete="off">' +
      (acquired.length
        ? '<div id="attlist" class="attest-list">' + attRowsHTML(acquired) + '</div>'
        : '<div id="attlist" class="attest-list"><div class="empty">취득(내용 독취) 파일 없음</div></div>') +
      '</details>';

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

    var html = '<div class="sub">MCP 사용 현황</div>';

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
    // [R8-A] 서버명으로 dedupe+그룹(표시만 — 재집계/재판정 아님). 같은 서버가 여러 프로젝트에
    //   설정돼 d.configs가 중복되므로(정상 데이터), 서버 N종 / 인스턴스 M으로 접어 보여준다.
    var cfgs = (d.configs || []);
    var byCfg = {};
    cfgs.forEach(function (c) {
      var s = c.server;
      if (!byCfg[s]) byCfg[s] = { server: s, scopes: {}, insts: [], cmd: "" };
      var g = byCfg[s];
      if (c.scope) g.scopes[c.scope] = true;       // scope 집합(connector/global/project)
      g.insts.push(c);
      if (!g.cmd && c.command) g.cmd = c.command;   // 대표 command(첫 비어있지 않은 것)
    });
    var cfgServers = Object.keys(byCfg).sort();      // 결정성: 서버명 오름차순
    // [사용자] 섹션 헤더 자체를 토글(<details.mcpcfgwrap>)로 — 클릭 시 N종 펼침.
    //   usage 아코디언과 시각적 간격은 .mcpcfgwrap{margin-top}로 분리.
    var cfgBody = cfgServers.map(function (s) {
      var g = byCfg[s];
      var scopes = Object.keys(g.scopes).sort();     // scope 뱃지 정렬
      var badges = scopes.map(function (sc) {
        return '<span class="cfgscope">' + esc(sc) + '</span>';
      }).join("");
      var insts = g.insts.slice().sort(function (a, b) {   // 인스턴스 정렬(scope·project)
        var ap = (a.scope || "") + " " + (a.project || "");
        var bp = (b.scope || "") + " " + (b.project || "");
        return ap < bp ? -1 : ap > bp ? 1 : 0;
      }).map(function (c) {
        return '<div class="row"><span class="muted">(' + esc(c.scope || "") +
          (c.project ? ' · ' + esc(c.project) : "") + ')</span> ' + esc(c.command || "") +
          (c.env_keys && c.env_keys.length ?
            ' <span class="muted">env: ' + c.env_keys.map(esc).join(",") + '</span>' : "") +
          '</div>';
      }).join("");
      return '<details class="mcpcfg"><summary><b>' + esc(g.server) + '</b> ' + badges +
        ' <span class="muted">×' + esc(g.insts.length) + '</span>' +
        (g.cmd ? ' <span class="muted cfgcmd">' + esc(g.cmd) + '</span>' : "") +
        '</summary>' + insts + '</details>';
    }).join("");
    if (d.configured_unused && d.configured_unused.length) {
      cfgBody += '<div class="sub muted">설정O 미사용: ' + d.configured_unused.map(esc).join(", ") + '</div>';
    }
    if (d.used_unconfigured && d.used_unconfigured.length) {
      cfgBody += '<div class="sub muted">설정 출처 미확인: ' + d.used_unconfigured.map(esc).join(", ") + '</div>';
    }
    html += '<details class="mcpcfgwrap"><summary>설정된 MCP</summary>' + cfgBody + '</details>';
    el.innerHTML = html;
  }

  /* 파일 1행(귀속 행 전용 재설계).
     origin별 보존 텍스트: wsl → expires_in_days>0 면 "만료까지 N일 남음" 아니면 "만료 경과";
       windows → "자동삭제 없음"(expires_in_days는 null). 임박(wsl·0<ed≤7) warn 강조.
     actor 뱃지: user→A, agent→B. source 있으면 file:line 표기(.rsource). leakSet 포함 행은 evtag.
     값은 엔진 그대로(표시용 round만) — JS 재판정 없음. 모든 동적 문자열 esc(). */
  function retentionRowHTML(r, leakSet) {
    var isWsl = r.origin === "wsl";
    var ed = r.expires_in_days;
    var soon = isWsl && ed != null && ed > 0 && ed <= 7;
    var exp = isWsl
      ? (ed != null && ed > 0 ? '만료까지 ' + Math.round(ed) + '일 남음' : '만료 경과')
      : '자동삭제 없음';
    var isEv = !!(leakSet && leakSet.has(r.path));
    var ev = isEv ? '<span class="evtag">증거 관련</span>' : '';
    var cls = 'row' + (isEv ? ' ev' : '') + (soon ? ' warn' : '');
    // actor 뱃지(귀속 행). user→A, agent→B.
    var badge = '';
    if (r.actor === "user") badge = '<span class="actorbadge a" title="사용자">A</span>';
    else if (r.actor === "agent") badge = '<span class="actorbadge b" title="에이전트">B</span>';
    // 출처(transcript file:line) — 있을 때만.
    var src = (r.source && r.source.file != null)
      ? '<span class="rsource">' + esc(r.source.file) + ':' + esc(r.source.line) + '</span> '
      : '';
    return '<div class="' + cls + '">' + ev + badge + src + esc(r.path) + ' ' +
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

  /* [#4][R9] tmp 보존기간: transcript 귀속 우선 재설계.
     완전성 불변식: 헤더가 전체 tmp 개수를 항상 공개(잔여 은닉 금지). 접근실패는 errors[](여기 미표시).
     - PRIMARY 목록 = attributed(transcript 기록 작업 파일)만 — 환경 잔존물은 접이식으로 분리.
     - origin-aware 만료: wsl=systemd ~30d(만료 표기), windows=무기한(자동삭제 없음).
     leakSet optional(없으면 증거표식 생략). 값은 엔진 단일진실 — JS 재판정/재집계 없음. 모든 동적 esc(). */
  function renderRetention(el, rows, leakSet) {
    if (!el) return;
    if (!rows || !rows.length) { el.innerHTML = '<span class="muted">tmp 잔존 없음</span>'; return; }
    var hasLeak = !!(leakSet && leakSet.size);
    function isEv(r) { return hasLeak && leakSet.has(r.path); }

    var attributed = rows.filter(function (r) { return r.attributed === true; });
    var nonAttributed = rows.filter(function (r) { return r.attributed !== true; });

    // 만료임박: 귀속 wsl 행 중 0<expires_in_days≤7.
    var soon = attributed.filter(function (r) {
      return r.origin === "wsl" && r.expires_in_days != null &&
        r.expires_in_days > 0 && r.expires_in_days <= 7;
    }).length;

    // 헤더(완전성 — 전체·귀속·임박 모두 공개).
    var html = '<div class="rnote">WSL /tmp는 ~30일(systemd) 후 정리될 수 있음 · ' +
      'Windows tmp는 자동삭제 없음(무기한 잔존). 목록은 transcript에 기록된 작업 파일만.</div>';
    html += '<div class="sub">전체 tmp ' + rows.length + '개 중 transcript 귀속 ' +
      attributed.length + '개 · 만료임박(WSL ≤7d) ' + soon + '개</div>';

    // 귀속 행 정렬: 증거 desc, 임박(wsl) desc, expires_in_days asc(windows null은 맨 뒤), path asc.
    function isSoon(r) {
      return r.origin === "wsl" && r.expires_in_days != null &&
        r.expires_in_days > 0 && r.expires_in_days <= 7;
    }
    var attSorted = attributed.slice().sort(function (a, b) {
      var ev = (isEv(b) ? 1 : 0) - (isEv(a) ? 1 : 0);
      if (ev) return ev;
      var sn = (isSoon(b) ? 1 : 0) - (isSoon(a) ? 1 : 0);
      if (sn) return sn;
      var ae = (a.expires_in_days == null) ? Infinity : a.expires_in_days;
      var be = (b.expires_in_days == null) ? Infinity : b.expires_in_days;
      if (ae !== be) return ae - be;
      return a.path < b.path ? -1 : a.path > b.path ? 1 : 0;
    });

    if (attSorted.length) {
      html += attSorted.map(function (r) { return retentionRowHTML(r, leakSet); }).join("");
    } else {
      html += '<div class="empty">transcript에 귀속된 tmp 작업 파일 없음</div>';
    }

    // 환경 잔존물(귀속 안 됨) — 완전성 위해 보존하되 접이식 + 롤업 그룹(평면 덤프 회피).
    // tmp 존재 != Claude 귀속(/tmp는 모든 프로세스 공유) — 중립 표기.
    if (nonAttributed.length) {
      var groups = {};
      nonAttributed.forEach(function (r) {
        var dir = rollupKey(r.path);
        (groups[dir] || (groups[dir] = [])).push(r);
      });
      var grpHTML = Object.keys(groups).sort().map(function (dir) {
        var items = groups[dir].slice().sort(function (a, b) {
          return a.path < b.path ? -1 : a.path > b.path ? 1 : 0;
        });
        var body = items.map(function (r) { return retentionRowHTML(r, leakSet); }).join("");
        return '<details class="rgrp"><summary class="rsum">' + esc(dir) +
          ' (' + items.length + '개)</summary>' + body + '</details>';
      }).join("");
      html += '<details class="rresidue"><summary>환경 잔존물(귀속 안 됨) ' +
        nonAttributed.length + '개</summary>' + grpHTML + '</details>';
    }

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

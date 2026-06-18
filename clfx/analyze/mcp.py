"""MCP 통합 — read-only 설정 스캔(마스킹) + transcript 실사용 집계 + 대조.

절대 불변식:
- READ-ONLY FS: open(path,"r")+json.load만.
- 완전성: ~/.claude.json이 아는 모든 project의 .mcp.json 읽기. 실패→errors[].
- 보안: env 값 전부 ‹secret›, url/args는 secrets.scan/mask. command는 유지.
- 결정성: 모든 출력 정렬.
"""

import json
import os
import re

from clfx.analyze.secrets import mask, scan
from clfx.event import ts_key


def _mask_str(s):
    """문자열 내 secret 패턴 마스킹(없으면 원본)."""
    if not isinstance(s, str):
        return s
    f = scan(s)
    return mask(s, f) if f else s


# F3: 키이름 기준 강제 마스킹 — 저엔트로피 토큰도 scan/mask와 병행해 마스킹.
_SENS = r"token|api[-_]?key|secret|password|authorization|auth|access[-_]?token|bearer"
_URL_KV = re.compile(r"(?i)([?&#](?:" + _SENS + r")=)([^&#]*)")
_ARG_EQ = re.compile(r"(?i)^(--?(?:" + _SENS + r")=)(.*)$")
_ARG_FLAG = re.compile(r"(?i)^--?(?:" + _SENS + r")$")
_BEARER = re.compile(r"(?i)(bearer\s+)(\S+)")


def _mask_url(u):
    if not isinstance(u, str):
        return u
    u = _URL_KV.sub(lambda m: m.group(1) + "‹secret›", u)   # ?token=.. / &api_key=.. / #secret=..
    return _mask_str(u)                                     # 고엔트로피 패턴도 병행


def _mask_args(args):
    out, mask_next = [], False
    for a in args:
        if not isinstance(a, str):
            out.append(a); continue
        if mask_next:                                       # 직전이 분리형 민감 플래그(--token VAL)
            out.append("‹secret›"); mask_next = False; continue
        if _ARG_FLAG.match(a):                              # --token / --api-key (분리형) → 다음 값 마스킹
            out.append(a); mask_next = True; continue
        m = _ARG_EQ.match(a)
        if m:                                               # --token=VAL / --api-key=VAL
            out.append(m.group(1) + "‹secret›"); continue
        b = _BEARER.sub(lambda mm: mm.group(1) + "‹secret›", a)  # Authorization: Bearer VAL
        out.append(_mask_str(b))                            # 인라인 고엔트로피도 병행
    return out


def _mask_config(cfg):
    """MCP 서버 설정 dict → 마스킹 사본. env 값 전부 ‹secret›(키 보존), url/args는 키이름+scan/mask 병행."""
    out = dict(cfg)
    env = out.get("env")
    if isinstance(env, dict):
        out["env"] = {k: "‹secret›" for k in env}      # 값은 민감 → 전부 마스킹, 키는 증거로 보존
    if isinstance(out.get("url"), str):
        out["url"] = _mask_url(out["url"])
    if isinstance(out.get("args"), list):
        out["args"] = _mask_args(out["args"])
    return out


def parse_mcp_config(path):
    """단일 .mcp.json 또는 mcpServers 보유 JSON을 read-only로 읽어 {server: 마스킹설정}.
    읽기/파싱 실패는 raise(상위 find_mcp_configs가 errors로 수집)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    servers = data.get("mcpServers") or {}
    out = {}
    for name, cfg in servers.items():
        if isinstance(cfg, dict):
            out[name] = _mask_config(cfg)
    return out


def _config_rows(servers, scope, project, source_file):
    """{server: 마스킹설정} → 정규화된 행 리스트."""
    rows = []
    for name, cfg in servers.items():
        rows.append({
            "server": name,
            "scope": scope,                 # "global" | "project"
            "project": project,             # 프로젝트 경로(글로벌이면 None)
            "command": cfg.get("command"),
            "args": cfg.get("args") if isinstance(cfg.get("args"), list) else [],
            "type": cfg.get("type"),
            "url": cfg.get("url"),
            "env_keys": sorted(cfg["env"].keys()) if isinstance(cfg.get("env"), dict) else [],
            "source_file": source_file,
        })
    return rows


def _synthetic_row(name, scope, project, source_file):
    """설정 본문이 없는 출처(커넥터·플러그인·enabledMcpjsonServers)용 빈 행.
    server/scope/project 외 필드는 비움(명령·env 등 알 수 없음)."""
    return {
        "server": name,
        "scope": scope,                 # "connector" | "plugin" | "project"
        "project": project,
        "command": None,
        "args": [],
        "type": None,
        "url": None,
        "env_keys": [],
        "source_file": source_file,
    }


def find_mcp_configs(roots):
    """각 .claude 루트의 형제 ~/.claude.json + 그 projects의 .mcp.json 전수 read-only 스캔.
    추가 출처(claude.ai 커넥터·플러그인·enabledMcpjsonServers)도 설정으로 인식.
    반환 {"configs":[...정렬...], "errors":[...정렬...], "plugin_prefixes":[...정렬...]}.
    완전성: 모든 설정 읽기, 실패→errors(조용히 누락 금지)."""
    from clfx.analyze.artifacts import resolve_candidates

    configs = []
    errors = []
    plugin_prefixes = set()                 # plugin_<plugin> prefix 집합(서버명 매칭용)
    seen = set()                            # (source_file, scope, project, server) 중복제거(결정성)

    def _add(servers, scope, project, source_file):
        for row in _config_rows(servers, scope, project, source_file):
            key = (source_file, scope, project, row["server"])
            if key in seen:
                continue
            seen.add(key)
            configs.append(row)

    def _add_row(row):
        key = (row["source_file"], row["scope"], row["project"], row["server"])
        if key in seen:
            return
        seen.add(key)
        configs.append(row)

    for root in roots or []:
        claude_json = os.path.join(os.path.dirname(str(root)), ".claude.json")
        if not os.path.isfile(claude_json):
            continue
        try:
            with open(claude_json, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:                                  # noqa: BLE001 - 완전성: 어떤 실패도 errors로
            errors.append({"path": claude_json, "reason": type(e).__name__})
            continue
        # 글로벌 mcpServers
        gserv = data.get("mcpServers") or {}
        _add({k: _mask_config(v) for k, v in gserv.items() if isinstance(v, dict)},
             "global", None, claude_json)
        # claude.ai 커넥터 (claudeAiMcpEverConnected: 서버명 list)
        for name in data.get("claudeAiMcpEverConnected") or []:
            if isinstance(name, str):
                _add_row(_synthetic_row(name, "connector", None, claude_json))
        # 플러그인 사용 (pluginUsage: {"<plugin>@<marketplace>": n}) → plugin_<plugin> prefix
        for key in (data.get("pluginUsage") or {}):
            if isinstance(key, str):
                plugin = key.split("@", 1)[0]
                if plugin:
                    plugin_prefixes.add("plugin_" + plugin)
        # best-effort: 플러그인 매니페스트(plugin.json)의 mcpServers를 서버명(scope="plugin")으로 추가.
        # 경로 불확실 → 실패해도 errors[]에 기록하고 계속(조용히 누락 금지).
        plugins_dir = os.path.join(os.path.dirname(claude_json), ".claude", "plugins")
        if os.path.isdir(plugins_dir):
            for dirpath, _dirs, files in os.walk(plugins_dir, followlinks=False):
                for fname in files:
                    if fname != "plugin.json":
                        continue
                    mpath = os.path.join(dirpath, fname)
                    try:
                        with open(mpath, "r", encoding="utf-8") as f:
                            mdata = json.load(f)
                        mserv = mdata.get("mcpServers") or {}
                        for sname in mserv:
                            if isinstance(sname, str):
                                _add_row(_synthetic_row(sname, "plugin", None, mpath))
                    except Exception as e:                      # noqa: BLE001 - best-effort: 실패도 기록
                        errors.append({"path": mpath, "reason": type(e).__name__})
        # 프로젝트별
        for proj, pdata in (data.get("projects") or {}).items():
            # 인라인 projects[proj].mcpServers
            if isinstance(pdata, dict):
                pserv = pdata.get("mcpServers") or {}
                _add({k: _mask_config(v) for k, v in pserv.items() if isinstance(v, dict)},
                     "project", proj, claude_json)
                # 활성화된 .mcp.json 서버 (enabledMcpjsonServers: 서버명 list)
                for name in pdata.get("enabledMcpjsonServers") or []:
                    if isinstance(name, str):
                        _add_row(_synthetic_row(name, "project", proj, claude_json))
            # <proj>/.mcp.json (경로변환 후 존재하는 첫 후보)
            for cand_dir in resolve_candidates(proj, root):
                mcp_path = os.path.join(cand_dir, ".mcp.json")
                if not os.path.isfile(mcp_path):
                    continue
                try:
                    servers = parse_mcp_config(mcp_path)
                except Exception as e:                          # noqa: BLE001
                    errors.append({"path": mcp_path, "reason": type(e).__name__})
                    break
                _add(servers, "project", proj, mcp_path)
                break                                           # 첫 존재 후보만(동일 프로젝트 1파일)

    configs.sort(key=lambda c: (c["scope"], c["project"] or "", c["server"]))
    errors.sort(key=lambda e: e["path"])
    return {
        "configs": configs,
        "errors": errors,
        "plugin_prefixes": sorted(plugin_prefixes),
    }


def _split_target(target):
    """mcp__<server>__<tool> → (server, tool). 형식 어긋나면 (target, '')."""
    parts = (target or "").split("__")
    server = parts[1] if len(parts) >= 2 else (target or "")
    tool = parts[2] if len(parts) >= 3 else ""
    return server, tool


def mcp_usage_from_events(events):
    """action=='mcp' 이벤트를 (server, tool)별 집계. 정렬: (server, tool). 결정적."""
    agg = {}
    for e in events or []:
        if getattr(e, "action", None) != "mcp":
            continue
        server, tool = _split_target(e.target)
        a = agg.setdefault((server, tool), {
            "server": server, "tool": tool, "count": 0,
            "first_ts": None, "last_ts": None, "sessions": set(),
        })
        a["count"] += 1
        a["sessions"].add(e.session)
        if a["first_ts"] is None or ts_key(e.ts) < ts_key(a["first_ts"]):
            a["first_ts"] = e.ts
        if a["last_ts"] is None or ts_key(e.ts) > ts_key(a["last_ts"]):
            a["last_ts"] = e.ts
    rows = [{
        "server": a["server"], "tool": a["tool"], "count": a["count"],
        "first_ts": a["first_ts"], "last_ts": a["last_ts"], "sessions": len(a["sessions"]),
    } for a in agg.values()]
    rows.sort(key=lambda r: (r["server"], r["tool"]))
    return rows


def _norm(s):
    """서버명 매칭용 정규화: 소문자 → 영숫자 외 '_' → 연속 '_' 축약 → 양끝 '_' strip.
    'claude.ai Notion'/'claude_ai_Notion' → 'claude_ai_notion' (표기차 흡수). 표시는 원본 유지."""
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower())
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def mcp_summary(roots, events):
    """설정 스캔 + 실사용 집계 + 대조. /api/mcp 단일 진입점.
    plugin prefix(plugin_<plugin>_*) 매칭으로 플러그인 서버를 설정됨으로 인식.
    이름 정규화(_norm)로 표기차(공백/구두점/대소문자)를 흡수해 매칭(표시는 원본명 유지)."""
    cfg = find_mcp_configs(roots)
    configs, errors = cfg["configs"], cfg["errors"]
    prefixes = cfg["plugin_prefixes"]
    usage = mcp_usage_from_events(events)
    configured = {c["server"] for c in configs}
    used = {u["server"] for u in usage}
    configured_norm = {_norm(c) for c in configured}
    used_norm = {_norm(u) for u in used}

    def _is_configured(s):
        if _norm(s) in configured_norm:
            return True
        ns = _norm(s)
        return any(
            s == p or s.startswith(p + "_") or s.startswith(p)
            or ns == _norm(p) or ns.startswith(_norm(p) + "_") or ns.startswith(_norm(p))
            for p in prefixes
        )

    return {
        "configs": configs,
        "usage": usage,
        "configured_unused": sorted(c for c in configured if _norm(c) not in used_norm),
        "used_unconfigured": sorted(s for s in used if not _is_configured(s)),
        "errors": errors,
        "plugin_prefixes": prefixes,
    }

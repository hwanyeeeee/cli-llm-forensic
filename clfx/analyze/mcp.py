"""MCP 통합 — read-only 설정 스캔(마스킹) + transcript 실사용 집계 + 대조.

절대 불변식:
- READ-ONLY FS: open(path,"r")+json.load만.
- 완전성: ~/.claude.json이 아는 모든 project의 .mcp.json 읽기. 실패→errors[].
- 보안: env 값 전부 ‹secret›, url/args는 secrets.scan/mask. command는 유지.
- 결정성: 모든 출력 정렬.
"""

import json
import os

from clfx.analyze.secrets import mask, scan
from clfx.event import ts_key


def _mask_str(s):
    """문자열 내 secret 패턴 마스킹(없으면 원본)."""
    if not isinstance(s, str):
        return s
    f = scan(s)
    return mask(s, f) if f else s


def _mask_config(cfg):
    """MCP 서버 설정 dict → 마스킹 사본. env 값 전부 ‹secret›(키 보존), url/args는 scan/mask."""
    out = dict(cfg)
    env = out.get("env")
    if isinstance(env, dict):
        out["env"] = {k: "‹secret›" for k in env}      # 값은 민감 → 전부 마스킹, 키는 증거로 보존
    if isinstance(out.get("url"), str):
        out["url"] = _mask_str(out["url"])
    if isinstance(out.get("args"), list):
        out["args"] = [_mask_str(a) for a in out["args"]]
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


def find_mcp_configs(roots):
    """각 .claude 루트의 형제 ~/.claude.json + 그 projects의 .mcp.json 전수 read-only 스캔.
    반환 {"configs":[...정렬...], "errors":[...정렬...]}. 완전성: 모든 설정 읽기, 실패→errors."""
    from clfx.analyze.artifacts import resolve_candidates

    configs = []
    errors = []
    seen = set()                            # (source_file, scope, project, server) 중복제거(결정성)

    def _add(servers, scope, project, source_file):
        for row in _config_rows(servers, scope, project, source_file):
            key = (source_file, scope, project, row["server"])
            if key in seen:
                continue
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
        # 프로젝트별
        for proj, pdata in (data.get("projects") or {}).items():
            # 인라인 projects[proj].mcpServers
            if isinstance(pdata, dict):
                pserv = pdata.get("mcpServers") or {}
                _add({k: _mask_config(v) for k, v in pserv.items() if isinstance(v, dict)},
                     "project", proj, claude_json)
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
    return {"configs": configs, "errors": errors}


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


def mcp_summary(roots, events):
    """설정 스캔 + 실사용 집계 + 대조. /api/mcp 단일 진입점."""
    cfg = find_mcp_configs(roots)
    configs, errors = cfg["configs"], cfg["errors"]
    usage = mcp_usage_from_events(events)
    configured = {c["server"] for c in configs}
    used = {u["server"] for u in usage}
    return {
        "configs": configs,
        "usage": usage,
        "configured_unused": sorted(configured - used),
        "used_unconfigured": sorted(used - configured),
        "errors": errors,
    }

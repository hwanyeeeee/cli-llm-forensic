"""O11 WSL-side 파싱 위임 — UNC 판정/경로재작성/스테이징 해시/헬퍼 등가성(핵심: 직접 파싱과 byte-identical)."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

import clfx.wsl_delegate as wd
from clfx.web.api import scan_to_engine

REPO = Path(__file__).resolve().parents[1]
FIXTURE = str(REPO / "tests" / "fixtures" / "dot-claude")
LOCAL_RUNNER = [sys.executable, "-B", "-E", "-s"]


def test_parse_wsl_unc():
    assert wd.parse_wsl_unc(r"\\wsl.localhost\Ubuntu\home\u\.claude") == ("Ubuntu", "/home/u/.claude")
    assert wd.parse_wsl_unc(r"\\wsl$\Ubuntu-22.04\root\.claude") == ("Ubuntu-22.04", "/root/.claude")
    assert wd.parse_wsl_unc("/home/u/.claude") is None
    assert wd.parse_wsl_unc(r"C:\Users\u\.claude") is None


def test_rewrite_prefix_posix_to_unc():
    out = wd.rewrite_prefix("/home/u/.claude/projects/a.jsonl",
                            "/home/u/.claude", r"\\wsl.localhost\Ubuntu\home\u\.claude")
    assert out == r"\\wsl.localhost\Ubuntu\home\u\.claude\projects\a.jsonl"


def test_rewrite_prefix_identity_and_miss():
    assert wd.rewrite_prefix("/a/b/c.jsonl", "/a/b", "/a/b") == "/a/b/c.jsonl"
    assert wd.rewrite_prefix("/other/x.jsonl", "/a/b", "/dst") == "/other/x.jsonl"


def test_win_to_wsl_path():
    assert wd.win_to_wsl_path(r"C:\Users\u\AppData\Local\Temp\o.jsonl") == "/mnt/c/Users/u/AppData/Local/Temp/o.jsonl"
    with pytest.raises(wd.DelegateError):
        wd.win_to_wsl_path("/already/posix")


def test_stage_helper_deterministic_sha(tmp_path):
    a, sha_a = wd.stage_helper(tmp_path / "s1")
    b, sha_b = wd.stage_helper(tmp_path / "s2")
    assert a.exists() and (tmp_path / "s1" / "clfx" / "wsl_helper.py").exists()
    assert sha_a == sha_b and len(sha_a) == 64


def test_delegate_equivalence_with_direct_parse(tmp_path):
    # 위임 경로(로컬 러너 주입 = wsl.exe 자리에 현재 파이썬)가 직접 파싱과 완전 동일해야 함(I1 핵심).
    from clfx.cli import _origin_label
    label = _origin_label(FIXTURE)
    direct = scan_to_engine([FIXTURE])                    # 현행(직접) 경로 — 태그+enrich 완료
    progress = []
    res = wd._run_staged(FIXTURE, FIXTURE, label, runner=LOCAL_RUNNER,
                         workdir=str(tmp_path), on_progress=lambda d, t: progress.append((d, t)))
    assert [e.to_dict() for e in res["events"]] == [e.to_dict() for e in direct.events]
    assert res["manifest"] == direct.evidence_manifest
    assert len(res["helper_sha256"]) == 64
    assert {"parse_wall_s", "enrich_s"} <= set(res["timings"])
    assert progress and progress[-1][0] == progress[-1][1]   # 진행률이 완주까지 보고됨


def _codex_root_without_sidecars(tmp_path):
    """rollout 1개 + 사이드카 없는 SQLx DB 1개 → sqlite_sidecar_missing 경고를 유발하는 최소 증거 루트."""
    root = tmp_path / "case" / ".codex"
    rollout = root / "sessions" / "2026" / "08" / "21" / "rollout-delegate.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(json.dumps({
        "timestamp": "2026-08-21T05:00:00Z", "type": "session_meta", "ordinal": 1,
        "payload": {"id": "delegate-session", "cli_version": "0.147.0",
                    "originator": "codex-tui"}}) + "\n", encoding="utf-8")
    conn = sqlite3.connect(root / "state_5.sqlite")      # 기본 journal_mode → -wal/-shm 안 남음
    conn.execute("CREATE TABLE _sqlx_migrations(version INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO _sqlx_migrations VALUES (46)")
    conn.execute("""CREATE TABLE threads(
                        id TEXT PRIMARY KEY, rollout_path TEXT, cwd TEXT, git_branch TEXT,
                        git_sha TEXT, model TEXT, approval_mode TEXT, sandbox_policy TEXT)""")
    conn.commit()
    conn.close()
    return root


def test_delegate_rewrites_every_path_in_a_warning(tmp_path):
    # 6단계 회귀: file만 재작성하면 sqlite_sidecar_missing.missing[]가 POSIX로 남아
    # 경고 하나에 UNC/POSIX가 섞인다 → Windows 조사자가 못 여는 경로가 보고서에 실린다.
    root = _codex_root_without_sidecars(tmp_path)
    target = r"\\wsl.localhost\Ubuntu\case\.codex"

    res = wd._run_staged(str(root), target, "wsl", runner=LOCAL_RUNNER,
                         workdir=str(tmp_path / "work"))

    sidecar = [w for w in res["warnings"] if w["kind"] == "sqlite_sidecar_missing"]
    assert sidecar, res["warnings"]
    for warning in sidecar:
        assert warning["file"].startswith(target)
        assert warning["missing"] == [warning["file"] + "-wal", warning["file"] + "-shm"]
    assert all(key.startswith(target) for key in res["manifest"])


def test_delegate_helper_failure_raises(tmp_path):
    with pytest.raises(wd.DelegateError):
        wd._run_staged("/nonexistent-root-zzz", "/nonexistent-root-zzz", "other",
                       runner=LOCAL_RUNNER, workdir=str(tmp_path))


import clfx.web.api as api


def _fresh_delegate_result(tmp_path):
    """실제 헬퍼(로컬 러너)로 만든 진짜 위임 결과 — 통합 테스트 입력."""
    from clfx.cli import _origin_label
    return wd._run_staged(FIXTURE, FIXTURE, _origin_label(FIXTURE),
                          runner=LOCAL_RUNNER, workdir=str(tmp_path))


def test_scan_to_engine_with_delegate_equals_direct(tmp_path, monkeypatch):
    direct = scan_to_engine([FIXTURE])
    res = _fresh_delegate_result(tmp_path)
    monkeypatch.setattr(api, "_delegate_eligible", lambda r: True)
    monkeypatch.setattr(api.wsl_delegate, "delegate_root",
                        lambda root, label, on_progress=None: res)
    eng = scan_to_engine([FIXTURE])
    assert [e.to_dict() for e in eng.events] == [e.to_dict() for e in direct.events]   # I1
    assert eng.evidence_manifest == direct.evidence_manifest
    assert eng.delegate_info["delegated"] == [FIXTURE]
    assert eng.delegate_info["helper_sha256"] == [res["helper_sha256"]]
    assert eng.delegate_info["errors"] == []


def test_scan_to_engine_delegate_failure_falls_back(monkeypatch):
    direct = scan_to_engine([FIXTURE])
    monkeypatch.setattr(api, "_delegate_eligible", lambda r: True)

    def _boom(root, label, on_progress=None):
        raise wd.DelegateError("simulated 9P/interop failure")
    monkeypatch.setattr(api.wsl_delegate, "delegate_root", _boom)
    eng = scan_to_engine([FIXTURE])
    assert [e.to_dict() for e in eng.events] == [e.to_dict() for e in direct.events]   # 폴백 무손실(I2)
    assert eng.delegate_info["delegated"] == []
    assert eng.delegate_info["errors"] and "simulated" in eng.delegate_info["errors"][0]["error"]


def test_delegate_eligible_gates():
    # WSL(리눅스)에서는 항상 False(os.name != "nt") — 위임은 Windows 전용.
    assert api._delegate_eligible(r"\\wsl.localhost\Ubuntu\home\u\.claude") is False
    assert api._delegate_eligible("/home/u/.claude") is False


def test_build_script_bundles_helper_source():
    # frozen exe에서 helper_source_dir()가 _MEIPASS/clfx_src를 찾음 — 빌드가 소스를 동봉해야 함.
    # 단일 진실원천 = build-exe.bat(tracked). AgenTrace.spec은 bat가 재생성하는 산출물이라
    # gitignore(*.spec) — fresh clone엔 없다. 존재할 때만 정합성 검사(이식성).
    bat = (REPO / "packaging" / "build-exe.bat").read_text(encoding="utf-8", errors="ignore")
    assert 'clfx;clfx_src' in bat
    spec_path = REPO / "AgenTrace.spec"
    if spec_path.exists():
        assert "clfx_src" in spec_path.read_text(encoding="utf-8", errors="ignore")


# --- 2026-07-03 실데이터 회귀: U+2028/NEL이 preview에 있으면 splitlines()가 JSON을 쪼갬 ---

def test_parse_out_text_survives_unicode_line_separators():
    import json
    meta = {"files": 1, "events": 1, "manifest": {}, "timings": {}}
    ev = {"ts": None, "agent": "claude", "session": "s", "actor": "user", "action": "prompt",
          "target": "t", "preview": "a b\x85c d", "source": {"file": "/r/x.jsonl", "line": 1},
          "tags": []}
    text = json.dumps(meta, ensure_ascii=False) + "\n" + json.dumps(ev, ensure_ascii=False) + "\n"
    m, dicts = wd._parse_out_text(text)
    assert m["events"] == 1
    assert dicts[0]["preview"] == "a b\x85c d"   # 무손실 왕복(줄 쪼개짐 없음)


def test_parse_out_text_bad_event_raises_delegate_error():
    text = '{"files":0,"events":0,"manifest":{},"timings":{}}\n{"broken": "untermina\n'
    with pytest.raises(wd.DelegateError):
        wd._parse_out_text(text)


def test_scan_to_engine_falls_back_on_any_delegate_exception(monkeypatch):
    # DelegateError가 아닌 예외(실사: JSONDecodeError)도 스캔을 죽이지 않고 직접 경로 폴백해야 함(I2).
    direct = scan_to_engine([FIXTURE])
    monkeypatch.setattr(api, "_delegate_eligible", lambda r: True)

    def _boom(root, label, on_progress=None):
        raise ValueError("Unterminated string starting at: line 1 column 183 (char 182)")
    monkeypatch.setattr(api.wsl_delegate, "delegate_root", _boom)
    eng = scan_to_engine([FIXTURE])
    assert [e.to_dict() for e in eng.events] == [e.to_dict() for e in direct.events]
    assert eng.delegate_info["errors"] and "ValueError" in eng.delegate_info["errors"][0]["error"]

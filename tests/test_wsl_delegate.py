"""O11 WSL-side 파싱 위임 — UNC 판정/경로재작성/스테이징 해시/헬퍼 등가성(핵심: 직접 파싱과 byte-identical)."""
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


def test_delegate_helper_failure_raises(tmp_path):
    with pytest.raises(wd.DelegateError):
        wd._run_staged("/nonexistent-root-zzz", "/nonexistent-root-zzz", "other",
                       runner=LOCAL_RUNNER, workdir=str(tmp_path))

"""Phase1 프런트 계측 — performance.mark/FETCH_TIMINGS 존재 + JS 문법 유효(I6: 표시·콘솔만)."""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
APP_JS = REPO / "clfx" / "web" / "static" / "app.js"


def test_app_js_perf_instrumentation_present():
    src = APP_JS.read_text(encoding="utf-8")
    assert 'performance.mark("clfx-boot-start")' in src
    assert 'performance.mark("clfx-boot-stage1")' in src
    assert 'performance.mark("clfx-boot-stage2")' in src
    assert "FETCH_TIMINGS" in src
    assert "function perfReport" in src


def test_app_js_node_check_still_valid():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    r = subprocess.run([node, "--check", str(APP_JS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

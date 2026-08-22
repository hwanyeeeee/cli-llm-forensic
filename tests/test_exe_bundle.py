"""25단계: exe 번들 검증이 소스와 함께 늙지 않게 잡아 둔다.

`packaging/verify-exe.py` 는 빌드된 exe 를 열어 소스와 대조한다. 그런데 **그 검증기 자체가
낡을 수 있다** — 새 정적 자산을 추가하고 검증기 목록에 안 넣으면, 검증은 통과하면서 그
자산만 조용히 빠진다. 그래서 여기서 검증기의 기대 목록을 실제 소스 트리와 맞춰 둔다.

빌드 산출물이 있는 머신에서는 검증기를 실제로 돌린다. 없으면 skip 하되 **조용히 통과시키지
않는다** — 사유를 남긴다(패널 수치 테스트와 같은 규칙).
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VERIFY = REPO / "packaging" / "verify-exe.py"
STATIC = REPO / "clfx" / "web" / "static"
EXE = REPO / "dist" / "AgenTrace.exe"
BAT = REPO / "packaging" / "build-exe.bat"


def _verifier():
    spec = importlib.util.spec_from_file_location("clfx_verify_exe", VERIFY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_asset_list_covers_every_static_file():
    """정적 자산은 `datas` 로 복사될 뿐 자동탐지가 없다. 새 파일을 넣고 검증기에 안 넣으면
    그 파일만 낡은 채로 exe 에 박혀도 아무도 모른다."""
    on_disk = {p.name for p in STATIC.iterdir() if p.is_file()}
    listed = set(_verifier().REQUIRED_ASSETS)
    assert listed == on_disk, (
        f"검증기 자산 목록이 소스와 어긋난다 — 소스에만: {sorted(on_disk - listed)} · "
        f"목록에만: {sorted(listed - on_disk)}")


def test_required_modules_actually_exist():
    """없는 모듈을 요구하면 검증이 영원히 실패한다. 반대로 오타는 영원히 통과한다."""
    for name in _verifier().REQUIRED_MODULES:
        path = REPO / Path(*name.split(".")[:-1]) / (name.split(".")[-1] + ".py")
        package = REPO / Path(*name.split(".")) / "__init__.py"
        assert path.is_file() or package.is_file(), f"검증기가 없는 모듈을 요구한다: {name}"


def test_wsl_helper_is_data_not_a_frozen_module():
    """`clfx.wsl_helper` 는 exe 프로세스가 import 하지 않는다 — wsl_delegate 가 shim 문자열을
    파일로 써서 WSL 안의 **다른** python3 로 실행한다. 그래서 PYZ 가 아니라 clfx_src(datas)
    로 실려야 맞다. 검증기 목록에 되돌려 넣으면 안 쓰는 모듈을 프리즈하게 된다."""
    module = _verifier()
    assert "clfx.wsl_helper" not in module.REQUIRED_MODULES
    source = (REPO / "clfx" / "wsl_delegate.py").read_text(encoding="utf-8")
    assert "from clfx.wsl_helper import main" in source, "shim 이 바뀌었다면 이 판단도 다시 해라"
    # 그 문자열이 진짜 shim 안(=실행 코드가 아니라 데이터)에 있는지 확인
    assert "_SHIM = (" in source


def test_build_script_runs_the_verifier():
    """검증을 '기억해서 돌리는 절차'로 두면 안 돈다. 빌드 스크립트가 직접 부르게 한다."""
    text = BAT.read_text(encoding="utf-8", errors="replace")
    assert "verify-exe.py" in text, "build-exe.bat 가 빌드 후 검증기를 안 부른다"


@pytest.mark.skipif(not EXE.is_file(),
                    reason=f"빌드 산출물 없음: {EXE} — packaging/build-exe.bat 를 돌린 머신에서만 "
                           "번들 내용을 검증할 수 있다. 배포 전에는 반드시 한 번 돌려라.")
def test_built_exe_matches_the_sources():
    """실제 번들 대조. 모듈 누락·자산 낡음이면 검증기가 0이 아닌 코드를 낸다."""
    result = subprocess.run([sys.executable, str(VERIFY), str(EXE)],
                            capture_output=True, text=True, cwd=str(REPO))
    assert result.returncode == 0, result.stdout + result.stderr

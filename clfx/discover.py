"""소스(.claude 루트) 자동탐지. 단일 PC의 Windows + WSL 후보를 나열한다.
판정·라벨은 cli._origin_label 재사용(단일 출처). 환경 비의존 위해 candidates 주입 가능."""
import os
from pathlib import Path
from clfx.cli import _origin_label


def _default_candidates():
    """현재 OS home + Windows %USERPROFILE% + WSL distro home들의 .claude 후보(중복제거, 순서보존)."""
    cands = []
    home = os.path.expanduser("~")
    cands.append(os.path.join(home, ".claude"))                  # 현재 OS home
    up = os.environ.get("USERPROFILE")                           # Windows home(있으면)
    if up:
        cands.append(os.path.join(up, ".claude"))
    # WSL distros (Windows에서 실행 시 보임). 없으면 조용히 스킵.
    wsl_root = Path(r"\\wsl.localhost")
    try:
        if wsl_root.exists():
            for distro in wsl_root.iterdir():
                # \\wsl.localhost\<distro>\home\<user>\.claude
                home_dir = distro / "home"
                if home_dir.exists():
                    for user in home_dir.iterdir():
                        cands.append(str(user / ".claude"))
                cands.append(str(distro / "root" / ".claude"))   # 루트 사용자
    except OSError:
        pass
    # 중복 제거(순서 보존)
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def discover_sources(candidates=None):
    """반환: [{"path","label","exists"}] — label=origin(wsl/windows/other), exists=디렉터리 존재."""
    cands = candidates if candidates is not None else _default_candidates()
    out = []
    for c in cands:
        out.append({"path": c, "label": _origin_label(c), "exists": os.path.isdir(c)})
    return out

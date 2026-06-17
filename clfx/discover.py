"""소스(.claude 루트) 자동탐지. 단일 PC의 Windows + WSL 후보를 나열한다.
판정·라벨은 cli._origin_label 재사용(단일 출처). 환경 비의존 위해 candidates 주입 가능."""
import glob
import os
import subprocess
from pathlib import Path
from clfx.cli import _origin_label


def _parse_wsl_list(raw):
    """`wsl.exe -l -q` stdout(UTF-16LE) → distro 이름 리스트. 빈/깨짐은 []."""
    text = raw.decode("utf-16-le", errors="ignore").replace("\x00", "")
    return [line.strip().lstrip("﻿") for line in text.splitlines() if line.strip()]


def _wsl_distros():
    """설치된 WSL distro 목록(Windows 전용). 실패 시 []."""
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(["wsl.exe", "-l", "-q"],
                             capture_output=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return _parse_wsl_list(out or b"")


def _default_candidates():
    """현재 OS home + Windows %USERPROFILE% + WSL distro home들의 .claude 후보(중복제거, 순서보존)."""
    cands = []
    home = os.path.expanduser("~")
    cands.append(os.path.join(home, ".claude"))                  # 현재 OS home
    up = os.environ.get("USERPROFILE")                           # Windows home(있으면)
    if up:
        cands.append(os.path.join(up, ".claude"))
    # WSL/리눅스에서 Windows Claude 기록 보기: /mnt/c/Users/*/.claude (Windows에선 /mnt 없음→빈 결과)
    for c in sorted(glob.glob("/mnt/c/Users/*/.claude")):
        cands.append(c)
    # WSL distros (Windows 전용): 바 UNC 루트는 stat/iterdir 불가 → wsl.exe로 distro 목록을 얻어
    # 각 distro의 home/<user>/.claude 전체경로를 후보로(전체경로는 isdir 동작).
    for distro in _wsl_distros():
        base = Path(r"\\wsl.localhost") / distro
        home_dir = base / "home"
        try:
            if home_dir.is_dir():
                for user in home_dir.iterdir():
                    cands.append(str(user / ".claude"))
        except OSError:
            pass
        cands.append(str(base / "root" / ".claude"))
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

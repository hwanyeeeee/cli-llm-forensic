"""소스(.claude 루트) 자동탐지. 단일 PC의 Windows + WSL 후보를 나열한다.
판정·라벨은 cli._origin_label 재사용(단일 출처). 환경 비의존 위해 candidates 주입 가능."""
import glob
import os
import subprocess
import threading
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


_TIMEOUT_MSG = "접근 시간 초과 — WSL 파일공유(9P) 응답 없음. wsl --shutdown 후 재시도"


def _isdir_t(path, timeout=3.0):
    """os.path.isdir에 타임아웃 — 9P wedge 시 무한 hang 차단(2026-07-03 실사, O10).
    반환 (isdir, timed_out). 타임아웃 시 (False, True). 데몬 스레드가 남을 수 있으나
    프로세스 종료를 막지 않는다(의도적 트레이드오프 — hang보다 낫다)."""
    res = {}

    def _probe():
        try:
            res["v"] = os.path.isdir(path)
        except OSError:
            res["v"] = False

    t = threading.Thread(target=_probe, daemon=True)
    t.start()
    t.join(timeout)
    if "v" not in res:
        return False, True
    return res["v"], False


def _listdir_t(path, timeout=3.0):
    """디렉터리 나열에 타임아웃(WSL home 사용자 열거용). (이름 리스트, timed_out)."""
    res = {}

    def _probe():
        try:
            res["v"] = sorted(os.listdir(path))
        except OSError:
            res["v"] = []

    t = threading.Thread(target=_probe, daemon=True)
    t.start()
    t.join(timeout)
    if "v" not in res:
        return [], True
    return res["v"], False


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
        names, timed_out = _listdir_t(str(base / "home"))
        if not timed_out:
            for user in names:
                cands.append(str(base / "home" / user / ".claude"))
        cands.append(str(base / "root" / ".claude"))
    # 중복 제거(순서 보존)
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def discover_sources(candidates=None):
    """반환: [{"path","label","exists"[,"error"]}] — label=origin(wsl/windows/other), exists=디렉터리 존재.
    O10: 존재확인은 타임아웃 경유 — 원격 경로 hang 시 exists=False + error 사유(조용한 누락 금지)."""
    cands = candidates if candidates is not None else _default_candidates()
    out = []
    for c in cands:
        isdir, timed_out = _isdir_t(c)
        rec = {"path": c, "label": _origin_label(c), "exists": isdir}
        if timed_out:
            rec["error"] = _TIMEOUT_MSG
        out.append(rec)
    return out

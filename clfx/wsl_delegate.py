"""O11: WSL-side 파싱 위임 오케스트레이션 — \\wsl.localhost(9P) 우회.
wsl.exe interop 채널로 WSL 안에서 clfx.wsl_helper를 실행해 네이티브 파싱 결과만 회수한다.
9P가 wedge 되어도 interop은 별개 채널이라 동작(2026-07-03 실사, docs/perf-baseline.md).
read-only(I3): 증거 트리 쓰기 0 — 스테이징(헬퍼 사본)·출력(out.jsonl)은 호출측(Windows) 임시 디렉터리.
도구 무결성: 스테이징된 헬퍼 전체(.py + shim)의 SHA-256을 반환 — attestation에 표면화(chain of custody)."""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from clfx.event import Event


class DelegateError(Exception):
    """위임 실패 — 호출자는 UNC 직접 파싱으로 폴백하고 사유를 표면화한다(I2)."""


_UNC_RE = re.compile(r"^\\\\wsl(?:\.localhost|\$)\\([^\\]+)\\(.+)$")

_SHIM = ("import os, sys\n"
         "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
         "from clfx.wsl_helper import main\n"
         "sys.exit(main())\n")


def parse_wsl_unc(root):
    r"""\\wsl.localhost\<distro>\<path> 또는 \\wsl$\<distro>\<path> → (distro, "/posix/path"). 아니면 None."""
    m = _UNC_RE.match(str(root))
    if not m:
        return None
    return m.group(1), "/" + m.group(2).replace("\\", "/")


def rewrite_prefix(path, src_prefix, dst_prefix):
    """경로 표기 재작성(헬퍼의 posix 경로 → 호출자가 선택한 root 표기). 프리픽스 불일치는 원문 유지.
    dst가 백슬래시 표기면 잔여 구분자도 \\로 — UNC 직접 파싱 결과와 byte-identical(I1)."""
    p = str(path)
    if not p.startswith(src_prefix):
        return p
    rest = p[len(src_prefix):]
    if "\\" in dst_prefix:
        rest = rest.replace("/", "\\")
    return dst_prefix + rest


def win_to_wsl_path(p):
    """C:\\... → /mnt/c/... (wsl.exe에 넘길 인자). 드라이브 문자 소문자화. 비-드라이브 경로는 에러."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", str(p))
    if not m:
        raise DelegateError(f"Windows 드라이브 경로 아님: {p}")
    return "/mnt/" + m.group(1).lower() + "/" + m.group(2).replace("\\", "/")


def helper_source_dir():
    """스테이징할 clfx 패키지 소스 위치. PyInstaller onefile은 _MEIPASS/clfx_src(빌드 --add-data),
    개발/테스트는 설치된 패키지 디렉터리 자체."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cand = Path(base) / "clfx_src"
        if (cand / "wsl_helper.py").exists():
            return cand
    import clfx
    return Path(clfx.__file__).parent


def stage_helper(workdir):
    """workdir에 clfx 패키지 사본 + 실행 shim(run_helper.py) 기록. (shim_path, sha256_hex) 반환.
    sha256 = shim + 패키지 전체 .py(상대경로+내용, 정렬)의 결합 해시 — 결정적(도구 무결성 표면화용).
    web/(정적 UI)은 헬퍼에 불필요해 제외 — 스테이징 최소화."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    pkg_dst = workdir / "clfx"
    shutil.copytree(helper_source_dir(), pkg_dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "web"))
    shim_path = workdir / "run_helper.py"
    shim_path.write_text(_SHIM, encoding="utf-8")
    h = hashlib.sha256()
    h.update(_SHIM.encode("utf-8"))
    for f in sorted(pkg_dst.rglob("*.py")):
        h.update(str(f.relative_to(pkg_dst)).replace("\\", "/").encode("utf-8"))
        h.update(f.read_bytes())
    return shim_path, h.hexdigest()


def delegate_root(root, origin_label, on_progress=None, runner=None, workdir=None):
    """root(WSL UNC)를 WSL 내부에서 파싱해 회수. 반환 dict:
    {"events": [Event...(태그+enrich 완료, source.file은 원 UNC 표기)],
     "manifest": {원표기 jsonl path: sha256} (정렬), "timings": {...}, "helper_sha256": hex}.
    runner: 헬퍼 실행 argv 프리픽스(테스트 주입용) — None이면 wsl.exe interop."""
    parsed = parse_wsl_unc(root)
    if parsed is None:
        raise DelegateError(f"WSL UNC 아님: {root}")
    distro, posix_root = parsed
    return _run_staged(posix_root, str(root), origin_label, distro=distro,
                       on_progress=on_progress, runner=runner, workdir=workdir)


def _parse_out_text(text):
    """헬퍼 out 파일 텍스트 → (meta dict, [event dict...]). 전 실패는 DelegateError(호출자 폴백).
    반드시 split(\"\\n\") — splitlines()는 U+2028/U+2029/NEL(0x85)에서도 쪼개는데,
    json.dumps(ensure_ascii=False)는 이 문자들을 이스케이프하지 않아 preview에 있으면
    JSON 문자열 한가운데가 갈라져 'Unterminated string'이 난다(2026-07-03 실데이터 실사)."""
    lines = text.split("\n")
    if not lines or not lines[0].strip():
        raise DelegateError("헬퍼 출력이 비어있음")
    try:
        meta = json.loads(lines[0])
    except json.JSONDecodeError as e:
        raise DelegateError(f"meta 파싱 실패: {e}")
    dicts = []
    try:
        for ln in lines[1:]:
            if not ln.strip():
                continue
            dicts.append(json.loads(ln))
    except ValueError as e:                          # JSONDecodeError 포함
        raise DelegateError(f"이벤트 파싱 실패: {e}")
    return meta, dicts


def _run_staged(posix_root, target_root, origin_label, distro=None,
                on_progress=None, runner=None, workdir=None):
    """스테이징→실행→회수→경로재작성 코어. runner=None이면 wsl.exe(-d distro) 경유(distro 필수)."""
    own_tmp = workdir is None
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="agentrace-delegate-"))
    try:
        shim, helper_sha = stage_helper(workdir)
        out_path = workdir / "out.jsonl"
        origin_tag = f"origin:{origin_label}"
        if runner is None:
            if not distro:
                raise DelegateError("distro 미지정(wsl.exe 실행 불가)")
            argv = ["wsl.exe", "-d", distro, "--", "python3", "-B", "-E", "-s",
                    win_to_wsl_path(shim), posix_root,
                    "--origin-tag", origin_tag, "--out", win_to_wsl_path(out_path)]
        else:
            argv = list(runner) + [str(shim), posix_root,
                                   "--origin-tag", origin_tag, "--out", str(out_path)]
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace")
        except OSError as e:
            raise DelegateError(f"헬퍼 실행 불가: {e}")
        for line in proc.stdout:                    # TOTAL/PROGRESS 스트림 포워딩
            parts = line.split()
            if len(parts) == 2 and parts[0] == "TOTAL" and parts[1].isdigit():
                if on_progress:
                    on_progress(0, int(parts[1]))
            elif len(parts) == 3 and parts[0] == "PROGRESS" and parts[1].isdigit():
                if on_progress:
                    on_progress(int(parts[1]), int(parts[2]))
        stderr_tail = (proc.stderr.read() or "")[:300]
        rc = proc.wait()
        if rc != 0:
            raise DelegateError(f"헬퍼 rc={rc}: {stderr_tail}")
        try:
            text = out_path.read_text(encoding="utf-8")
        except OSError as e:
            raise DelegateError(f"출력 회수 실패: {e}")
        meta, dicts = _parse_out_text(text)
        events = []
        try:
            for d in dicts:
                d["source"]["file"] = rewrite_prefix(d["source"]["file"], posix_root, target_root)
                events.append(Event.from_dict(d))
        except (KeyError, TypeError) as e:
            raise DelegateError(f"이벤트 복원 실패: {e!r}")
        if len(events) != meta.get("events"):
            raise DelegateError(f"이벤트 수 불일치: meta={meta.get('events')} 실제={len(events)}")
        manifest = {rewrite_prefix(k, posix_root, target_root): v
                    for k, v in (meta.get("manifest") or {}).items()}
        warnings = []
        for warning in meta.get("warnings") or []:
            row = dict(warning)
            if isinstance(row.get("file"), str):
                row["file"] = rewrite_prefix(row["file"], posix_root, target_root)
            # 6단계 sqlite_sidecar_missing.missing[]도 경로다 — file만 바꾸면 한 경고 안에
            # UNC/POSIX가 섞여 Windows 조사자가 못 여는 경로가 보고서에 실린다.
            if isinstance(row.get("missing"), list):
                row["missing"] = [rewrite_prefix(p, posix_root, target_root)
                                  if isinstance(p, str) else p for p in row["missing"]]
            warnings.append(row)
        return {"events": events,
                "manifest": {k: manifest[k] for k in sorted(manifest)},
                "warnings": warnings,
                "sqlite_support": meta.get("sqlite_support") or {},
                "timings": meta.get("timings") or {},
                "helper_sha256": helper_sha}
    finally:
        if own_tmp:
            shutil.rmtree(workdir, ignore_errors=True)

"""빌드된 exe 안을 열어 **소스와 대조**한다 — 25단계.

    python3 packaging/verify-exe.py [dist/AgenTrace.exe]

`.spec` 은 `hiddenimports = []` 라 파이썬 모듈은 PyInstaller 자동탐지에 맡긴다. 자동탐지는
import 문을 따라가므로 새 모듈이 조용히 빠질 수 있다. **정적 자산은 더 나쁘다** — `datas` 로
복사되는 것이라 자동탐지가 아예 없고, 옛 사본이 박혀도 빌드는 성공한다. 그러면 exe 만
깨진 화면으로 나간다(브라우저로 돌리면 멀쩡해서 못 찾는다).

그래서 두 축을 다르게 본다.
  - 코드: PYZ 아카이브에 모듈 이름이 있는가 (있으면 그 빌드에 프리즈된 것)
  - 자산: 번들 안 사본과 저장소 원본의 **sha256 이 같은가** (눈으로 보면 못 잡는다)

exe 를 실행하지 않는다 — 파일만 읽는다.
"""
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_EXE = REPO / "dist" / "AgenTrace.exe"

# 23·24단계가 실제로 쓰는 것들. 여기 빠지면 exe 에서만 기능이 사라진다.
REQUIRED_MODULES = (
    "clfx.sources.markers",        # 23단계 신규 — 원격제어 마커
    "clfx.sources.claude", "clfx.sources.codex", "clfx.sources",
    "clfx.codex_parser", "clfx.codex_sqlite",
    "clfx.web.api", "clfx.web.server", "clfx.parser", "clfx.wsl_delegate",
)
# `clfx.wsl_helper` 는 **일부러 여기 없다.** exe 프로세스가 import 하지 않는다 —
# wsl_delegate 가 shim 문자열(`from clfx.wsl_helper import main`)을 파일로 써서
# WSL 안의 **다른** python3 로 실행한다. 그래서 PYZ 가 아니라 clfx_src(datas) 로
# 실려야 맞고, 아래 clfx_src 해시 대조가 그 축을 본다.
# 여기 되돌려 넣고 --hidden-import 를 추가하면 안 쓰는 모듈을 프리즈하는 것뿐이다.
REQUIRED_ASSETS = ("index.html", "app.js", "app.css",
                   "view.html", "view.js", "forensic-views.js", "logo.png")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_archive(exe):
    """onefile exe → (PYZ 안 모듈 이름 집합, {번들경로: bytes}).

    PyInstaller 의 CArchiveReader/ZlibArchiveReader 를 쓴다. 손으로 오프셋을 뜯으면
    포맷이 바뀔 때 조용히 틀린 답을 내므로, 그 빌드를 만든 라이브러리에게 묻는다."""
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(exe))
    modules, assets = set(), {}
    for name, entry in archive.toc.items():
        # TOC 값은 (offset, 압축길이, 원본길이, 압축플래그, typecode) — typecode 는 **[4]** 다.
        # [3](압축플래그)을 typecode 로 읽으면 전부 "없음"으로 나온다(실제로 한 번 그랬다).
        typecode = entry[4]
        if typecode == "z":                       # PYZ 아카이브
            data = archive.extract(name)
            pyz = Path(exe).parent / ("_" + Path(name).name + ".tmp")
            pyz.write_bytes(data)
            try:
                from PyInstaller.archive.readers import ZlibArchiveReader
                modules |= set(ZlibArchiveReader(str(pyz)).toc)
            finally:
                pyz.unlink(missing_ok=True)
        elif typecode in ("x", "b"):              # datas(비바이너리/바이너리 파일)
            assets[name.replace("\\", "/")] = archive.extract(name)
        elif typecode in ("m", "M", "s"):         # 아카이브 밖 순수 모듈·스크립트
            modules.add(name)
    return modules, assets


def main(argv):
    exe = Path(argv[1]) if len(argv) > 1 else DEFAULT_EXE
    if not exe.is_file():
        print(f"exe 가 없다: {exe}\n  packaging/build-exe.bat 를 먼저 돌려라.")
        return 2
    print(f"대상: {exe}  {exe.stat().st_size / 1048576:.1f}MB")
    modules, assets = read_archive(exe)
    print(f"PYZ 모듈 {len(modules):,}개 · 번들 자산 {len(assets):,}개\n")

    failures = []

    print("── 코드(자동탐지) ──")
    for name in REQUIRED_MODULES:
        ok = name in modules
        print(f"  {'OK ' if ok else '없음'}  {name}")
        if not ok:
            failures.append(f"모듈 누락: {name} — .spec 의 hiddenimports 에 추가해야 한다")

    print("\n── 정적 자산(해시 대조) ──")
    static = REPO / "clfx" / "web" / "static"
    for name in REQUIRED_ASSETS:
        source = static / name
        if not source.is_file():
            failures.append(f"소스 자산 없음: {source}")
            print(f"  없음  {name}  (소스에 없다)")
            continue
        want = sha256(source)
        key = f"clfx/web/static/{name}"
        blob = assets.get(key)
        if blob is None:
            failures.append(f"자산 누락: {key}")
            print(f"  없음  {name}")
            continue
        got = hashlib.sha256(blob).hexdigest()
        same = got == want
        print(f"  {'OK  ' if same else '불일치'}  {name:<20} {got[:16]}"
              + ("" if same else f"  ≠ 소스 {want[:16]}"))
        if not same:
            failures.append(f"자산이 낡았다: {key} — 번들 {got[:16]} ≠ 소스 {want[:16]}. "
                            "build/ 캐시를 지우고 다시 빌드해라")

    # clfx_src(WSL 위임용 소스 사본)도 같은 이유로 낡을 수 있다.
    print("\n── WSL 위임 소스 사본(clfx_src) ──")
    for rel in ("wsl_helper.py", "sources/markers.py", "web/api.py"):
        key = f"clfx_src/{rel}"
        blob = assets.get(key)
        source = REPO / "clfx" / rel
        if blob is None:
            failures.append(f"clfx_src 누락: {key}")
            print(f"  없음  {rel}")
            continue
        got, want = hashlib.sha256(blob).hexdigest(), sha256(source)
        same = got == want
        print(f"  {'OK  ' if same else '불일치'}  {rel:<20} {got[:16]}")
        if not same:
            failures.append(f"clfx_src 가 낡았다: {key}")

    print()
    if failures:
        print("실패:")
        for line in failures:
            print("  · " + line)
        return 1
    print("전부 일치 — 이 exe 는 지금 소스로 만들어졌다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

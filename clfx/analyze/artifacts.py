"""아티팩트 포렌식 계층 — read-only FS (해시·stat·경로변환·클러스터·JOIN).

절대 불변식:
- READ-ONLY FS: open(path,"rb")/os.stat/os.walk(followlinks=False)만.
- 완전성: tmp 전수 스캔, 모든 정규파일 해시(cap/sample/top-N 절단 금지). 큰 파일도 스트리밍 전량.
- 결정성: 모든 출력 정렬. 병렬이어도 그룹핑·정렬 결정적.
"""

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from clfx.cli import _origin_label
from clfx.event import ts_key


# ── Task 1: 경로 변환 ──────────────────────────────────────────────
def _wsl_base_of(root):
    r"""root(\\wsl.localhost\Ubuntu\home\u\.claude) → \\wsl.localhost\Ubuntu. wsl 루트 아니면 None."""
    s = str(root)
    m = re.match(r"^(\\\\wsl\.localhost\\[^\\]+)", s) or re.match(r"^(\\\\wsl\$\\[^\\]+)", s)
    return m.group(1) if m else None


def resolve_candidates(target, root):
    """event.target(파일경로) → 분석 OS서 접근 가능한 실제 경로 후보. 비파일이면 []."""
    t = (target or "").strip()
    if not t or t.startswith("[") or "://" in t:        # [Pasted/Image], URL → 비파일
        return []
    on_nt = (os.name == "nt")
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", t)            # WSL이 본 Windows 드라이브
    if m:
        drive, rest = m.group(1).upper(), m.group(2)
        return [f"{drive}:\\" + rest.replace("/", "\\")] if on_nt else [t]
    if re.match(r"^[a-zA-Z]:[\\/]", t):                  # Windows 절대경로
        if on_nt:
            return [t.replace("/", "\\")]
        return ["/mnt/" + t[0].lower() + "/" + t[2:].replace("\\", "/").lstrip("/")]
    if t.startswith("/"):                                # POSIX 절대경로(WSL distro fs)
        if on_nt:
            base = _wsl_base_of(root)
            return [base + t.replace("/", "\\")] if base else []
        return [t]
    return []                                            # 상대/비경로 skip


def resolve_existing(target, root):
    """후보 중 실제 존재하는 첫 경로(없으면 None). read-only stat만."""
    for c in resolve_candidates(target, root):
        try:
            if os.path.isfile(c):
                return c
        except OSError:
            continue
    return None


# ── Task 2: 해시 + stat (read-only) ────────────────────────────────
def hash_file(path, chunk=1 << 16):
    """SHA-256 스트리밍(메모리 bound). read-only."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def _iso(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def stat_file(path):
    st = os.stat(path)
    owner = None
    if os.name != "nt":
        try:
            import pwd
            owner = pwd.getpwuid(st.st_uid).pw_name
        except Exception:
            owner = None
    return {"size": st.st_size, "mtime": _iso(st.st_mtime), "owner": owner}


# ── Task 3: ① 해시 클러스터(복제/유출 탐지) + tmp 전수 스캔 ─────────
_FILE_ACTIONS = {"read", "write", "paste", "upload"}


def tmp_roots(roots):
    r"""각 root서 tmp 디렉터리 도출. 존재하는 것만, 중복제거·정렬."""
    out = set()
    on_nt = (os.name == "nt")
    for root in roots or []:
        s = str(root)
        if on_nt:
            base = _wsl_base_of(s)
            if base:
                out.add(base + r"\tmp")
                out.add(base + r"\var\tmp")
            mu = re.match(r"^([a-zA-Z]:\\Users\\[^\\]+)", s)
            if mu:
                out.add(mu.group(1) + r"\AppData\Local\Temp")
            out.add(r"C:\tmp")
            for k in ("TEMP", "TMP"):
                v = os.environ.get(k)
                if v:
                    out.add(v)
        else:
            out.add("/tmp")
            out.add("/var/tmp")
    existing = [d for d in out if os.path.isdir(d)] if not on_nt else list(out)
    return sorted(existing)


def _walk_tmp(tmp_dirs):
    """각 tmp_dir을 os.walk(followlinks=False) 전수.

    반환: (files, walk_errors)
    - files: 모든 정규파일 경로(정렬, 중복제거).
    - walk_errors: stat/lstat 자체가 OSError로 실패한 '접근 실패' 파일들
      ({path, reason}). 비정규파일(디바이스/소켓/fifo/symlink)은 errors 아님 → skip.
    완전성 불변식: 실재하지만 접근 실패한 정규파일도 흔적 없이 사라지지 않게 전량 기록.
    """
    import stat as _stat
    files = []
    walk_errors = {}   # path → reason (결정성: 정렬 위해 dict)
    for d in tmp_dirs or []:
        if not os.path.isdir(d):
            continue
        for dirpath, _dirnames, filenames in os.walk(d, followlinks=False):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                try:
                    # lstat: symlink을 따라가지 않고 엔트리 자체를 stat(read-only).
                    st = os.lstat(p)
                except OSError as e:
                    # stat 자체 실패 = 접근 실패(권한 거부, 레이스 삭제 등) → 기록.
                    walk_errors[p] = type(e).__name__
                    continue
                # symlink·비정규파일(디바이스/소켓/fifo)은 정상 skip(errors 아님).
                if _stat.S_ISLNK(st.st_mode):
                    continue
                if _stat.S_ISREG(st.st_mode):
                    files.append(p)
    errors = [{"path": p, "reason": r} for p, r in walk_errors.items()]
    return sorted(set(files)), errors


RETENTION_DAYS = 30        # Claude tmp 보존기간 실측치(docs/실측-temp-원본보존-원리.md)


def tmp_retention(tmp_dirs, now_epoch=None):
    """tmp 전수 → 각 정규파일 보존기간 메타. read-only stat. _walk_tmp 재사용.
    now_epoch: 나이 계산 기준 현재시각(테스트 주입용; None이면 time.time()).
    반환 {"retention":[...정렬: path...], "errors":[...정렬: path...]}."""
    import time
    if now_epoch is None:
        now_epoch = time.time()
    files, walk_errors = _walk_tmp(tmp_dirs)
    # _walk_tmp의 errors는 [{path, reason}, ...] — 그대로 누적(접근 실패 흔적 보존).
    errors = [{"path": e["path"], "reason": e["reason"]} for e in walk_errors]
    rows = []
    for p in files:
        try:
            st = os.stat(p)
        except OSError as e:
            errors.append({"path": p, "reason": type(e).__name__})   # 완전성: 조용한 누락 금지
            continue
        age_days = (now_epoch - st.st_mtime) / 86400.0
        expires = RETENTION_DAYS - age_days
        rows.append({
            "path": p,
            "size": st.st_size,
            "mtime": _iso(st.st_mtime),
            "atime": _iso(st.st_atime),
            "age_days": round(age_days, 2),
            "expires_in_days": round(expires, 2) if expires > 0 else 0,
        })
    rows.sort(key=lambda r: r["path"])
    errors.sort(key=lambda e: e["path"])
    return {"retention": rows, "errors": errors}


def hash_clusters(events_with_root, roots=None, tmp_dirs=None):
    """참조 파일 해시 + tmp 전수 스캔 → 동일 해시 군집(복제/유출)."""
    # 1. 참조 파일: file-action 이벤트 → resolve_existing.
    referenced = {}   # real_path → 대표 이벤트 정보
    missing = 0
    for ev, root in events_with_root or []:
        if ev.action not in _FILE_ACTIONS:
            continue
        if not resolve_candidates(ev.target, root):
            continue                       # 비파일 target skip(missing 아님)
        real = resolve_existing(ev.target, root)
        if real is None:
            missing += 1
            continue
        rec = {
            "path": real,
            "in_tmp": False,
            "origin": _origin_label(root),
            "referenced": True,
            "action": ev.action,
            "actor": ev.actor,
            "ts": ev.ts,
            "tags": list(ev.tags or []),
            "source": {"file": ev.source.file, "line": ev.source.line},
        }
        # 같은 실경로 여러 이벤트면 결정적으로 1개만(가장 늦은 ts 우선).
        prev = referenced.get(real)
        if prev is None or ts_key(ev.ts) >= ts_key(prev["ts"]):
            referenced[real] = rec

    # 2. tmp 파일: 전수 스캔.
    if tmp_dirs is None:
        tmp_dirs = tmp_roots(roots)
    tmp_files, walk_errors = _walk_tmp(tmp_dirs)
    tmp_set = set(tmp_files)

    # 3. 병렬 해시(전수, skip 금지). 실패 → errors.
    #    walk 단계 접근실패(정규파일이나 stat 불가)도 errors에 병합 — 흔적 보존.
    targets = sorted(set(referenced.keys()) | tmp_set)
    hashes_by_path = {}
    errors = list(walk_errors)
    if targets:
        N = len(targets)
        with ThreadPoolExecutor(max_workers=min(16, max(1, N))) as ex:
            results = list(ex.map(lambda p: (p, _safe_hash(p)), targets))
        for p, (digest, err) in results:
            if err is not None:
                errors.append({"path": p, "reason": err})
            else:
                hashes_by_path[p] = digest

    scanned = len(hashes_by_path)
    tmp_scanned = sum(1 for p in tmp_set if p in hashes_by_path)

    # 4. 해시별 그룹 → count>1 군집만.
    groups = {}
    for p, digest in hashes_by_path.items():
        groups.setdefault(digest, []).append(p)

    hashes = []
    for digest, paths in groups.items():
        if len(paths) < 2:
            continue
        path_recs = []
        secret = False
        in_tmp = False
        size = None
        for p in sorted(paths):
            if size is None:
                try:
                    size = os.stat(p).st_size
                except OSError:
                    size = None
            p_in_tmp = p in tmp_set
            if p_in_tmp:
                in_tmp = True
            ref = referenced.get(p)
            if ref is not None:
                rec = dict(ref)
                rec["in_tmp"] = p_in_tmp
                if any(t in ("secret", "pii") for t in rec.get("tags", [])):
                    secret = True
                path_recs.append(rec)
            else:
                path_recs.append({
                    "path": p,
                    "in_tmp": p_in_tmp,
                    "origin": "other",
                    "referenced": False,
                    "action": None,
                    "actor": None,
                    "ts": None,
                    "tags": [],
                    "source": None,
                })
        leak_suspect = len(paths) > 1
        if secret and in_tmp:
            reason = "시크릿 내용이 원본과 tmp 사본에 동일 존재 — 강한 유출 의심"
        elif in_tmp:
            reason = "동일 내용이 원본과 tmp 사본(2경로)에 존재"
        else:
            reason = f"동일 내용이 {len(paths)}개 경로에 존재"
        hashes.append({
            "sha256": digest,
            "size": size if size is not None else 0,
            "count": len(paths),
            "secret": secret,
            "in_tmp": in_tmp,
            "leak_suspect": leak_suspect,
            "reason": reason,
            "paths": path_recs,
        })

    hashes.sort(key=lambda c: (-c["count"], c["sha256"]))
    errors.sort(key=lambda e: e["path"])
    return {
        "scanned": scanned,
        "missing": missing,
        "tmp_scanned": tmp_scanned,
        "tmp_roots": sorted([d for d in (tmp_dirs or []) if os.path.isdir(d)]),
        "errors": errors,
        "hashes": hashes,
    }


def _safe_hash(path):
    """(digest, None) 또는 (None, reason). 조용히 누락 금지."""
    try:
        return (hash_file(path), None)
    except Exception as e:
        return (None, type(e).__name__)


# ── Task 4: ④ 주체왜곡 보정 JOIN ──────────────────────────────────
def attribution_join(events_with_root):
    """FS메타 ↔ transcript 증거 JOIN. distortion = transcript_actor=='agent'."""
    # 같은 path 여러 write 이벤트면 가장 늦은 것 기준(최종 작성자). 결정적.
    by_path = {}
    for ev, root in events_with_root or []:
        if ev.action not in ("write", "read"):
            continue
        real = resolve_existing(ev.target, root)
        if real is None:
            continue
        prev = by_path.get(real)
        # write 우선, 동급이면 늦은 ts.
        if prev is None:
            by_path[real] = (ev, root)
        else:
            pev, _ = prev
            cur_w = ev.action == "write"
            prev_w = pev.action == "write"
            if cur_w and not prev_w:
                by_path[real] = (ev, root)
            elif cur_w == prev_w and ts_key(ev.ts) >= ts_key(pev.ts):
                by_path[real] = (ev, root)

    rows = []
    for real, (ev, root) in by_path.items():
        try:
            st = stat_file(real)
        except OSError:
            continue
        fs_mtime = st["mtime"]
        mtime_matches = False
        try:
            delta = abs((ts_key(fs_mtime) - ts_key(ev.ts)).total_seconds())
            mtime_matches = delta <= 5
        except Exception:
            mtime_matches = False
        distortion = (ev.actor == "agent")
        if distortion:
            note = (
                f"파일시스템상 소유자는 계정(사람)이나, transcript 증거상 에이전트(B)가 작성 "
                f"({ev.source.file}:{ev.source.line})"
            )
        else:
            note = (
                f"transcript상 사용자(A)가 {ev.action} ({ev.source.file}:{ev.source.line})"
            )
        rows.append({
            "path": real,
            "origin": _origin_label(root),
            "fs_mtime": fs_mtime,
            "fs_size": st["size"],
            "fs_owner": st["owner"],
            "transcript_actor": ev.actor,
            "transcript_action": ev.action,
            "transcript_ts": ev.ts,
            "source": {"file": ev.source.file, "line": ev.source.line},
            "mtime_matches": mtime_matches,
            "distortion": distortion,
            "note": note,
        })

    rows.sort(key=lambda r: r["path"])
    return rows

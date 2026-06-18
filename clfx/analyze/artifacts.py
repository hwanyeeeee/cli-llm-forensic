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

from clfx import roio
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
    m = re.match(r"^\\\\wsl(?:\.localhost|\$)\\([^\\]+)(\\.*)?$", t)  # UNC WSL 경로(완전성)
    if m:
        if on_nt:
            return [t.replace("/", "\\")]                 # Windows는 UNC 직접 접근(역슬래시 정규화)
        rest = (m.group(2) or "").replace("\\", "/")      # \home\u\x → /home/u/x ; \mnt\c\x → /mnt/c/x
        return [rest] if rest else []
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
    with roio._ro_open(path, "rb") as f:        # B-2: read-only 강제 + in-memory audit 경유
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def _iso(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _stat_dict(st):
    """os.stat_result → {size, mtime(_iso), owner(pwd)}. stat_file·attribution_join·hash_clusters 공유(DRY).
    동일 st로부터 byte-identical 값 산출 — 재-stat 없이 캐시된 stat을 재사용 가능."""
    owner = None
    if os.name != "nt":
        try:
            import pwd
            owner = pwd.getpwuid(st.st_uid).pw_name
        except Exception:
            owner = None
    return {"size": st.st_size, "mtime": _iso(st.st_mtime), "owner": owner}


def stat_file(path):
    return _stat_dict(os.stat(path))


# ── Task 3: ① 해시 클러스터(복제/유출 탐지) + tmp 전수 스캔 ─────────
_FILE_ACTIONS = {"read", "write", "paste", "upload"}
# attribution_join은 {write,read}만 — 두 소비자 합집합으로 캐시 키를 덮는다(완전성).
_REF_RESOLVE_ACTIONS = _FILE_ACTIONS | {"write", "read"}


def build_reference_resolution(events_with_root):
    """OPT-2: (root, target) → {"real": 실경로 or None, "st": os.stat_result or None} 캐시.
    동일 (root,target)은 1회만 해석(중복제거). 후보 중 첫 isfile을 real로(resolve_existing 의미 복제),
    그 stat 1회를 st로 캐시. hash_clusters·attribution_join이 공유해 resolve+stat 재호출 제거.
    read-only(os.path.isfile/os.stat만). 캐시는 두 소비자가 쓰는 file-action 합집합을 덮는다."""
    cache = {}
    for ev, root in events_with_root or []:
        if ev.action not in _REF_RESOLVE_ACTIONS:
            continue
        key = (root, ev.target)
        if key in cache:
            continue
        real = None
        st = None
        for c in resolve_candidates(ev.target, root):
            try:
                if os.path.isfile(c):
                    real = c
                    break
            except OSError:
                continue
        if real is not None:
            try:
                st = os.stat(real)
            except OSError:
                st = None
        cache[key] = {"real": real, "st": st}
    return cache


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


def build_tmp_inventory(tmp_dirs):
    """OPT-1: tmp 전수를 단일 walk로 인벤토리화 — 엔트리당 lstat 1회, size/mtime/atime/mode 보존.

    반환 {"files":[{path,size,mtime,atime,mode}...정렬·중복제거], "errors":[{path,reason}...정렬]}.
    skip 의미는 기존 _walk_tmp와 동일: symlink(S_ISLNK)·비정규파일(정규 S_ISREG만 수집)은
    errors 없이 skip; 디렉터리 목록조회 실패는 onerror로, 엔트리별 lstat 실패는 errors로 기록.
    완전성: 접근 실패 정규파일도 흔적 없이 사라지지 않게 errors에 전량 기록.
    재-stat 금지를 위해 size/mtime/atime/mode를 레코드에 그대로 담는다(소비자가 재호출 불필요)."""
    import stat as _stat
    by_path = {}        # path → 레코드(중복제거; 결정성 위해 dict 후 정렬)
    walk_errors = {}    # path → reason
    for d in tmp_dirs or []:
        if not os.path.isdir(d):
            continue

        def _cb(oserr, _d=d):
            # 목록조회 불가 하위 디렉터리(권한거부 등)도 흔적 보존. late-binding 방지 default-arg.
            walk_errors[getattr(oserr, "filename", None) or _d] = type(oserr).__name__

        for dirpath, _dirnames, filenames in os.walk(d, topdown=True, followlinks=False, onerror=_cb):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                try:
                    # lstat: symlink을 따라가지 않고 엔트리 자체를 stat(read-only). 엔트리당 1회.
                    st = os.lstat(p)
                except OSError as e:
                    walk_errors[p] = type(e).__name__
                    continue
                if _stat.S_ISLNK(st.st_mode):
                    continue
                if _stat.S_ISREG(st.st_mode):
                    by_path[p] = {
                        "path": p,
                        "size": st.st_size,
                        "mtime": _iso(st.st_mtime),
                        "atime": _iso(st.st_atime),
                        "mode": st.st_mode,
                    }
    files = [by_path[p] for p in sorted(by_path)]
    errors = sorted(
        ({"path": p, "reason": r} for p, r in walk_errors.items()),
        key=lambda e: e["path"],
    )
    return {"files": files, "errors": errors}


def _resolve_inventory(tmp_dirs, inventory):
    """inventory 주입 시 그대로 사용(재-walk 금지), None이면 단일 walk로 구축(DRY)."""
    return inventory if inventory is not None else build_tmp_inventory(tmp_dirs)


def _walk_tmp(tmp_dirs):
    """OPT-1: build_tmp_inventory에서 파생하는 얇은 래퍼.

    반환: (files, walk_errors) — 기존 시그니처·반환형 동일.
    - files: 모든 정규파일 경로(정렬, 중복제거).
    - walk_errors: 접근 실패 항목 [{path, reason}...] (정렬). 비정규/symlink는 errors 아님.
    완전성 불변식: 실재하지만 접근 실패한 정규파일도 흔적 없이 사라지지 않게 전량 기록.
    """
    inv = build_tmp_inventory(tmp_dirs)
    files = [r["path"] for r in inv["files"]]   # 인벤토리가 이미 정렬·중복제거.
    return files, inv["errors"]


RETENTION_DAYS = 30        # Claude tmp 보존기간 실측치(docs/실측-temp-원본보존-원리.md)


def _epoch_from_iso(iso):
    """_iso()로 만든 'YYYY-MM-DDTHH:MM:SSZ' → epoch(초). 인벤토리 mtime/atime을 나이 계산에 재사용.
    _iso는 초 단위 truncate이므로 round-trip은 같은 초 정밀도(결정적). 재-stat 회피 전용."""
    s = iso[:-1] + "+00:00" if iso.endswith("Z") else iso
    return datetime.fromisoformat(s).timestamp()


def tmp_retention(tmp_dirs, now_epoch=None, inventory=None):
    """tmp 전수 → 각 정규파일 보존기간 메타. read-only. OPT-1: 인벤토리에서 size/mtime/atime 소싱(재-stat 금지).
    now_epoch: 나이 계산 기준 현재시각(테스트 주입용; None이면 time.time()).
    inventory: build_tmp_inventory 결과(없으면 내부 구축 — 직접호출 동작 동일).
    반환 {"retention":[...정렬: path...], "errors":[...정렬: path...]}."""
    import time
    if now_epoch is None:
        now_epoch = time.time()
    inv = _resolve_inventory(tmp_dirs, inventory)
    # 인벤토리의 접근 실패 흔적 그대로 누적(완전성).
    errors = [{"path": e["path"], "reason": e["reason"]} for e in inv["errors"]]
    rows = []
    for rec in inv["files"]:
        mtime_epoch = _epoch_from_iso(rec["mtime"])
        age_days = (now_epoch - mtime_epoch) / 86400.0
        expires = RETENTION_DAYS - age_days
        rows.append({
            "path": rec["path"],
            "size": rec["size"],
            "mtime": rec["mtime"],
            "atime": rec["atime"],
            "age_days": round(age_days, 2),
            "expires_in_days": round(expires, 2) if expires > 0 else 0,
        })
    rows.sort(key=lambda r: r["path"])
    errors.sort(key=lambda e: e["path"])
    return {"retention": rows, "errors": errors}


def hash_clusters(events_with_root, roots=None, tmp_dirs=None,
                  inventory=None, resolved=None, on_hash_progress=None):
    """참조 파일 해시 + tmp 전수 스캔 → 동일 해시 군집(복제/유출).

    OPT-1 inventory: build_tmp_inventory 결과 주입 시 재-walk/재-stat 없이 tmp size/mtime 소싱.
    OPT-2 resolved: build_reference_resolution 캐시 주입 시 resolve_existing/os.stat 재호출 제거.
    OPT-3 size-prefilter: target을 크기로 그룹핑, 같은 크기 ≥2 그룹만 SHA-256(unique-size는 미판독).
      hashes[](count≥2)는 전수 해시와 byte-identical(unique-size 단독은 콘텐츠 군집에 절대 못 낀다).
    OPT-7 on_hash_progress(done,total): 해시 진행 콜백(해시 대상 수 기준). None이면 no-op.
    완전성: 모든 파일은 최소 stat 커버(stat_verified). 미판독은 content_unread로 정직 보고."""
    # 1. 참조 파일: file-action 이벤트 → 해석(캐시 우선).
    if resolved is None:
        resolved = build_reference_resolution(events_with_root)
    referenced = {}   # real_path → 대표 이벤트 정보
    ref_size = {}     # real_path → 캐시된 stat 기반 size(None 가능)
    missing = 0
    _tk = {}          # OPT-8: 이벤트별 ts_key 1회 캐시(id 기준)
    for ev, root in events_with_root or []:
        if ev.action not in _FILE_ACTIONS:
            continue
        if not resolve_candidates(ev.target, root):
            continue                       # 비파일 target skip(missing 아님)
        entry = resolved.get((root, ev.target))
        real = entry["real"] if entry is not None else None
        if real is None:
            missing += 1
            continue
        st = entry["st"] if entry is not None else None
        ref_size[real] = st.st_size if st is not None else None
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
        # 같은 실경로 여러 이벤트면 결정적으로 1개만(가장 늦은 ts 우선). ts_key 캐시.
        ev_k = _tk.get(id(ev))
        if ev_k is None:
            ev_k = _tk[id(ev)] = ts_key(ev.ts)
        prev = referenced.get(real)
        if prev is None:
            referenced[real] = rec
        else:
            prev_k = _tk.get(id(prev))
            if prev_k is None:
                prev_k = _tk[id(prev)] = ts_key(prev["ts"])
            if ev_k >= prev_k:
                referenced[real] = rec
                _tk[id(rec)] = ev_k

    # 2. tmp 파일: 단일 인벤토리(재-walk 금지).
    if tmp_dirs is None:
        tmp_dirs = tmp_roots(roots)
    inv = _resolve_inventory(tmp_dirs, inventory)
    tmp_size = {r["path"]: r["size"] for r in inv["files"]}   # 인벤토리 size(재-stat 금지)
    tmp_set = set(tmp_size)
    walk_errors = inv["errors"]

    # 3. size-prefilter 해싱(OPT-3). target = 참조-실경로 ∪ tmp-인벤토리.
    #    크기별 그룹 → 같은 크기 ≥2인 파일만 콘텐츠 해시(unique-size는 군집 불가 → 무손실 skip).
    #    walk 단계 접근실패도 errors에 병합(완전성).
    targets = sorted(tmp_set | set(referenced.keys()))
    size_of = {}      # path → size(있으면). 참조는 ref_size, tmp는 tmp_size.
    for p in targets:
        if p in tmp_size:
            size_of[p] = tmp_size[p]
        else:
            size_of[p] = ref_size.get(p)
    size_groups = {}
    for p in targets:
        size_groups.setdefault(size_of[p], []).append(p)
    # 같은 size 그룹(멤버 ≥2)만 해시 대상. size None(stat 실패)도 그룹키로 취급 — 여러 개면 해시 시도.
    to_hash = sorted(
        p for sz, members in size_groups.items() if len(members) >= 2 for p in members
    )

    hashes_by_path = {}
    errors = list(walk_errors)
    hash_failed_dup = 0   # dup-size이지만 해시 실패 → errors로 간 파일 수(검산식용)
    if to_hash:
        N = len(to_hash)
        done = 0
        with ThreadPoolExecutor(max_workers=min(32, max(1, N))) as ex:
            for p, (digest, err) in ex.map(lambda p: (p, _safe_hash(p)), to_hash):
                done += 1
                if on_hash_progress is not None:
                    on_hash_progress(done, N)
                if err is not None:
                    errors.append({"path": p, "reason": err})
                    hash_failed_dup += 1
                else:
                    hashes_by_path[p] = digest

    # 투명 카운터(OPT-3). stat 커버 = 참조 해석 성공 + tmp 인벤토리(접근 실패는 inventory.errors).
    hashed = len(hashes_by_path)
    stat_verified = len(targets)
    content_unread = stat_verified - hashed - hash_failed_dup
    # 검산: 모든 stat-커버 파일은 해시되거나 / 미판독(unique-size)이거나 / 해시 실패(errors)다.
    assert stat_verified == hashed + content_unread + hash_failed_dup
    scanned = stat_verified                              # 완전성: 전수 stat 커버를 정직 보고.
    tmp_scanned = len(tmp_set)                           # tmp 전수 stat 커버.

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
                size = size_of.get(p)            # OPT 캐시 size(재-stat 금지). None 가능.
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
        has_ref = any(r.get("referenced") for r in path_recs)
        has_tmp = in_tmp
        leak_suspect = has_ref and has_tmp   # 참조 파일 내용이 tmp 사본에도 = 진짜 유출 신호
        tmp_only = not has_ref               # referenced 0 = tmp 내부 중복(설치/캐시 노이즈)
        if has_ref and has_tmp and secret:
            reason = "시크릿 참조 파일이 tmp 사본과 동일 해시 — 강한 유출 의심"
        elif has_ref and has_tmp:
            reason = "참조 파일이 tmp 사본과 동일 해시(유출 의심)"
        elif tmp_only:
            reason = "tmp 내부 중복(설치/캐시 등 — 유출 아님)"
        else:
            reason = f"동일 내용이 {len(paths)}개 경로에 존재"
        # [R4] 빈 파일(0B)은 유출할 내용이 없음 → 분류만 덮어쓴다(전수 스캔·그룹핑은 유지).
        #      size==0일 때만 적용. size None(stat 실패)은 0이 아님 → 건드리지 않음.
        if size == 0:
            leak_suspect = False
            tmp_only = True
            reason = "빈 파일(0B) — 내용 없음, 유출 아님"
        hashes.append({
            "sha256": digest,
            "size": size if size is not None else 0,
            "count": len(paths),
            "secret": secret,
            "in_tmp": in_tmp,
            "leak_suspect": leak_suspect,
            "tmp_only": tmp_only,
            "reason": reason,
            "paths": path_recs,
        })

    hashes.sort(key=lambda c: (-c["count"], c["sha256"]))
    errors.sort(key=lambda e: e["path"])

    # 5. 원본→동일해시 tmp 검색용 인덱스: 실제 해시된 tmp 파일만(OPT-3 — dup-size).
    #    sha256 → [{path,size,mtime}...] (path 정렬, 결정적). size/mtime은 인벤토리에서(재-stat 금지).
    inv_by_path = {r["path"]: r for r in inv["files"]}
    tmp_hash_index = {}
    for p in sorted(tmp_set):
        digest = hashes_by_path.get(p)
        if digest is None:
            continue
        rec = inv_by_path.get(p)
        if rec is None:
            continue
        tmp_hash_index.setdefault(digest, []).append(
            {"path": p, "size": rec["size"], "mtime": rec["mtime"]})

    # B-1 acquisition manifest(ADDITIVE — 기존 키/값 불변): 콘텐츠를 실제로 읽은 파일의
    #   이미-계산된 해시를 재해시 없이 표면화. acquired_hashes = hashes_by_path 사본
    #   (real_path → sha256, 참조+tmp 중 콘텐츠 판독된 파일). stat_only = stat 커버됐으나
    #   콘텐츠 미판독(unique-size = targets − to_hash) — 가짜 해시 없이 경로만 정렬 보고.
    acquired_hashes = dict(hashes_by_path)
    stat_only = sorted(set(targets) - set(to_hash))

    return {
        "scanned": scanned,
        "missing": missing,
        "tmp_scanned": tmp_scanned,
        "hashed": hashed,
        "stat_verified": stat_verified,
        "content_unread": content_unread,
        "tmp_roots": sorted([d for d in (tmp_dirs or []) if os.path.isdir(d)]),
        "errors": errors,
        "hashes": hashes,
        "tmp_hash_index": tmp_hash_index,
        "acquired_hashes": acquired_hashes,
        "stat_only": stat_only,
    }


def _safe_hash(path):
    """(digest, None) 또는 (None, reason). 조용히 누락 금지."""
    try:
        return (hash_file(path), None)
    except Exception as e:
        return (None, type(e).__name__)


def build_tmp_hash_index(inventory):
    """OPT-3: 인벤토리 전수(unique-size 포함) SHA-256 해시 → sha256: [{path,size,mtime}...정렬].
    서버 lazy reverse-search 전용(스캔 중 아님 — 비싼 전수 해시). _safe_hash 재사용; 해시 실패 파일은
    skip(그 stat 실패는 inventory.errors에 이미 기록됨). 결정적(path 정렬, 병렬이어도 결과 결정적)."""
    files = inventory.get("files", []) if inventory else []
    if not files:
        return {}
    paths = [r["path"] for r in files]
    size_mtime = {r["path"]: (r["size"], r["mtime"]) for r in files}
    N = len(paths)
    with ThreadPoolExecutor(max_workers=min(32, max(1, N))) as ex:
        results = list(ex.map(lambda p: (p, _safe_hash(p)), paths))
    by_digest = {}
    for p, (digest, err) in results:
        if err is not None or digest is None:
            continue
        sz, mt = size_mtime[p]
        by_digest.setdefault(digest, []).append({"path": p, "size": sz, "mtime": mt})
    for d in by_digest:
        by_digest[d].sort(key=lambda m: m["path"])
    return by_digest


# ── Task 4: ④ 주체왜곡 보정 JOIN ──────────────────────────────────
def attribution_join(events_with_root, resolved=None):
    """FS메타 ↔ transcript 증거 JOIN. distortion = transcript_actor=='agent'.
    OPT-2 resolved: build_reference_resolution 캐시 주입 시 resolve_existing/os.stat 재호출 제거.
      캐시된 stat(st)을 fs_mtime/fs_size/fs_owner에 재사용(_stat_dict로 byte-identical). None이면 기존대로."""
    # 같은 path 여러 write 이벤트면 가장 늦은 것 기준(최종 작성자). 결정적.
    by_path = {}
    _tk = {}          # OPT-8: 이벤트별 ts_key 1회 캐시(id 기준)

    def _key(ev):
        k = _tk.get(id(ev))
        if k is None:
            k = _tk[id(ev)] = ts_key(ev.ts)
        return k

    for ev, root in events_with_root or []:
        if ev.action not in ("write", "read"):
            continue
        if resolved is not None:
            entry = resolved.get((root, ev.target))
            real = entry["real"] if entry is not None else None
            st_cached = entry["st"] if entry is not None else None
        else:
            real = resolve_existing(ev.target, root)
            st_cached = None
        if real is None:
            continue
        prev = by_path.get(real)
        # write 우선, 동급이면 늦은 ts.
        if prev is None:
            by_path[real] = (ev, root, st_cached)
        else:
            pev, _, _ = prev
            cur_w = ev.action == "write"
            prev_w = pev.action == "write"
            if cur_w and not prev_w:
                by_path[real] = (ev, root, st_cached)
            elif cur_w == prev_w and _key(ev) >= _key(pev):
                by_path[real] = (ev, root, st_cached)

    rows = []
    for real, (ev, root, st_cached) in by_path.items():
        try:
            st = _stat_dict(st_cached) if st_cached is not None else stat_file(real)
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

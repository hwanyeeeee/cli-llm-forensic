"""B-2: 공유 read-only open + in-memory acquisition audit.

포렌식 불변식(READ-ONLY FS)의 단일 강제 지점. 분석 대상 파일시스템에는
오직 읽기만 한다 — _ro_open은 read 외 mode를 거부한다. 모든 open 호출을
in-memory audit 리스트에 (path, mode)로 기록한다(증거 출처 attestation).
디스크 쓰기 0(매니페스트·감사 전부 메모리). stdlib만.

parse는 32 스레드에서 병렬 실행 → audit append는 threading.Lock으로 보호.
"""
import threading

# read로 인정하는 mode(이것 외엔 거부). 분석 FS는 절대 변형하지 않는다.
_READ_MODES = ("r", "rb")

_audit = []                 # [(str path, str mode)] — open될 때마다 append (in-memory, zero disk)
_lock = threading.Lock()    # parse 32-thread 동시 append 보호


def _ro_open(path, mode="rb", **kw):
    """read-only open. read 외 mode면 ValueError로 거부(쓰기·생성·갱신 차단).

    성공 경로: (str(path), mode)를 audit에 lock 하에 기록 후 open(path, mode, **kw).
    encoding/errors 등 kwargs는 그대로 통과(텍스트/바이너리 양쪽 지원)."""
    if mode not in _READ_MODES:
        raise ValueError("read-only: refusing mode " + str(mode))
    with _lock:
        _audit.append((str(path), mode))
    return open(path, mode, **kw)


def audit_records():
    """기록된 모든 open을 [{"path","mode"}...] (path,mode) 정렬로 반환(결정적)."""
    with _lock:
        snapshot = list(_audit)
    return [{"path": p, "mode": m} for p, m in sorted(snapshot)]


def modes_seen():
    """관측된 distinct mode를 정렬해 반환. read 강제이므로 {r,rb}의 부분집합."""
    with _lock:
        modes = {m for _p, m in _audit}
    return sorted(modes)


def reset_audit():
    """audit 비우기(스캔 시작마다 호출). in-memory만, 디스크 미접근."""
    with _lock:
        _audit.clear()


def write_delete_rename_ops():
    """항상 0 — 이 도구는 write/delete/rename syscall을 전혀 발행하지 않는다.
    attestation을 위해 정적 보장값으로 노출(실제 카운터가 아니라 불변식의 표면화)."""
    return 0

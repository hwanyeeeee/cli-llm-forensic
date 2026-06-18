import base64


def resolve_paste(item: dict, source) -> "str | None":
    """display→pastedContents→paste-cache 3단계의 마지막 단계.
    content 직접 보유면 그대로, contentHash면 paste-cache/<hash>.txt 읽음. 없으면 None."""
    if item.get("content") is not None:
        return item["content"]
    h = item.get("contentHash")
    if not h:
        return None
    p = source.paste_cache_path(h)
    # exists() precheck 제거 → 직접 read 시도(파일당 syscall 1회 절감).
    # 캐시 파일 없음/접근 불가(OSError·FileNotFoundError)면 None — 기존 missing-cache와 동일(무손실).
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except (OSError, FileNotFoundError):
        return None


def decode_image(part: dict) -> bytes:
    """transcript message.content[] 의 type:image 파트 → 원본 bytes.
    누락/손상 파트는 b"" 반환(포렌식 배치 중 크래시 방지)."""
    src = part.get("source") if isinstance(part, dict) else None
    data = src.get("data") if isinstance(src, dict) else None
    if not data:
        return b""
    try:
        return base64.b64decode(data)
    except Exception:
        return b""

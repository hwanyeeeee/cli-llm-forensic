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
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="ignore")


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

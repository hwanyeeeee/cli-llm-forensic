import base64
from clfx.sources.claude import ClaudeSource
from clfx.paste import resolve_paste, decode_image
from tests.conftest import ENV_BODY, PNG_1x1_B64

def test_resolve_content_direct(built_root):
    assert resolve_paste({"type":"text","content":"HELLO"}, ClaudeSource(built_root)) == "HELLO"

def test_resolve_via_paste_cache(built_root):
    src = ClaudeSource(built_root)
    item = next(iter(src.history_records())).obj["pastedContents"]["1"]
    assert "contentHash" in item                      # 골든은 hash 경로
    assert resolve_paste(item, src) == ENV_BODY

def test_resolve_missing_cache_returns_none(built_root):
    assert resolve_paste({"type":"text","contentHash":"deadbeef"}, ClaudeSource(built_root)) is None

def test_decode_image_roundtrips_png():
    part = {"type":"image","source":{"type":"base64","data":PNG_1x1_B64}}
    raw = decode_image(part)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"            # PNG 매직
    assert raw == base64.b64decode(PNG_1x1_B64)

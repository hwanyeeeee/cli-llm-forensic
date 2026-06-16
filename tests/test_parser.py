from clfx.sources.claude import ClaudeSource
from clfx.parser import parse_source
from tests.conftest import ENV_BODY

def _events(root): return list(parse_source(ClaudeSource(root)))

def test_paste_event_from_history(built_root):
    evs = _events(built_root)
    pastes = [e for e in evs if e.action == "paste"]
    assert pastes and all(e.actor == "user" for e in pastes)
    assert ENV_BODY.strip() in pastes[0].preview        # 본문이 사슬 끝까지 따라가 들어옴
    # contentHash 붙여넣기 → source는 본문이 실제 든 paste-cache/<hash>.txt
    # (event-schema §규칙: 증거 추적). 골든 픽스처(built_root)는 contentHash 경로.
    assert pastes[0].source.file.endswith(".txt")
    assert "paste-cache" in pastes[0].source.file
    assert pastes[0].source.line == 1

def test_paste_inline_content_keeps_history_source(tmp_path):
    # 인라인 content 붙여넣기 → 본문이 history 줄 안에 있으므로 source는 history.jsonl
    from tests.conftest import make_history, write_jsonl
    root = tmp_path / "dot-claude"
    write_jsonl(root / "history.jsonl",
                make_history([{"display": "d", "items": [{"content": "INLINE_PASTE_BODY"}]}]))
    pastes = [e for e in parse_source(ClaudeSource(root)) if e.action == "paste"]
    assert pastes and pastes[0].preview == "INLINE_PASTE_BODY"
    assert pastes[0].source.file.endswith("history.jsonl")
    assert pastes[0].source.line == 1

def test_read_event_is_agent(built_root):
    reads = [e for e in _events(built_root) if e.action == "read"]
    assert {e.target.rsplit("/",1)[-1] for e in reads} >= {".env","config.py","id_rsa",".npmrc"}
    assert all(e.actor == "agent" for e in reads)
    assert all(e.source.line >= 1 for e in reads)

def test_prompt_event_is_user(built_root):
    prompts = [e for e in _events(built_root) if e.action == "prompt"]
    assert prompts and all(e.actor == "user" for e in prompts)

def test_every_event_has_source(built_root):
    assert all(e.source.file and e.source.line >= 1 for e in _events(built_root))

def test_non_event_types_dont_crash(built_root):
    # permission-mode/agent-name/file-history-snapshot/thinking 가 있어도 예외 없음
    assert _events(built_root)   # 그냥 완주

def test_history_contenthash_missing_cache_uses_history_source(tmp_path):
    # contentHash인데 paste-cache 파일이 없으면 없는 파일을 증거로 지목하면 안 됨 → history.jsonl 유지
    from tests.conftest import make_history, write_jsonl
    root = tmp_path / "dot-claude"
    write_jsonl(root / "history.jsonl",
                make_history([{"display": "d", "items": [{"contentHash": "deadbeefdeadbeef"}]}]))
    # paste-cache 파일은 일부러 만들지 않음
    pastes = [e for e in parse_source(ClaudeSource(root)) if e.action == "paste"]
    assert pastes
    assert pastes[0].source.file.endswith("history.jsonl")
    assert pastes[0].source.line == 1
    assert "<unresolved>" in pastes[0].preview

def _user_record(content):
    return {"type": "user", "sessionId": "s", "timestamp": "2026-06-11T02:00:00Z",
            "message": {"role": "user", "content": content}}

def _parse_records(tmp_path, records):
    from tests.conftest import write_jsonl
    root = tmp_path / "dot-claude"
    write_jsonl(root / "projects" / "-p" / "s.jsonl", records)
    return list(parse_source(ClaudeSource(root)))

def test_user_record_image_and_real_text_emit_both(tmp_path):
    from tests.conftest import PNG_1x1_B64
    evs = _parse_records(tmp_path, [_user_record([
        {"type": "text", "text": "진짜 사용자 프롬프트"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG_1x1_B64}},
    ])])
    pastes = [e for e in evs if e.action == "paste"]
    prompts = [e for e in evs if e.action == "prompt"]
    assert len(pastes) == 1 and pastes[0].target == "[Image #1]"
    assert pastes[0].preview == "<image:image/png>"
    assert len(prompts) == 1 and prompts[0].preview == "진짜 사용자 프롬프트"

def test_user_record_image_placeholder_text_not_prompt(tmp_path):
    from tests.conftest import PNG_1x1_B64
    evs = _parse_records(tmp_path, [_user_record([
        {"type": "text", "text": "[Image #1]"},   # 이미지 placeholder — prompt 아님
        {"type": "image", "source": {"media_type": "image/png", "data": PNG_1x1_B64}},
    ])])
    assert [e for e in evs if e.action == "paste"]
    assert not [e for e in evs if e.action == "prompt"]

def test_user_record_multiple_images(tmp_path):
    from tests.conftest import PNG_1x1_B64
    img = {"type": "image", "source": {"media_type": "image/png", "data": PNG_1x1_B64}}
    evs = _parse_records(tmp_path, [_user_record([img, img])])
    pastes = [e for e in evs if e.action == "paste"]
    assert [p.target for p in pastes] == ["[Image #1]", "[Image #2]"]

def test_non_dict_jsonl_lines_dont_crash(tmp_path):
    # 비-dict 최상위 JSON 줄(배열/문자열/숫자)이 섞여도 크래시 없이 정상 줄만 처리
    from tests.conftest import write_jsonl
    root = tmp_path / "dot-claude"
    write_jsonl(root / "history.jsonl",
                [[1, 2, 3], "bare", {"pastedContents": {"1": {"content": "OK"}}}])
    write_jsonl(root / "projects" / "-p" / "s.jsonl",
                ["bare string", 42, _user_record([{"type": "text", "text": "real"}])])
    evs = list(parse_source(ClaudeSource(root)))   # 예외 없어야 함
    assert any(e.action == "paste" and e.preview == "OK" for e in evs)
    assert any(e.action == "prompt" and e.preview == "real" for e in evs)

def test_empty_or_missing_text_no_spurious_prompt(tmp_path):
    for content in ([{"type": "text", "text": ""}],
                    [{"type": "text", "text": "   \n\t "}],
                    [{"type": "text"}],                       # text 키 없음
                    [{"type": "text", "text": None}]):        # 명시적 None
        evs = _parse_records(tmp_path, [_user_record(content)])
        assert not [e for e in evs if e.action == "prompt"]

def test_content_order_preserved(tmp_path):
    from tests.conftest import PNG_1x1_B64
    img = {"type": "image", "source": {"media_type": "image/png", "data": PNG_1x1_B64}}
    evs = _parse_records(tmp_path, [_user_record([
        {"type": "text", "text": "Caption 1"}, img,
        {"type": "text", "text": "Caption 2"}, img,
    ])])
    seq = [(e.action, e.target if e.action == "paste" else e.preview) for e in evs]
    assert seq == [("prompt", "Caption 1"), ("paste", "[Image #1]"),
                   ("prompt", "Caption 2"), ("paste", "[Image #2]")]

def test_tooluseresult_and_text_coexist_emit_both(tmp_path):
    # read와 사용자 코멘트(text)가 한 레코드에 공존하면 둘 다 발행(누락 금지)
    rec = {"type": "user", "sessionId": "s", "timestamp": "t",
           "toolUseResult": {"file": {"filePath": "/tmp/out.txt", "content": "FILE_BODY"}},
           "message": {"role": "user", "content": [
               {"type": "tool_result", "content": "FILE_BODY"},
               {"type": "text", "text": "사용자 코멘트"}]}}
    evs = _parse_records(tmp_path, [rec])
    assert any(e.action == "read" and e.target == "/tmp/out.txt" for e in evs)
    assert any(e.action == "prompt" and e.preview == "사용자 코멘트" for e in evs)

def test_tooluseresult_and_image_coexist_emit_both(tmp_path):
    from tests.conftest import PNG_1x1_B64
    rec = {"type": "user", "sessionId": "s", "timestamp": "t",
           "toolUseResult": {"file": {"filePath": "/tmp/x", "content": "B"}},
           "message": {"role": "user", "content": [
               {"type": "image", "source": {"media_type": "image/png", "data": PNG_1x1_B64}}]}}
    evs = _parse_records(tmp_path, [rec])
    assert any(e.action == "read" for e in evs)
    assert any(e.action == "paste" and e.target == "[Image #1]" for e in evs)

def test_string_content_emits_prompt(tmp_path):
    # message.content 가 리스트가 아닌 문자열인 단순 메시지도 prompt로 살린다
    rec = {"type": "user", "sessionId": "s", "timestamp": "t",
           "message": {"role": "user", "content": "그냥 문자열 프롬프트"}}
    evs = _parse_records(tmp_path, [rec])
    prompts = [e for e in evs if e.action == "prompt"]
    assert prompts and prompts[0].preview == "그냥 문자열 프롬프트"

def _assistant_record(parts):
    return {"type": "assistant", "sessionId": "s", "timestamp": "t",
            "message": {"role": "assistant", "content": parts}}

def test_assistant_bash_and_response(tmp_path):
    evs = _parse_records(tmp_path, [_assistant_record([
        {"type": "text", "text": "작업 중"},
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la /etc"}},
    ])])
    assert any(e.action == "response" and e.actor == "agent" and e.preview == "작업 중" for e in evs)
    assert any(e.action == "bash" and e.actor == "agent" and e.target == "ls -la /etc" for e in evs)

def test_assistant_write_variants(tmp_path):
    cases = [
        ("Write", {"file_path": "/a.py"}, "/a.py"),
        ("Edit", {"file_path": "/b.py"}, "/b.py"),
        ("MultiEdit", {"file_path": "/c.py"}, "/c.py"),
        ("NotebookEdit", {"notebook_path": "/n.ipynb"}, "/n.ipynb"),          # notebook_path 우선
        ("NotebookEdit", {"file_path": "/fallback.ipynb"}, "/fallback.ipynb"),  # 없으면 file_path
    ]
    for name, inp, expect in cases:
        evs = _parse_records(tmp_path, [_assistant_record([
            {"type": "tool_use", "name": name, "input": inp}])])
        writes = [e for e in evs if e.action == "write"]
        assert writes and writes[0].actor == "agent" and writes[0].target == expect, (name, inp)

def test_assistant_read_tooluse_not_emitted(tmp_path):
    # tool_use Read/Grep/Glob 은 Event 미발행 — 읽기는 toolUseResult read가 담당(중복 방지)
    evs = _parse_records(tmp_path, [_assistant_record([
        {"type": "tool_use", "name": "Read", "input": {"file_path": "/x"}},
        {"type": "tool_use", "name": "Grep", "input": {"pattern": "foo"}},
        {"type": "tool_use", "name": "Glob", "input": {"pattern": "*.py"}},
    ])])
    assert not [e for e in evs if e.action in ("read", "write", "bash")]

def test_empty_tooluseresult_file_still_emits_read(tmp_path):
    # 계약: toolUseResult.file 키가 있으면(빈 dict라도) read 발행(target=""/preview="")
    rec = {"type": "user", "sessionId": "s", "timestamp": "t",
           "toolUseResult": {"file": {}},
           "message": {"role": "user", "content": [{"type": "text", "text": "x"}]}}
    reads = [e for e in _parse_records(tmp_path, [rec]) if e.action == "read"]
    assert len(reads) == 1 and reads[0].actor == "agent" and reads[0].target == ""

def test_image_zero_text_is_not_placeholder(tmp_path):
    # [Image #0] 은 파서가 매기지 않는 번호 → placeholder 아님 → prompt 발행
    evs = _parse_records(tmp_path, [_user_record([{"type": "text", "text": "[Image #0]"}])])
    prompts = [e for e in evs if e.action == "prompt"]
    assert prompts and prompts[0].preview == "[Image #0]"
    # [Image #1] 은 placeholder → skip (대조군)
    evs2 = _parse_records(tmp_path, [_user_record([{"type": "text", "text": "[Image #1]"}])])
    assert not [e for e in evs2 if e.action == "prompt"]

def test_non_string_payloads_coerced_no_crash(tmp_path):
    # 손상 jsonl: content/text 가 비-문자열(int/float)이어도 크래시 없이 str화 발행
    from tests.conftest import write_jsonl
    root = tmp_path / "dot-claude"
    write_jsonl(root / "history.jsonl",
                [{"timestamp": "t", "project": "p", "pastedContents": {"1": {"content": 42}}}])
    write_jsonl(root / "projects" / "-p" / "s.jsonl",
                [_user_record([{"type": "text", "text": 7}]),
                 _assistant_record([{"type": "text", "text": 3.5}])])
    evs = list(parse_source(ClaudeSource(root)))   # 예외 없어야 함
    assert any(e.action == "paste" and e.preview == "42" for e in evs)
    assert any(e.action == "prompt" and e.preview == "7" for e in evs)
    assert any(e.action == "response" and e.preview == "3.5" for e in evs)

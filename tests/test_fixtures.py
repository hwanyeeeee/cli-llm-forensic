import json
from tests.conftest import make_history, make_transcript, ENV_BODY, content_hash

def test_make_history_emits_pastedcontents():
    rows = make_history([{"display":"d","items":[{"content":"X"}]}])
    assert rows[0]["pastedContents"]["1"] == {"type":"text","content":"X"}

def test_make_transcript_read_has_tooluseresult():
    rec = make_transcript([{"kind":"read","path":"/x/.env","content":ENV_BODY}])[0]
    assert rec["toolUseResult"]["file"]["filePath"] == "/x/.env"
    assert "CLFXTEST001" in rec["toolUseResult"]["file"]["content"]

def test_built_root_layout(built_root):
    assert (built_root/"history.jsonl").exists()
    assert list((built_root/"paste-cache").glob("*.txt"))
    assert (built_root/"projects"/"-clfx-victim"/"sess.jsonl").exists()

import json
from clfx.cli import main, _origin_label

def _load(out):
    return [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_parse_writes_events_jsonl(built_root, tmp_path, capsys):
    out = tmp_path / "events.jsonl"
    rc = main(["parse", str(built_root), "-o", str(out)])
    assert rc == 0 and out.exists()
    evs = _load(out)
    actions = {e["action"] for e in evs}
    assert {"paste","read","prompt"} <= actions
    assert all("source" in e and e["source"]["line"] >= 1 for e in evs)


def test_parse_multi_root_concatenates(built_root, tmp_path):
    # 여러 루트(WSL+Windows)를 한 번에 스캔 → 합집합. 같은 fixture 2번 → 정확히 2배.
    single = tmp_path / "one.jsonl"
    multi = tmp_path / "two.jsonl"
    assert main(["parse", str(built_root), "-o", str(single)]) == 0
    assert main(["parse", str(built_root), str(built_root), "-o", str(multi)]) == 0
    one, two = _load(single), _load(multi)
    assert len(two) == 2 * len(one)
    # source.file(루트경로 포함) 출처 보존 — 스키마 불변
    assert all(e["source"]["file"] and e["source"]["line"] >= 1 for e in two)


def test_origin_label():
    assert _origin_label(r"C:\Users\x\.claude") == "windows"
    assert _origin_label(r"\\wsl.localhost\Ubuntu\home\u\.claude") == "wsl"
    assert _origin_label("/home/u/.claude") == "wsl"
    assert _origin_label("/mnt/c/Users/x/.claude") == "windows"
    assert _origin_label("/root/.claude") == "wsl"


def test_parse_tags_origin(built_root, tmp_path):
    # 각 이벤트에 origin: 태그 부여(루트 경로로 판정). built_root는 tmp_path 하위(/...) → wsl/other.
    out = tmp_path / "ev.jsonl"
    assert main(["parse", str(built_root), "-o", str(out)]) == 0
    evs = _load(out)
    label = _origin_label(str(built_root))
    assert all(f"origin:{label}" in e["tags"] for e in evs)

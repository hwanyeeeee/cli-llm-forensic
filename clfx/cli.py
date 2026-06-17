import argparse
import json
import os
import re
import sys

from clfx.sources.claude import ClaudeSource
from clfx.parser import parse_source
from clfx.event import Event
from clfx.analyze.attribution import enrich
from clfx.query.engine import QueryEngine
from clfx.web.api import query_payload


def _write_events(events, out_path):
    """원자적·전부-아니면-전무 기록: 같은 디렉토리 temp 파일에 쓴 뒤 os.replace.
    포렌식 산출물은 완전하거나 아예 없어야 한다(부분 기록 = 변조된 감사추적)."""
    out_path = os.fspath(out_path)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(ev.to_json() + "\n")
        os.replace(tmp, out_path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _origin_label(root):
    """루트 경로로 출처(머신) 판정 — owner 아님. tags에 origin:<label> 부여(스키마 불변)."""
    r = str(root).replace("\\", "/").lower()
    if "wsl.localhost" in r or "wsl$" in r:
        return "wsl"
    if re.match(r"^[a-z]:/", r) or r.startswith("/mnt/"):   # 드라이브문자(C:/) 또는 /mnt/c(=Windows 마운트)
        return "windows"
    if r.startswith("/home") or r.startswith("/root"):
        return "wsl"
    return "other"


def parse_roots(roots):
    """여러 .claude 루트 → origin 태깅된 Event 리스트(병합). parse/scan 공용. enrich는 호출자 책임.
    WSL/Windows는 별 세션이라 dedup 불요."""
    evs = []
    for root in roots:                       # nargs="+" → 항상 list. 여러 루트(WSL+Windows .claude)를 한 번에.
        tag = f"origin:{_origin_label(root)}"
        for e in parse_source(ClaudeSource(root)):
            if tag not in e.tags:            # 출처 태그(스키마 불변 — tags[] 사용). source.file과 함께 머신 보존.
                e.tags.append(tag)
            evs.append(e)
    return evs


def cmd_parse(args):
    try:
        evs = parse_roots(args.root)
        _write_events(evs, args.out)
    except Exception as e:
        print(f"clfx parse: {e}", file=sys.stderr)
        return 1
    return 0


def _read_events(path):
    with open(path, encoding="utf-8") as f:
        return [Event.from_dict(json.loads(l)) for l in f if l.strip()]


class _NullSource:
    """--root 미지정 시 bypass 판정용 빈 소스(transcript 없음)."""
    agent = "claude"

    def transcript_records(self):
        return iter(())


def cmd_analyze(args):
    try:
        events = _read_events(args.events)
        src = ClaudeSource(args.root) if args.root else _NullSource()
        _write_events(enrich(events, src), args.out)
    except Exception as e:
        print(f"clfx analyze: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_query(args):
    try:
        eng = QueryEngine(_read_events(args.analyzed))
        p = query_payload(eng, args.question, answer_only_summary=True)   # CLI: 요약 intent만 LLM(make_llm+digest 폴백), 비요약은 비호출
        for e in p["events"]:
            src = e["source"]
            print(f"[{e['ts'] or '?'}] {e['actor']}/{e['action']} {e['target']}  "
                  f"({src['file']}:{src['line']})")
            if e["preview"]:
                print(f"    {e['preview'][:200]}")
        # CLI는 answer_only_summary=True라 비요약 질의면 summary=None → 자동 미출력. 요약 intent만 출력.
        if p["summary"]:
            print("\n--- 요약 ---")
            print(p["summary"]["text"])
        print(f"\n({p['count']} events)")
    except Exception as e:
        print(f"clfx query: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_serve(args):
    try:
        from clfx.web.server import serve
        serve(args.analyzed, host=args.host, port=args.port)
    except FileNotFoundError as e:
        print(f"clfx serve: 파일 없음 {e}", file=sys.stderr)
        return 1
    except Exception as e:           # 깨진 jsonl(JSONDecodeError/ValueError)·OSError 등 로드/바인드 실패
        print(f"clfx serve: {e}", file=sys.stderr)
        return 1
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="clfx")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("parse", help="에이전트 기록 → events.jsonl")
    sp.add_argument("root", nargs="+",
                    help="~/.claude 루트(들) — 여러 개 가능(예: Windows + \\\\wsl.localhost\\... )")
    sp.add_argument("-o", "--out", required=True)
    sp.set_defaults(func=cmd_parse)

    ap = sub.add_parser("analyze", help="events.jsonl → analyzed.jsonl (tags·mask·귀속)")
    ap.add_argument("events")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--root", default=None, help="bypass 판정용 ~/.claude 루트(선택)")
    ap.set_defaults(func=cmd_analyze)

    qp = sub.add_parser("query", help="analyzed.jsonl 에 자연어 질의")
    qp.add_argument("analyzed")
    qp.add_argument("question")
    qp.set_defaults(func=cmd_query)

    rp = sub.add_parser("serve", help="analyzed.jsonl 을 로컬 웹 대시보드로 본다 (생략 시 빈 상태로 起動→스캔)")
    rp.add_argument("analyzed", nargs="?", default=None)
    rp.add_argument("--host", default="127.0.0.1")
    rp.add_argument("--port", type=int, default=8787)
    rp.set_defaults(func=cmd_serve)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

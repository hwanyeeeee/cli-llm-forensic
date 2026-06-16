import argparse
import json
import os
import sys

from clfx.sources.claude import ClaudeSource
from clfx.parser import parse_source
from clfx.event import Event
from clfx.analyze.attribution import enrich
from clfx.query.engine import QueryEngine
from clfx.query.llm import route_intent, summarize


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


def cmd_parse(args):
    try:
        _write_events(parse_source(ClaudeSource(args.root)), args.out)
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
        intent = route_intent(args.question)
        op = intent["op"]
        if op == "who_did":
            res = eng.who_did(intent["action"], intent.get("target", ""))
        elif op == "secrets":
            res = eng.secrets()
        elif op == "on_date":
            res = eng.on_date(intent["day"])
        elif op == "timeline":
            res = eng.timeline()
        else:
            res = eng.search(intent.get("kw", ""))
        out = summarize(res, llm=None) if intent.get("summarize") else None
        for e in res:
            print(f"[{e.ts or '?'}] {e.actor}/{e.action} {e.target}  ({e.source.file}:{e.source.line})")
            if e.preview:
                print(f"    {e.preview[:200]}")
        if out:
            print("\n--- 요약 ---")
            print(out["text"])
        print(f"\n({len(res)} events)")
    except Exception as e:
        print(f"clfx query: {e}", file=sys.stderr)
        return 1
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="clfx")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("parse", help="에이전트 기록 → events.jsonl")
    sp.add_argument("root", help="~/.claude 루트")
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
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

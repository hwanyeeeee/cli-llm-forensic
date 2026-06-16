import argparse
import json
import os
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
        p = query_payload(eng, args.question)   # op 디스패치 단일 진실원천(web.api)
        for e in p["events"]:
            src = e["source"]
            print(f"[{e['ts'] or '?'}] {e['actor']}/{e['action']} {e['target']}  "
                  f"({src['file']}:{src['line']})")
            if e["preview"]:
                print(f"    {e['preview'][:200]}")
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

    rp = sub.add_parser("serve", help="analyzed.jsonl 을 로컬 웹 대시보드로 본다")
    rp.add_argument("analyzed")
    rp.add_argument("--host", default="127.0.0.1")
    rp.add_argument("--port", type=int, default=8787)
    rp.set_defaults(func=cmd_serve)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

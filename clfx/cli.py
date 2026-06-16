import argparse
import os
import sys

from clfx.sources.claude import ClaudeSource
from clfx.parser import parse_source


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


def build_parser():
    p = argparse.ArgumentParser(prog="clfx")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("parse", help="에이전트 기록 → events.jsonl")
    sp.add_argument("root", help="~/.claude 루트")
    sp.add_argument("-o", "--out", required=True)
    sp.set_defaults(func=cmd_parse)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

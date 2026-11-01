"""IMP-SCN-004: 명령행 도구.

uv run swarm-scenario validate <file.json>...
uv run swarm-scenario show <file.json>
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from google.protobuf import text_format

from swarm.v1 import entity_pb2

from .convert import from_dict
from .validate import validate


def _validate(paths: list[str]) -> int:
    rc = 0
    for p in paths:
        issues = validate(json.loads(Path(p).read_text(encoding="utf-8")))
        if issues:
            rc = 1
            print(f"{p}: INVALID")
            for i in issues:
                print(f"  {i}")
        else:
            print(f"{p}: OK")
    return rc


def _show(path: str) -> int:
    sc = from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    kinds = Counter(entity_pb2.EntityKind.Name(e.kind) for e in sc.entities)
    print(f"name: {sc.name}")
    print(f"start: {text_format.MessageToString(sc.start, as_one_line=True)}")
    print(f"entities: {len(sc.entities)} {dict(kinds)}")
    if sc.mission_plan is not None:
        print(f"mission_plan: {sc.mission_plan.plan_id} tasks={len(sc.mission_plan.tasks)} "
              f"formations={len(sc.mission_plan.formations)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="swarm-scenario")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate").add_argument("files", nargs="+")
    sub.add_parser("show").add_argument("file")
    args = ap.parse_args(argv)
    if args.cmd == "validate":
        return _validate(args.files)
    return _show(args.file)


if __name__ == "__main__":
    sys.exit(main())

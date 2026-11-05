"""QA-019 비교기: 같은 시드 lockstep 반복 실행(--trace-io) 결과를 기준 실행과 비교한다.

출력(실행마다):
- traj: 공통 프레임에서 처음 어긋난 프레임·엔티티, 최대 차이(m)
- agent_io: MA 입력(항법 위치·신선도·P2P/C2 수신함)이 처음 다른 프레임과 필드
- stale: 항법 보고가 그 프레임 것이 아니거나 fresh=0인 (프레임, 기체) 수와 첫 프레임
- link: 프레임별 LinkOutcome 집합(순서 무시)이 처음 다른 프레임, 수신 순서만 다른 프레임 수

사용: uv run python qa/qa019_diff.py qa/out/p5/q19_base_1 qa/out/p5/q19_base_2 ... [--upto N]
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import pickle
import re
from collections import defaultdict
from pathlib import Path

M_PER_DEG = 111_320.0
LINE = re.compile(r"^(\d+) (\S+) nav=(-?\d+) fresh=(\d) x=(\S+) p2p=\[(.*?)\] c2=\[(.*?)\]$")


def load_traj(d: Path) -> dict[str, dict[int, tuple]]:
    t = pickle.load(gzip.open(d / "trace.pkl.gz"))["traj"]
    return {e: {r[0]: r[1:] for r in rows} for e, rows in t.items()}


def traj_diff(a, b, upto: int) -> dict:
    first, worst, n = None, 0.0, 0
    for e in sorted(set(a) & set(b)):
        for fr in sorted(set(a[e]) & set(b[e])):
            if fr > upto:
                break
            n += 1
            pa, pb = a[e][fr], b[e][fr]
            if pa != pb:
                dn = (pa[0] - pb[0]) * M_PER_DEG
                de = (pa[1] - pb[1]) * M_PER_DEG * math.cos(math.radians(pa[0]))
                dd = math.sqrt(dn * dn + de * de + (pa[2] - pb[2]) ** 2)
                worst = max(worst, dd)
                if first is None or fr < first[0]:
                    first = (fr, e, dd)
    return {"common": n, "first": first, "worst_m": worst}


def load_io(d: Path, upto: int) -> dict[tuple[int, str], tuple]:
    out = {}
    with open(d / "agent_io.txt", encoding="utf-8") as f:
        for ln in f:
            m = LINE.match(ln.rstrip("\n"))
            if not m:
                continue
            fr = int(m.group(1))
            if fr > upto:
                break
            out[(fr, m.group(2))] = (int(m.group(3)), int(m.group(4)), m.group(5), m.group(6), m.group(7))
    return out


def stale(io: dict) -> dict:
    bad = sorted(k for k, v in io.items() if v[0] != k[0] or v[1] == 0)
    return {"n": len(bad), "first": bad[:5]}


FIELDS = ("nav_frame", "fresh", "x", "p2p", "c2")


def io_diff(a: dict, b: dict) -> dict:
    keys = sorted(set(a) & set(b))
    first = None
    per_field = defaultdict(int)
    order_only = 0
    for k in keys:
        if a[k] == b[k]:
            continue
        fs = [FIELDS[i] for i in range(5) if a[k][i] != b[k][i]]
        for f in fs:
            per_field[f] += 1
        if fs == ["p2p"] and sorted(a[k][3].split(",")) == sorted(b[k][3].split(",")):
            order_only += 1
        if first is None:
            first = {"frame": k[0], "entity": k[1], "fields": fs,
                     "a": {f: a[k][FIELDS.index(f)] for f in fs}, "b": {f: b[k][FIELDS.index(f)] for f in fs}}
    return {"common": len(keys), "first": first, "per_field": dict(per_field), "p2p_order_only": order_only}


def load_link(d: Path, upto: int) -> dict[int, list]:
    rows = pickle.load(gzip.open(d / "link_io.pkl.gz"))
    by = defaultdict(list)
    for r in rows:
        if r[0] <= upto:
            by[r[0]].append(r[1:])
    return by


def link_diff(a: dict, b: dict) -> dict:
    lo = max(min(a, default=0), min(b, default=0)) + 2  # 관측자 연결 직후 프레임은 뺀다
    hi = min(max(a, default=0), max(b, default=0)) - 2
    first_set, order_frames, set_frames = None, 0, 0
    for fr in range(lo, hi + 1):
        x, y = a.get(fr, []), b.get(fr, [])
        if sorted(x) != sorted(y):
            set_frames += 1
            if first_set is None:
                sx, sy = set(x), set(y)
                first_set = {"frame": fr, "only_a": sorted(sx - sy)[:6], "only_b": sorted(sy - sx)[:6]}
        elif x != y:
            order_frames += 1
    return {"range": [lo, hi], "first_set_diff": first_set, "set_diff_frames": set_frames,
            "order_only_frames": order_frames}


def load_ctrl(d: Path, upto: int) -> dict[tuple[int, str], list[bytes]] | None:
    f = d / "ctrl_io.pkl.gz"
    if not f.exists():
        return None
    by = defaultdict(list)
    for fr, e, b in pickle.load(gzip.open(f)):
        if fr <= upto:
            by[(fr, e)].append(b)
    return by


def ctrl_diff(a, b) -> dict | None:
    """Agent 출력(ControlOutput) 비교. 관측자 연결 직후는 뺀다"""
    if a is None or b is None:
        return None
    keys = sorted(set(a) & set(b))
    lo = keys[0][0] + 2 if keys else 0
    first, n = None, 0
    for k in keys:
        if k[0] < lo:
            continue
        if a[k] != b[k]:
            n += 1
            first = first or k
    miss = sorted(k for k in set(a) ^ set(b) if k[0] >= lo)
    return {"common": len(keys), "first": first, "diff": n, "missing": miss[:5], "n_missing": len(miss)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--upto", type=int, default=10**9)
    ap.add_argument("--json")
    a = ap.parse_args()
    dirs = [Path(r) for r in a.runs]
    ref = dirs[0]
    rt, ri, rl, rc = load_traj(ref), load_io(ref, a.upto), load_link(ref, a.upto), load_ctrl(ref, a.upto)
    res = {"ref": ref.name, "ref_stale": stale(ri), "runs": {}}
    for d in dirs[1:]:
        t, io, lk, ct = load_traj(d), load_io(d, a.upto), load_link(d, a.upto), load_ctrl(d, a.upto)
        res["runs"][d.name] = {"traj": traj_diff(rt, t, a.upto), "stale": stale(io),
                               "agent_io": io_diff(ri, io), "ctrl": ctrl_diff(rc, ct), "link": link_diff(rl, lk)}
    txt = json.dumps(res, ensure_ascii=False, indent=1, default=str)
    print(txt)
    if a.json:
        Path(a.json).write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()

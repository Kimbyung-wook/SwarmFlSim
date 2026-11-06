"""QA-019 변형별 요약: 같은 변형의 반복 실행을 궤적이 같은 무리로 나누고, 0 지연 전달과 Agent 수신 프레임 차이를 센다.

사용: uv run python qa/qa019_summary.py base nosensor nopayload noloss [--n 6] [--prefix q19] [--json 파일]
--prefix: 실행 폴더 접두어(qa/out/p5/<prefix>_<변형>_<i>). truth 이벤트(trace.pkl.gz)도 실행 1과 바이트 단위로 비교한다.
"""
from __future__ import annotations

import argparse
import gzip
import json
import pickle
from collections import Counter
from pathlib import Path

import qa019_diff as q

OUT = Path(__file__).resolve().parent / "out/p5"


def events(d: Path, upto: int) -> list:
    """trace.pkl.gz의 truth 이벤트 (종류, 직렬화 바이트) 중 프레임 upto 이하"""
    from swarm.v1 import truth_pb2
    tr = pickle.load(gzip.open(d / "trace.pkl.gz"))
    return [(k, p) for k, p in tr["events"] if truth_pb2.TruthEvent.FromString(p).header.frame <= upto]


def summarize(variant: str, n: int, prefix: str = "q19") -> dict:
    dirs = [OUT / f"{prefix}_{variant}_{i}" for i in range(1, n + 1)]
    dirs = [d for d in dirs if (d / "agent_io.txt").exists() and (d / "link_io.pkl.gz").exists()]
    trajs = [q.load_traj(d) for d in dirs]
    ios = [q.load_io(d, 10**9) for d in dirs]
    links = [q.load_link(d, 10**9) for d in dirs]
    upto = min(max(fr for e in t.values() for fr in e) for t in trajs) - 5
    # 궤적 무리: 앞 무리 대표와 공통 프레임(upto까지)에서 완전히 같으면 같은 무리
    groups: list[list[int]] = []
    for i in range(len(dirs)):
        for g in groups:
            if q.traj_diff(trajs[g[0]], trajs[i], upto)["first"] is None:
                g.append(i)
                break
        else:
            groups.append([i])
    zero = []
    for i, lk in enumerate(links):
        # r = (src, dst, seq, iface, msg_type, size, kind, reason, tx_us, rx_us)
        z = sorted((fr, r[0], r[1], r[2]) for fr, rows in lk.items() for r in rows
                   if r[6] != "DROPPED" and r[9] == r[8])
        zero.append(z)
    evs = [events(d, upto) for d in dirs]
    pairs = []
    for i in range(1, len(dirs)):
        td = q.traj_diff(trajs[0], trajs[i], upto)
        io = q.io_diff(ios[0], ios[i])
        pairs.append({"run": dirs[i].name, "traj_first": td["first"], "worst_m": td["worst_m"],
                      "io_first": io["first"], "io_fields": io["per_field"],
                      "link": q.link_diff(links[0], links[i]),
                      "events_identical": evs[i] == evs[0],
                      "event_first_diff": next((j for j, (x, y) in enumerate(zip(evs[0], evs[i])) if x != y),
                                               None if len(evs[0]) == len(evs[i]) else min(len(evs[0]), len(evs[i])))})
    return {"variant": variant, "runs": [d.name for d in dirs], "upto": upto,
            "groups": [[dirs[i].name.rsplit("_", 1)[1] for i in g] for g in groups],
            "zero_delay": [z[:4] for z in zero], "zero_delay_n": [len(z) for z in zero],
            "stale": [q.stale(io)["n"] for io in ios], "n_events": [len(e) for e in evs],
            "event_kinds": dict(sorted(Counter(k for k, _ in evs[0]).items())) if evs else {},
            "vs_first": pairs}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variants", nargs="+")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--prefix", default="q19")
    ap.add_argument("--json")
    a = ap.parse_args()
    res = [summarize(v, a.n, a.prefix) for v in a.variants]
    txt = json.dumps(res, ensure_ascii=False, indent=1, default=str)
    print(txt)
    if a.json:
        Path(a.json).write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()

"""TC-QA-040: 같은 시드 lockstep 반복 실행에서 GCS가 받은 임무장비 상태(*Activity, DEC-051) 순서·프레임 비교.

실행마다 gcs_act.pkl.gz(qa/p5_e2e.py)를 읽어 기준 실행(첫 번째)과 비교한다.
- rx: 수신 순서 그대로 (rx 프레임, src, msg, payload_id, 본문 프레임, 본문 해시). 처음 다른 위치와 프레임
- rx_set: rx 프레임별 집합(순서 무시)이 다른 프레임 수
- tx: *Activity LinkOutcome의 (tx 프레임, src, msg, kind, reason, rx_us) 집합이 다른 프레임 수
- body_lag: 본문 프레임(Core onboard 발행 프레임)과 송신 프레임의 차 분포 (onboard 도착이 늦으면 커진다)

사용: uv run python qa/act_det.py qa/out/p5/a40_base_1 qa/out/p5/a40_base_2 ... [--json 파일]
"""
from __future__ import annotations

import argparse
import gzip
import json
import pickle
from collections import Counter, defaultdict
from pathlib import Path

FR_US = 20000


def load(d: Path) -> dict:
    x = pickle.load(gzip.open(d / "gcs_act.pkl.gz"))
    # rx 행: (관측 프레임, dst, msg, src, seq, env 프레임, rx_us, 본문 프레임, payload_id, 해시)
    rx = [(r[6] // FR_US, r[3], r[2], r[8], r[7], r[9]) for r in x["rx"]]
    env = [(r[6] // FR_US, r[3], r[2], r[8], r[5], r[7]) for r in x["rx"]]  # env 프레임 = 송신 프레임
    # outcome 행: (tx 프레임, src, dst, msg, kind, reason, tx_us, rx_us, seq)
    tx = [(r[0], r[1], r[3], r[4], r[5], r[7]) for r in x["outcome"]]
    return {"rx": rx, "env": env, "tx": tx}


def by_frame(rows: list[tuple]) -> dict[int, list[tuple]]:
    b = defaultdict(list)
    for r in rows:
        b[r[0]].append(r)
    return b


def cmp(a: dict, b: dict) -> dict:
    hi = min(max((r[0] for r in a["rx"]), default=0), max((r[0] for r in b["rx"]), default=0)) - 2
    ra = [r for r in a["rx"] if r[0] <= hi]
    rb = [r for r in b["rx"] if r[0] <= hi]
    first = None
    for i, (x, y) in enumerate(zip(ra, rb)):
        if x != y:
            first = {"index": i, "a": x, "b": y}
            break
    if first is None and len(ra) != len(rb):
        first = {"index": min(len(ra), len(rb)), "len": [len(ra), len(rb)]}
    fa, fb = by_frame(ra), by_frame(rb)
    set_diff = [f for f in sorted(set(fa) | set(fb)) if sorted(fa.get(f, [])) != sorted(fb.get(f, []))]
    order_only = [f for f in sorted(set(fa) & set(fb)) if fa[f] != fb[f] and sorted(fa[f]) == sorted(fb[f])]
    ta = by_frame([r for r in a["tx"] if r[0] <= hi])
    tb = by_frame([r for r in b["tx"] if r[0] <= hi])
    tx_diff = [f for f in sorted(set(ta) | set(tb)) if sorted(ta.get(f, [])) != sorted(tb.get(f, []))]
    out = {"upto": hi, "rx_n": [len(ra), len(rb)], "rx_first_diff": first, "rx_set_diff_frames": len(set_diff),
           "rx_set_diff_first": set_diff[:5], "rx_order_only_frames": len(order_only),
           "tx_set_diff_frames": len(tx_diff), "tx_set_diff_first": tx_diff[:5]}
    if set_diff:
        f = set_diff[0]
        sa, sb = set(fa.get(f, [])), set(fb.get(f, []))
        out["rx_set_diff_detail"] = {"frame": f, "only_a": sorted(sa - sb)[:6], "only_b": sorted(sb - sa)[:6]}
    if tx_diff:
        f = tx_diff[0]
        sa, sb = set(ta.get(f, [])), set(tb.get(f, []))
        out["tx_set_diff_detail"] = {"frame": f, "only_a": sorted(sa - sb)[:6], "only_b": sorted(sb - sa)[:6]}
    return out


def lag(run: dict) -> dict:
    """송신 프레임(env) - 본문 프레임(onboard). DEC-051에서 Agent는 틱 f+1에 본문 프레임 f 상태를 보낸다"""
    c = Counter(r[4] - r[5] for r in run["env"])
    return dict(sorted(c.items()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--json")
    a = ap.parse_args()
    dirs = [Path(r) for r in a.runs if (Path(r) / "gcs_act.pkl.gz").exists()]
    runs = [load(d) for d in dirs]
    res = {"ref": dirs[0].name, "lag_ref": lag(runs[0]),
           "by_msg_ref": dict(Counter(f"{r[1]}:{r[2]}" for r in runs[0]["rx"])), "runs": {}}
    for d, r in zip(dirs[1:], runs[1:]):
        res["runs"][d.name] = cmp(runs[0], r) | {"lag": lag(r)}
    txt = json.dumps(res, ensure_ascii=False, indent=1, default=str)
    print(txt)
    if a.json:
        Path(a.json).write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()

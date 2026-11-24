"""QA 37차 O-30 재확인 (TC-QA-20x): realtime 시작 때 Agent 첫 송신이 늦는지 본다.

Datalink·Agent·Core(평지)만 띄운다. 관측자가 먼저 붙고 Core를 마지막에 띄운다(gw_plan과 같은 순서).
관측: 첫 truth/state 프레임, 기체 송신(swarm/<uav>/tx/**)의 첫 LinkEnvelope header(frame, sim_time_us)와 메시지 이름.
모의 시각 T_END s에서 끝낸다. realtime N회, lockstep 대조 M회.

uv run --with psutil python qa/run_release.py qa/o30_start.py --out qa/out/qa37/o30 --rt 20 --ls 5
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402

QA = Path(__file__).resolve().parent
ROOT = QA.parent
SCN = QA / "scenarios" / "qa_gw_plan.json"
T_END = 4.0


def one(out: Path, lockstep: bool, base_port: int) -> dict:
    st_ = h.Stack(out / "stack", SCN, base_port=base_port, lockstep=lockstep, rate=1.0, record=False,
                  core_extra=["--terrain-flat", "0"])
    first: dict[str, tuple] = {}
    lock = threading.Lock()
    res: dict = {"mode": "lockstep" if lockstep else "realtime"}
    try:
        st_.start_one("datalink")
        st_.start_one("agent")
        time.sleep(st_.settle)
        ob = h.Observer([st_.endpoint()])
        link = ob.m[2]

        def tx(s) -> None:  # noqa: ANN001
            src = str(s.key).split("/")[1]
            if not src.startswith("uav"):
                return
            env = link.LinkEnvelope.FromString(s.payload)
            with lock:
                if src not in first:
                    first[src] = (env.header.frame, env.header.sim_time_us * 1e-6, env.msg_type.rsplit(".", 1)[-1],
                                  time.monotonic())
        ob.subs.append(ob.bus.subscribe("swarm/*/tx/**", tx))
        time.sleep(1.0)
        t_core = time.monotonic()
        st_.start_one("core")
        t_first = None
        while time.monotonic() - t_core < 60:
            time.sleep(0.02)
            if t_first is None and ob.first_frame is not None:
                t_first = time.monotonic()
            if ob.sim_s() >= T_END or "core" in "".join(st_.dead()):
                break
        res["dead"] = st_.dead()
        res["first_frame"] = ob.first_frame
        res["wall_core_to_first_frame_s"] = round(t_first - t_core, 3) if t_first else None
        snap = ob.snapshot()
        res["snapshot"] = {k: snap.get(k) for k in ("last_frame", "sim_s", "gap_frames", "overruns")}
        ob.close()
    finally:
        st_.down()
    with lock:
        res["first_tx"] = {e: {"frame": v[0], "sim_s": round(v[1], 3), "msg": v[2],
                               "wall_after_first_frame_s": round(v[3] - t_first, 3) if t_first else None}
                           for e, v in sorted(first.items())}
    fr = [v["frame"] for v in res["first_tx"].values()]
    res["min_first_tx_frame"] = min(fr) if fr else None
    res["max_first_tx_frame"] = max(fr) if fr else None
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rt", type=int, default=20)
    ap.add_argument("--ls", type=int, default=5)
    ap.add_argument("--base-port", type=int, default=48800)
    a = ap.parse_args()
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    os.environ["PYTHONIOENCODING"] = "utf-8"
    runs = []
    for i, ls in enumerate([False] * a.rt + [True] * a.ls, 1):
        r = one(out / f"r{i:02d}", ls, a.base_port)
        r["run"] = i
        runs.append(r)
        print(json.dumps({k: r[k] for k in ("run", "mode", "first_frame", "wall_core_to_first_frame_s",
                                            "min_first_tx_frame", "max_first_tx_frame")}, ensure_ascii=False),
              flush=True)
    summ = {}
    for m in ("realtime", "lockstep"):
        rr = [r for r in runs if r["mode"] == m]
        mx = [r["max_first_tx_frame"] for r in rr if r["max_first_tx_frame"] is not None]
        mn = [r["min_first_tx_frame"] for r in rr if r["min_first_tx_frame"] is not None]
        summ[m] = {"n": len(rr), "max_first_tx_frame": {"median": st.median(mx) if mx else None,
                                                         "max": max(mx) if mx else None},
                   "min_first_tx_frame_max": max(mn) if mn else None,
                   "runs_late_gt5": sum(1 for x in mx if x > 5),
                   "first_frame": sorted({r["first_frame"] for r in rr}, key=str),
                   "dead": [r["dead"] for r in rr if r["dead"]]}
    (out / "result.json").write_text(json.dumps({"summary": summ, "runs": runs}, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    finally:
        h.Stack.down_all()

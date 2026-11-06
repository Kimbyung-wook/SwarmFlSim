"""TC-QA-049: Datalink 재시작 뒤 재밍 구역 안 링크 두절 (QA-021 비고, DEC-052, DEC-055).

realtime 1배속, qa_p5_near(재머 기지 jam-site-01이 군집 가까이). Core가 돌고 있는 중에 Datalink를 강제로
끝내고 다시 띄운다. 새 Datalink는 frame 0의 첫 구역 이벤트를 받지 못했으므로 Core의 1 s 재발행(DEC-052)으로만
구역을 안다. LinkOutcome을 수신 기체가 그 프레임에 구역 안에 있었는지(수평 거리, truth 궤적)로 나눈다.
- 재시작 뒤 첫 LinkOutcome부터 구역 안 수신이 처음 JAMMED가 될 때까지의 프레임, 그 사이 DELIVERED 건수
- 첫 JAMMED 뒤 구역 안 수신의 DELIVERED (0이어야 한다), 송신자만 구역 안일 때의 전달 (DEC-055 수신단 판정)

uv run python qa/dl_restart_jam.py --out qa/out/p5/dlr1 --base-port 48420
"""
from __future__ import annotations

import argparse
import gzip
import pickle
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
from p5_e2e import P5Observer, P5Stack  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NEAR = ROOT / "qa/scenarios/qa_p5_near.json"


def horiz_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    dn = (a[0] - b[0]) * 111_320.0
    de = (a[1] - b[1]) * 111_320.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dn, de)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--scenario", default=str(NEAR))
    ap.add_argument("--base-port", type=int, default=48420)
    ap.add_argument("--restart-at-s", type=float, nargs="*", default=[20.0, 40.0], help="Datalink를 끝낼 모의 초")
    ap.add_argument("--down-s", type=float, default=3.0, help="끝낸 뒤 다시 띄우기까지 벽시계 초")
    ap.add_argument("--until-s", type=float, default=60.0)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    st = P5Stack(out / "stack", Path(a.scenario), base_port=a.base_port, lockstep=False, rate=1.0, record=False,
                 probe_out=out / "probe.json")
    res: dict = {"scenario": a.scenario, "restarts": []}
    try:
        st.start_one("datalink")
        st.start_one("agent")
        time.sleep(st.settle + 1.0)
        st.start_one("core")
        t0 = time.monotonic()
        time.sleep(1.5)
        ob = P5Observer([st.endpoint("datalink"), st.endpoint("agent"), st.endpoint("core")])
        from swarm.v1 import truth_pb2
        pending = sorted(a.restart_at_s)
        while True:
            time.sleep(0.1)
            w = time.monotonic() - t0
            lf = ob.last_frame or 0
            if pending and lf * 0.02 >= pending[0]:
                pending.pop(0)
                with ob.lock:
                    n_lo = len(ob.lo)
                st.kill("datalink")
                kill_fr = ob.last_frame or 0
                time.sleep(a.down_s)
                st.start_one("datalink")
                rs_fr = ob.last_frame or 0
                res["restarts"].append({"kill_obs_frame": kill_fr, "start_obs_frame": rs_fr, "lo_index": n_lo,
                                        "wall_s": round(w, 1)})
                print(f"{w:6.1f}s datalink restarted (kill frame {kill_fr}, start frame {rs_fr})", flush=True)
            if lf * 0.02 >= a.until_s or "core" in st.dead() or "agent" in st.dead() or w > a.until_s * 3 + 60:
                print(f"stop sim {lf * 0.02:.1f} wall {w:.1f} dead {st.dead()}", flush=True)
                break
        time.sleep(1.0)
        with ob.lock:
            lo = list(ob.lo)
            evs = [(k, bytes(p)) for k, p in ob.events]
            traj = {k: {f: (la, lo_) for f, la, lo_, _ in v} for k, v in ob.traj.items()}
        zones = []
        for k, p in evs:
            e = truth_pb2.TruthEvent.FromString(p)
            if e.HasField("jam_zone"):
                z = e.jam_zone
                c = z.area.circle
                zones.append({"frame": e.header.frame, "owner": z.owner, "active": z.active,
                              "c": (c.center.lat_deg, c.center.lon_deg), "r": c.radius_m})
        res["zone_events"] = {"n": len(zones), "frames_first10": [z["frame"] for z in zones[:10]]}
        act = [z for z in zones if z["active"]]
        if not act:
            res["error"] = "활성 구역 이벤트를 받지 못했다"
        else:
            zc, zr = act[0]["c"], act[0]["r"]
            res["zone"] = {"owner": act[0]["owner"], "center": zc, "radius_m": zr}

            def inside(eid: str, fr: int) -> bool | None:
                t = traj.get(eid)
                if not t:
                    return None
                p = t.get(fr) or t.get(fr - 1) or t.get(fr + 1)
                return None if p is None else horiz_m(p, zc) <= zr

            rows = []
            for fr, src, dst, kind, reason in lo:
                rows.append((fr, src, dst, kind, reason, inside(dst, fr), inside(src, fr)))

            def classify(rs: list) -> dict:
                c = Counter()
                for _, _, _, kind, reason, din, sin in rs:
                    cls = "rx_in" if din else ("tx_only_in" if sin else ("out" if din is False else "unknown"))
                    c[f"{cls}:{kind}{('/' + reason) if reason else ''}"] += 1
                return dict(sorted(c.items()))

            with gzip.open(out / "lo_rows.pkl.gz", "wb") as f:
                pickle.dump({"rows": rows, "zones": zones, "restarts": res["restarts"]}, f)
            # 구간은 송신 프레임으로 나눈다. 앞 Datalink가 끝나기 전 프레임은 앞 구간이다
            cuts = [r["kill_obs_frame"] for r in res["restarts"]]
            edges = [-1, *cuts, 10**9]
            res["segments"] = []
            for i in range(len(edges) - 1):
                seg = [r for r in rows if edges[i] < r[0] <= edges[i + 1]]
                d = {"segment": i, "n": len(seg), "classes": classify(seg)}
                if seg:
                    d["frames"] = [seg[0][0], seg[-1][0]]
                if i > 0 and seg:
                    first = seg[0][0]
                    rin = [r for r in seg if r[5]]
                    fj = next((r[0] for r in rin if r[3] == "DROPPED" and r[4] == "JAMMED"), None)
                    d["first_outcome_frame"] = first
                    d["first_rx_in_frame"] = rin[0][0] if rin else None
                    d["first_jammed_frame"] = fj
                    d["frames_to_first_jammed"] = (fj - first) if fj is not None else None
                    pre = [r for r in rin if fj is None or r[0] < fj]
                    d["rx_in_delivered_before_jam"] = sum(1 for r in pre if r[3] == "DELIVERED")
                    d["rx_in_before_jam_frames"] = [pre[0][0], pre[-1][0]] if pre else None
                    post = [r for r in rin if fj is not None and r[0] > fj]
                    d["rx_in_after_first_jam"] = dict(Counter(r[3] + ("/" + r[4] if r[4] else "") for r in post))
                    d["zone_events_after_restart"] = [z["frame"] for z in zones if z["frame"] >= first][:3]
                    dl = sorted(r[0] for r in rin if r[3] == "DELIVERED")
                    d["rx_in_delivered_frames"] = dict(Counter(dl))
                    d["rx_in_delivered_pairs"] = dict(Counter(f"{r[1]}>{r[2]}" for r in rin if r[3] == "DELIVERED"))
                res["segments"].append(d)
        res["log_issues"] = h.scan_logs(st)
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str), flush=True)
        ob.close()
    finally:
        st.down()


if __name__ == "__main__":
    main()

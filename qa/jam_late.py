"""TC-QA-042: 늦게 붙은 구독자의 활성 재밍 구역 수신 (QA-021, DEC-052).

Datalink·Agent·Core를 실제 프로세스로 띄운 뒤(관찰자는 Core보다 늦게 붙는다) 정해진 벽시계 시각에
새 버스 세션(늦은 구독자)을 열어 truth/event/jam_zone을 구독한다. 구독자마다 붙은 뒤 처음 받은
truth/state의 모의 시각과 처음 받은 활성 구역의 모의 시각 차를 잰다.
--kill-at-s 시각에 재머 기지에 FAULT_KIND_KILL을 주어 구역을 끄고, 그 뒤 붙은 구독자가 구역을 받지 않는지 본다.

uv run python qa/jam_late.py --out qa/out/p5/jl1 --base-port 48420
uv run python qa/jam_late.py --out qa/out/p5/jl_ui --base-port 48420 --bridge --ui --kill-at-s 120 --until-s 180 --late 5
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
from p5_e2e import P5Stack  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NEAR = ROOT / "qa/scenarios/qa_p5_near.json"


class Late:
    """늦은 구독자: 붙은 시각, 처음 본 truth/state 모의 시각, 받은 jam_zone 이벤트"""

    def __init__(self, name: str, endpoints: list[str], t_wall: float) -> None:
        from swarm_api import BusConfig, open_bus
        from swarm.v1 import truth_pb2
        self.tp = truth_pb2
        self.name, self.t_wall = name, t_wall
        self.lock = threading.Lock()
        self.first_sim_us: int | None = None
        self.first_frame: int | None = None
        self.zones: list[dict] = []
        self.bus = open_bus(BusConfig(connect=endpoints, multicast_scouting=False))
        self.subs = [self.bus.subscribe("truth/state", self._truth),
                     self.bus.subscribe("truth/event/**", self._ev)]

    def _truth(self, s) -> None:  # noqa: ANN001
        if self.first_sim_us is not None:
            return
        f = self.tp.TruthFrame.FromString(s.payload)
        with self.lock:
            if self.first_sim_us is None:
                self.first_sim_us, self.first_frame = f.header.sim_time_us, f.header.frame

    def _ev(self, s) -> None:  # noqa: ANN001
        e = self.tp.TruthEvent.FromString(s.payload)
        if not e.HasField("jam_zone"):
            return
        z = e.jam_zone
        with self.lock:
            self.zones.append({"frame": e.header.frame, "sim_us": e.header.sim_time_us, "seq": e.header.seq,
                               "owner": z.owner, "active": z.active, "r": z.area.circle.radius_m})

    def close(self) -> None:
        for s in self.subs:
            try:
                s.undeclare()
            except Exception:  # noqa: BLE001
                pass
        self.bus.close()

    def summary(self) -> dict:
        with self.lock:
            zs = list(self.zones)
        act = [z for z in zs if z["active"]]
        out = {"name": self.name, "attach_wall_s": self.t_wall, "attach_frame": self.first_frame,
               "n_zone": len(zs), "n_active": len(act), "n_inactive": len(zs) - len(act),
               "owners": sorted({z["owner"] for z in zs})}
        if act and self.first_sim_us is not None:
            out["first_active_frame"] = act[0]["frame"]
            out["first_active_delay_s"] = round((act[0]["sim_us"] - self.first_sim_us) / 1e6, 3)
            gaps = [(b["sim_us"] - a["sim_us"]) / 1e6 for a, b in zip(act, act[1:])]
            if gaps:
                out["period_s_min_max"] = [round(min(gaps), 3), round(max(gaps), 3)]
            out["last_active_frame"] = act[-1]["frame"]
        if len(zs) != len(act):
            out["inactive_frames"] = [z["frame"] for z in zs if not z["active"]]
        return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--scenario", default=str(NEAR))
    ap.add_argument("--base-port", type=int, default=48420)
    ap.add_argument("--late", type=float, nargs="*", default=[3.0, 9.4, 17.7, 31.3, 38.6],
                    help="Core 시작 뒤 늦은 구독자를 붙일 벽시계 초")
    ap.add_argument("--kill-at-s", type=float, default=25.0, help="재머 기지 KILL 모의 초")
    ap.add_argument("--kill", default="jam-site-01")
    ap.add_argument("--until-s", type=float, default=48.0, help="이 모의 초에 끝낸다")
    ap.add_argument("--bridge", action="store_true")
    ap.add_argument("--ui", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    st = P5Stack(out / "stack", Path(a.scenario), base_port=a.base_port, lockstep=False, rate=1.0, record=False,
                 bridge=a.bridge, probe_out=out / "probe.json")
    web, lates = [], []
    res: dict = {"scenario": a.scenario, "kill": None}
    try:
        st.start_one("datalink")
        st.start_one("agent")
        if a.bridge:
            st.start_one("bridge")
        if a.ui:
            web.append(subprocess.Popen(["npm.cmd", "run", "dev", "--", "--port", "45173", "--strictPort"],
                                        cwd=str(ROOT / "ui"), stdout=open(out / "ui.log", "w"),
                                        stderr=subprocess.STDOUT))
        time.sleep(st.settle + 1.0)
        st.start_one("core")
        t0 = time.monotonic()
        print(f"core started; endpoint {st.endpoint()}", flush=True)
        ob = None
        pending = sorted(a.late)
        while True:
            time.sleep(0.1)
            w = time.monotonic() - t0
            if pending and w >= pending[0]:
                tw = pending.pop(0)
                lates.append(Late(f"L{len(lates) + 1}", [st.endpoint()], round(w, 2)))
                print(f"{w:6.1f}s attach {lates[-1].name}", flush=True)
                if ob is None:
                    ob = h.Observer([st.endpoint()])
            lf = (ob.last_frame or 0) if ob else 0
            sim_s = lf * 0.02
            if ob and res["kill"] is None and sim_s >= a.kill_at_s:
                ob.fault(a.kill, "KILL")
                res["kill"] = {"entity": a.kill, "obs_frame": lf, "wall_s": round(w, 2)}
                print(f"{w:6.1f}s KILL {a.kill} at obs frame {lf}", flush=True)
            if sim_s >= a.until_s or st.dead() or w > a.until_s * 3 + 60:
                print(f"stop sim {sim_s:.1f} wall {w:.1f} dead {st.dead()}", flush=True)
                break
        time.sleep(1.0)
        res["late"] = [x.summary() for x in lates]
        res["log_issues"] = h.scan_logs(st)
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str), flush=True)
        for x in lates:
            x.close()
        if ob:
            ob.close()
    finally:
        for w in web:
            subprocess.run(["taskkill", "/PID", str(w.pid), "/T", "/F"], capture_output=True)
        st.down()


if __name__ == "__main__":
    main()

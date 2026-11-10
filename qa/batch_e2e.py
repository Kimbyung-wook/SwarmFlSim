"""DEC-081 항법·제어 일괄화 실제 스택 확인 (TC-QA-127~).

Core·Agent·Datalink 실제 프로세스로 lockstep을 끝까지 돌리고, 같은 시드 반복 실행의 truth를 바이트로 비교한다.
- 끝까지: Core --frames까지 진행, 프레임 누락 없음, 프로세스 종료 없음, 기체가 실제로 비행(motion)
- 일괄 키: 프레임당 NavigationBatch 1건, 참여자당 ControlBatch 1건, 항목 수, 옛 기체별 키 0건
- 재현: truth/state, truth/event, NavigationBatch, ControlBatch를 프레임별로 바이트 비교

uv run --with psutil python qa/batch_e2e.py --out qa/out/batch/det --runs 3
uv run --with psutil python qa/batch_e2e.py --out qa/out/batch/det --runs 3 --only d3w,d3w_a2
"""

import argparse
import hashlib
import json
import math
import sys
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import perf_p1 as pp  # noqa: E402

p0, ROOT, BUILD = pp.p0, pp.ROOT, pp.BUILD


@dataclass(frozen=True)
class Case:
    scn: str
    frames: int
    dof3: bool = False
    agents: int = 1


CASES = {
    "d3w": Case("qa_s6_load100", 3000, dof3=True),                  # REQ-PRF-002 구성
    "d3w_a2": Case("qa_s6_load100", 3000, dof3=True, agents=2),     # ControlBatch/<참여자> 2개
    "d3w_a4": Case("qa_s6_load100", 2000, dof3=True, agents=4),
    "d3f": Case("qa_s6_load100_flock", 1500, dof3=True),
    "s2": Case("qa_s2_swarm20", 3000),
    "s3": Case("qa_s3_link", 3000),                                  # 불완전 링크
    "p5": Case("qa_p5_near", 3000),                                  # 임무장비, 재밍
    "s5": Case("qa_s5_mixed", 2000),
}


def sha(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:16]


class Obs:
    def __init__(self, endpoints: list[str]) -> None:
        from swarm.v1 import fa_pb2, sim_pb2, truth_pb2, vi_pb2
        from swarm_api import BusConfig, open_bus
        self.fa, self.sim, self.truth_pb, self.vi = fa_pb2, sim_pb2, truth_pb2, vi_pb2
        self.bus = open_bus(BusConfig(connect=endpoints, multicast_scouting=False))
        self.lock = threading.Lock()
        self.truth: dict[int, str] = {}
        self.truth_dup = 0
        self.samples: dict[int, dict] = {}
        self.events: list[tuple[str, str]] = []
        self.nav: dict[int, tuple[str, int]] = {}
        self.nav_msgs: Counter = Counter()
        self.ctl: dict[tuple[str, int], tuple[str, int]] = {}
        self.ctl_msgs: Counter = Counter()
        self.ctl_sources: dict[str, set[str]] = defaultdict(set)
        self.legacy: Counter = Counter()
        self.last = -1
        self.state = 0
        self.subs = [self.bus.subscribe("truth/state", self._t), self.bus.subscribe("truth/event/**", self._e),
                     self.bus.subscribe("onboard_batch/NavigationBatch", self._n),
                     self.bus.subscribe("onboard_batch/ControlBatch/*", self._c),
                     self.bus.subscribe("onboard/*/NavigationReport", self._old),
                     self.bus.subscribe("onboard/*/ControlOutput", self._old),
                     self.bus.subscribe("sim/ctrl/status", self._s)]

    def _t(self, s) -> None:  # noqa: ANN001
        m = self.truth_pb.TruthFrame.FromString(s.payload)
        f = m.header.frame
        with self.lock:
            self.truth_dup += f in self.truth
            self.truth[f] = sha(bytes(s.payload))
            self.last = max(self.last, f)
            if f % 500 == 0:    # 실제로 비행했는지 보는 표본
                self.samples[f] = {e.id: (e.kinematics.position.lat_deg, e.kinematics.position.lon_deg, e.kinematics.position.alt_m,
                                          e.kinematics.velocity_ned_mps.x, e.kinematics.velocity_ned_mps.y, e.alive)
                                   for e in m.entities}

    def _e(self, s) -> None:  # noqa: ANN001
        with self.lock:
            self.events.append((s.key, sha(bytes(s.payload))))

    def _n(self, s) -> None:  # noqa: ANN001
        m = self.vi.NavigationBatch.FromString(s.payload)
        with self.lock:
            self.nav[m.header.frame] = (sha(bytes(s.payload)), len(m.reports))
            self.nav_msgs[m.header.frame] += 1

    def _c(self, s) -> None:  # noqa: ANN001
        m = self.fa.ControlBatch.FromString(s.payload)
        who = s.key.rsplit("/", 1)[1]
        with self.lock:
            self.ctl[(who, m.header.frame)] = (sha(bytes(s.payload)), len(m.controls))
            self.ctl_msgs[(who, m.header.frame)] += 1
            self.ctl_sources[who].update(c.header.source for c in m.controls)

    def _old(self, s) -> None:  # noqa: ANN001
        with self.lock:
            self.legacy[s.key.rsplit("/", 1)[1]] += 1

    def _s(self, s) -> None:  # noqa: ANN001
        self.state = self.sim.SimStatus.FromString(s.payload).state

    def close(self) -> None:
        for s in self.subs:
            s.close()
        self.bus.close()


def scenario(c: Case, out: Path) -> tuple[Path, list[str]]:
    d = json.loads((ROOT / "qa/scenarios" / f"{c.scn}.json").read_text(encoding="utf-8"))
    uavs = []
    for e in d["entities"]:
        if e.get("kind") == "uav":
            uavs.append(e["id"])
            if c.dof3:
                e["dynamics"] = "dof3"
    p = out / "scn.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p, uavs


def run_one(c: Case, out: Path, base: int) -> tuple[dict, dict]:
    out.mkdir(parents=True, exist_ok=True)
    src, uavs = scenario(c, out)
    agents = [f"agent-{i}" for i in range(c.agents)]
    pb = p0.export_scenario(src, out / "scenario.pb", ("datalink-0", *agents), 0.0)
    net = pp.Net(base)
    procs: dict = {}
    obs = None
    res: dict = {"frames_target": c.frames, "uavs": len(uavs), "agents": c.agents}
    try:
        procs["datalink"] = p0.Proc("datalink", [p0.exe(BUILD, "datalink", "swarm_datalink"), "--participant", "datalink-0", *net.args("datalink")], out)
        for i, name in enumerate(agents):
            ents = ["--entities", ",".join(uavs[i::c.agents])] if c.agents > 1 else []
            procs[name] = p0.Proc(name, [sys.executable, "-m", "swarm_agent.cli", "--participant", name, *ents, *net.args(name)], out)
        time.sleep(3.0 + c.agents)
        core_args = net.args("core")
        obs = Obs([f"tcp/127.0.0.1:{p}" for p in net.ports.values()])
        time.sleep(1.0)
        t0 = time.monotonic()
        procs["core"] = p0.Proc("core", [p0.exe(BUILD, "core", "swarm_core"), "--scenario", str(pb), "--autostart", "--mode", "lockstep", "--rate", "0",
                                         "--frames", str(c.frames), *core_args], out)
        deadline = t0 + 420
        startup = t0 + 45
        while time.monotonic() < deadline:
            if obs.last >= c.frames - 1 or obs.state == obs.sim.SIM_RUN_STATE_STOPPED:
                break
            if any(not p.alive() for n, p in procs.items() if n != "core"):
                break
            if not procs["core"].alive():
                break
            if time.monotonic() > startup and obs.last < 50:
                res["stalled"] = True
                break
            time.sleep(0.02)
        res["wall_s"] = round(time.monotonic() - t0, 1)
        time.sleep(1.0)
        res["state"] = obs.sim.SimRunState.Name(obs.state)
        res["dead"] = [n for n, p in procs.items() if not p.alive() and n != "core"]
        res["core_alive"] = procs["core"].alive()
        with obs.lock:
            fs = sorted(obs.truth)
            res |= {"first": fs[0] if fs else None, "last": fs[-1] if fs else None,
                    "truth_missing": (fs[-1] - fs[0] + 1 - len(fs)) if fs else None, "truth_dup": obs.truth_dup,
                    "events": len(obs.events), "legacy": dict(obs.legacy),
                    "nav_frames": len(obs.nav), "nav_multi": sum(1 for v in obs.nav_msgs.values() if v != 1),
                    "nav_items": dict(Counter(n for _, n in obs.nav.values())),
                    "ctl_msgs": len(obs.ctl), "ctl_multi": sum(1 for v in obs.ctl_msgs.values() if v != 1),
                    "ctl_items": dict(Counter(n for _, n in obs.ctl.values())),
                    "ctl_sources": {k: len(v) for k, v in obs.ctl_sources.items()}}
            cover = len({f for _, f in obs.ctl})
            res["ctl_frames"] = cover
            res["motion"] = motion(obs.samples, uavs)
            data = {"truth": dict(obs.truth), "events": list(obs.events), "nav": {k: v[0] for k, v in obs.nav.items()},
                    "ctl": {k: v[0] for k, v in obs.ctl.items()}}
    finally:
        if obs is not None:
            try:
                obs.close()
            except Exception:  # noqa: BLE001
                pass
        for p in procs.values():
            p.kill()    # Proc.kill은 자기가 띄운 PID만 종료한다
            p.log.close()
    logs = {n: (out / f"{n}.log").read_text(encoding="utf-8", errors="replace") for n in procs}
    res["warn"] = {n: [l[:200] for l in t.splitlines() if "WARNING" in l or "Traceback" in l or "ERROR" in l][:5] for n, t in logs.items()}
    return res, data


def motion(samples: dict[int, dict], uavs: list[str]) -> dict:
    """표본 프레임 사이 기체별 이동. 위도·경도를 평면 m로 근사한다"""
    fs = sorted(samples)
    if len(fs) < 2:
        return {}
    a, b = samples[fs[0]], samples[fs[-1]]
    def dist(p, q) -> float:
        return math.hypot((q[0] - p[0]) * 111_000, (q[1] - p[1]) * 111_000 * math.cos(math.radians(p[0])))
    disp = [dist(a[u], b[u]) for u in uavs if u in a and u in b]
    path = [sum(dist(samples[f0][u], samples[f1][u]) for f0, f1 in zip(fs, fs[1:]) if u in samples[f0] and u in samples[f1]) for u in uavs]
    spd = [math.hypot(b[u][3], b[u][4]) for u in uavs if u in b]
    return {"frames": [fs[0], fs[-1]], "disp_m": [round(min(disp)), round(sorted(disp)[len(disp) // 2]), round(max(disp))],
            "path_m": [round(min(path)), round(sorted(path)[len(path) // 2]), round(max(path))],
            "speed_mps": [round(min(spd), 1), round(sorted(spd)[len(spd) // 2], 1), round(max(spd), 1)],
            "alt_m": [round(min(b[u][2] for u in uavs if u in b)), round(max(b[u][2] for u in uavs if u in b))],
            "alive": sum(1 for u in uavs if u in b and b[u][5])}


def compare(a: dict, b: dict) -> dict:
    out = {}
    for k in ("truth", "nav", "ctl"):
        common = sorted(set(a[k]) & set(b[k]))
        bad = [x for x in common if a[k][x] != b[k][x]]
        out[k] = {"common": len(common), "diff": len(bad), "first": bad[0] if bad else None,
                  "only_a": len(set(a[k]) - set(b[k])), "only_b": len(set(b[k]) - set(a[k]))}
    n = min(len(a["events"]), len(b["events"]))
    ea, eb = Counter(a["events"][:n]), Counter(b["events"][:n])
    out["events"] = {"n": [len(a["events"]), len(b["events"])], "order_diff": sum(1 for x, y in zip(a["events"], b["events"]) if x != y),
                     "set_diff": sum(((ea - eb) + (eb - ea)).values())}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="qa/out/batch/det")
    ap.add_argument("--only", default="")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--base-port", type=int, default=49900)
    a = ap.parse_args()
    root = ROOT / a.out
    root.mkdir(parents=True, exist_ok=True)
    names = [n for n in a.only.split(",") if n] or list(CASES)
    base = a.base_port
    for name in names:
        c = CASES[name]
        runs, rep = [], {"case": c.__dict__, "runs": [], "cmp": []}
        for r in range(a.runs):
            res, d = run_one(c, root / name / f"r{r}", base)
            base += 12
            runs.append(d)
            rep["runs"].append(res)
            if r:
                rep["cmp"].append(compare(runs[0], d))
            (root / name / "result.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            brief = {k: res.get(k) for k in ("wall_s", "state", "last", "truth_missing", "legacy", "nav_multi", "nav_items", "ctl_multi", "ctl_items", "dead", "stalled")}
            print(json.dumps({"name": name, "r": r, **brief, "cmp": rep["cmp"][-1] if r else None}, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()

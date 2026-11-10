"""P1 성능 병목 측정 (TC-QA-114~, DEC-079, OPN-067). release 빌드, lockstep 최대 배속(rate 0).

uv run --with psutil python qa/perf_p1.py --out qa/out/perf --only d3_w,d3_f --repeat 3
uv run --with psutil python qa/perf_p1.py --list

시나리오: m_* = qa_s6_load100 원본(2/3-DoF 혼합 50+50), d3_* = 같은 파일에서 100대 모두 dof3로 바꾼 것.
창: 틱 warm부터 meas개. 속도는 sim/ctrl/status(50프레임마다)의 프레임과 벽시계로 잰다.
"""

import argparse
import importlib.util
import json
import shutil
import sys
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("run_p0_demo", ROOT / "scripts" / "run_p0_demo.py")
p0 = importlib.util.module_from_spec(_spec)
sys.modules["run_p0_demo"] = p0
_spec.loader.exec_module(p0)

import psutil  # noqa: E402

BUILD = ROOT / "build" / "msvc-release"
SCN = {"m": "qa_s6_load100", "mf": "qa_s6_load100_flock", "d3": "qa_s6_load100", "d3f": "qa_s6_load100_flock"}


@dataclass(frozen=True)
class Cfg:
    name: str
    scn: str = "d3"             # m | mf | d3 | d3f
    ma: str = ""                # 비우면 시나리오 그대로
    logger: bool = False
    state_off: bool = False     # Datalink --state-period 0 (link/state 1 Hz 전 쌍 발행을 끈다)
    agents: int = 1             # 0이면 Agent 없음
    mode: str = "plain"         # perf_agent --perf-mode
    nosub: bool = False         # Agent가 기체를 맡지 않음(틱→FrameDone만)
    timeline: bool = False      # 틱·FrameDone 수신 시각 기록
    count: bool = False         # 버스 전체 메시지 수 (rate 0.3으로)
    switch: float = 0.0
    narrow: bool = False        # Agent의 onboard/<id>/* 구독을 메시지별로 (자기 ControlOutput 수신 제거)
    pcore: bool = False         # 프로세스를 P 코어(논리 0~15)에 고정
    rate: float = 0.0
    warm: int = 250
    meas: int = 1250


C = [
    # 1. 실효 배속
    Cfg("m_w"), Cfg("m_w_log", logger=True), Cfg("m_hold", ma="hold"),
    Cfg("m_f", scn="mf"), Cfg("m_f_log", scn="mf", logger=True),
    Cfg("d3_w"), Cfg("d3_w_log", logger=True), Cfg("d3_hold", ma="hold"),
    Cfg("d3_f", scn="d3f"), Cfg("d3_f_log", scn="d3f", logger=True),
    # 비용 사다리 (뒤로 갈수록 Agent 일을 뺀다)
    Cfg("d3_nofa", ma="hold", mode="no_fa"), Cfg("d3_nosub", nosub=True), Cfg("d3_noagent", agents=0),
    Cfg("m_nofa", scn="m", ma="hold", mode="no_fa"), Cfg("m_nosub", scn="m", nosub=True), Cfg("m_noagent", scn="m", agents=0),
    # 2. 프레임 분해
    Cfg("d3_w_tl", timeline=True), Cfg("d3_f_tl", scn="d3f", timeline=True), Cfg("d3_hold_tl", ma="hold", timeline=True),
    Cfg("m_w_tl", scn="m", timeline=True), Cfg("m_f_tl", scn="mf", timeline=True),
    Cfg("d3_w_ti", mode="timers", timeline=True), Cfg("d3_f_ti", scn="d3f", mode="timers", timeline=True),
    Cfg("m_w_ti", scn="m", mode="timers"), Cfg("m_f_ti", scn="mf", mode="timers"),
    Cfg("d3_nofa_tl", ma="hold", mode="no_fa", timeline=True), Cfg("d3_nosub_tl", nosub=True, timeline=True),
    Cfg("d3_noagent_tl", agents=0, timeline=True),
    Cfg("d3_w_pr", mode="cprofile"), Cfg("d3_f_pr", scn="d3f", mode="cprofile"),
    # 3. 메시지 수
    Cfg("d3_w_cnt", count=True, rate=0.3, warm=250, meas=500), Cfg("d3_f_cnt", scn="d3f", count=True, rate=0.1, warm=250, meas=500),
    Cfg("m_w_cnt", scn="m", count=True, rate=0.3, warm=250, meas=500),
    # 5. Agent 분할 (실측)
    *[Cfg(f"d3_w_a{n}", agents=n) for n in (2, 4, 8)],
    *[Cfg(f"d3_f_a{n}", scn="d3f", agents=n) for n in (2, 4, 8)],
    *[Cfg(f"d3_w_a{n}_tl", agents=n, timeline=True) for n in (2, 4, 8)],
    # GIL 전환 주기 민감도
    Cfg("d3_w_sw", switch=0.0001), Cfg("d3_f_sw", scn="d3f", switch=0.0001),
    # 구독 축소 (자기 ControlOutput 수신 제거)
    Cfg("d3_w_nar", narrow=True), Cfg("d3_w_nar_ti", narrow=True, mode="timers"),
    # P 코어 고정 민감도 (i9-14900HX, 논리 0~15가 P)
    Cfg("d3_w_nols", state_off=True), Cfg("d3_w_nols_P", state_off=True, pcore=True), Cfg("d3_nofa_nols_P", ma="hold", mode="no_fa", state_off=True, pcore=True),
    Cfg("d3_w_nols_tl", state_off=True, timeline=True),
    Cfg("d3_w_P", pcore=True), Cfg("d3_f_P", scn="d3f", pcore=True), Cfg("d3_hold_P", ma="hold", pcore=True),
    Cfg("d3_nofa_P", ma="hold", mode="no_fa", pcore=True), Cfg("d3_nosub_P", nosub=True, pcore=True), Cfg("d3_noagent_P", agents=0, pcore=True),
    Cfg("d3_w_ti_P", mode="timers", timeline=True, pcore=True), Cfg("d3_f_ti_P", scn="d3f", mode="timers", timeline=True, pcore=True),
    Cfg("d3_w_nar_P", narrow=True, pcore=True), Cfg("m_w_P", scn="m", pcore=True), Cfg("m_f_P", scn="mf", pcore=True),
    *[Cfg(f"d3_w_a{n}_P", agents=n, pcore=True) for n in (2, 4, 8)],
    *[Cfg(f"d3_f_a{n}_P", scn="d3f", agents=n, pcore=True) for n in (2, 4, 8)],
    Cfg("d3_w_a4_nar_P", agents=4, narrow=True, pcore=True),
]
BY = {c.name: c for c in C}


def scenario(c: Cfg, out: Path) -> tuple[Path, list[str]]:
    d = json.loads((ROOT / "qa" / "scenarios" / f"{SCN[c.scn]}.json").read_text(encoding="utf-8"))
    uavs = []
    for e in d["entities"]:
        if e.get("kind") != "uav":
            continue
        uavs.append(e["id"])
        if c.scn.startswith("d3"):
            e["dynamics"] = "dof3"
        if c.ma:
            e["autonomy"]["ma_plugin"] = c.ma
            e["autonomy"].pop("ma_params", None)
    p = out / "scn.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p, uavs


class Net:
    def __init__(self, base: int) -> None:
        self.base, self.ports, self.alive = base, {}, []

    def args(self, name: str) -> list[str]:
        mine = self.base + len(self.ports)
        self.ports[name] = mine
        a = ["--no-multicast", "--listen", f"tcp/127.0.0.1:{mine}"]
        for o in self.alive:
            a += ["--connect", f"tcp/127.0.0.1:{self.ports[o]}"]
        self.alive.append(name)
        return a


def pin(c: Cfg, procs: dict) -> None:
    if not c.pcore:
        return
    for pr in procs.values():
        try:
            root = psutil.Process(pr.p.pid)
            for q in [root] + root.children(recursive=True):
                q.cpu_affinity(list(range(16)))
        except psutil.Error:
            pass


def snap(procs: dict) -> dict:
    t = time.perf_counter()
    res = {}
    for n, pr in procs.items():
        try:
            root = psutil.Process(pr.p.pid)
            ps = [root] + root.children(recursive=True)
            cpu = 0.0
            threads: dict = {}
            for q in ps:
                ct = q.cpu_times()
                cpu += ct.user + ct.system
                for th in q.threads():
                    threads[th.id] = th.user_time + th.system_time
            res[n] = (cpu, threads)
        except psutil.Error:
            pass
    return {"t": t, "procs": res, "cores": psutil.cpu_times(percpu=True)}


def cpu_delta(a: dict, b: dict) -> dict:
    dt = b["t"] - a["t"]
    out = {}
    for n in a["procs"]:
        if n not in b["procs"]:
            continue
        ca, ta = a["procs"][n]
        cb, tb = b["procs"][n]
        d = sorted(((tb[i] - ta.get(i, 0.0)) / dt * 100 for i in tb), reverse=True)
        out[n] = {"cpu_pct": round((cb - ca) / dt * 100, 1), "top_threads_pct": [round(x, 1) for x in d[:6]],
                  "n_busy_threads": sum(1 for x in d if x > 5)}
    cores = []
    for x, y in zip(a["cores"], b["cores"]):
        total = sum(y) - sum(x)
        cores.append(100 * (1 - (y.idle - x.idle) / total) if total > 0 else 0.0)
    out["_system"] = {"busy_pct_avg": round(sum(cores) / len(cores), 1), "core_max": round(max(cores), 1),
                      "cores_gt50": sum(1 for x in cores if x > 50), "per_core": [round(x) for x in cores]}
    return out


def normalize(key: str) -> str:
    p = key.split("/")
    if p[0] == "onboard":
        return f"onboard/*/{p[-1]}"
    if p[0] == "swarm" and len(p) >= 4:
        return f"swarm/*/{p[2]}/{'/'.join(p[3:])}"
    if p[:2] == ["sim", "param"]:
        return "sim/param/*"
    if p[0] == "link" and len(p) >= 2:
        return f"link/{p[1]}"
    return key


class Obs:
    """sim/ctrl/status만 받는 가벼운 관측자. timeline·count면 구독을 더한다"""

    def __init__(self, endpoints: list[str], c: Cfg) -> None:
        from swarm.v1 import sim_pb2
        from swarm_api import BusConfig, open_bus
        self.pb, self.c = sim_pb2, c
        self.bus = open_bus(BusConfig(connect=endpoints, multicast_scouting=False))
        self.frames: list[tuple[float, int, int]] = []
        self.ev: list[tuple[float, str, int]] = []
        self.cnt: Counter = Counter()
        self.byt: Counter = Counter()
        self.c_on = False
        self.subs = [self.bus.subscribe("sim/ctrl/status", self.status)]
        if c.timeline:
            self.subs.append(self.bus.subscribe("sim/clock/tick", self.tick))
            self.subs.append(self.bus.subscribe("sim/clock/done/*", self.done))
        if c.count:
            self.subs.append(self.bus.subscribe("**", self.all))

    def status(self, s) -> None:
        m = self.pb.SimStatus.FromString(s.payload)
        self.frames.append((time.perf_counter(), m.frame, m.frame_overruns))

    def tick(self, s) -> None:
        t = time.perf_counter()
        self.ev.append((t, "tick", self.pb.ClockTick.FromString(s.payload).frame))

    def done(self, s) -> None:
        t = time.perf_counter()
        d = self.pb.FrameDone.FromString(s.payload)
        self.ev.append((t, d.participant, d.frame))

    def all(self, s) -> None:
        if self.c_on:
            k = normalize(s.key)
            self.cnt[k] += 1
            self.byt[k] += len(s.payload)

    def ready(self, names: list[str]) -> None:
        """시험용: 적재를 끝낸 참여자의 준비 신호를 대신 낸다 (D-31 우회)"""
        for n in names:
            d = self.pb.FrameDone(participant=n, frame=0)
            self.bus.put(f"sim/clock/done/{n}", d.SerializeToString(), "application/protobuf;swarm.v1.FrameDone")

    def last(self) -> int:
        return self.frames[-1][1] if self.frames else -1

    def close(self) -> None:
        for s in self.subs:
            s.close()
        self.bus.close()


def timeline(ev: list, c: Cfg, f0: int, f1: int) -> dict:
    ev = sorted(ev)
    by: dict = defaultdict(dict)
    for t, who, f in ev:
        by[f].setdefault(who, t)  # 같은 프레임 0 준비 신호는 창 밖
    def q(v):
        v = sorted(v)
        return {"mean": round(1e3 * sum(v) / len(v), 3), "p50": round(1e3 * v[len(v) // 2], 3),
                "p95": round(1e3 * v[int(len(v) * .95)], 3), "max": round(1e3 * v[-1], 3)}
    dl, ag, core, tot, agmax = [], [], [], [], []
    for f in range(f0, f1):
        a, b = by.get(f), by.get(f + 1)
        if not a or not b or "tick" not in a or "tick" not in b:
            continue
        parts = [k for k in a if k != "tick"]
        ags = [a[k] for k in parts if k.startswith("agent")]
        dls = [a[k] for k in parts if k.startswith("datalink")]
        if not dls or (c.agents and len(ags) < c.agents):
            continue
        t0 = a["tick"]
        d = dls[0] - t0
        dl.append(d)
        last = max(dls + ags)
        ag.append((max(ags) - t0) if ags else 0.0)
        core.append(b["tick"] - last)
        tot.append(b["tick"] - t0)
    if not tot:
        return {}
    r = {"n": len(tot), "tick_to_datalink_done": q(dl), "tick_to_agent_done": q(ag),
         "last_done_to_next_tick(core)": q(core), "frame_total": q(tot)}
    r["agent_is_last_pct"] = round(100 * sum(1 for a, d in zip(ag, dl) if a > d) / len(tot), 1)
    # 프레임이 길게 끊기는 비중 (평균과 p50의 차이가 어디서 오는지 본다). 임계값은 ms
    for lim in (5, 10, 25):
        big = [x for x in tot if x * 1e3 >= lim]
        r[f"frames_ge_{lim}ms"] = {"n": len(big), "ms_per_frame": round(1e3 * sum(big) / len(tot), 3)}
    return r


def loaded(out: Path, agents: list[str]) -> bool:
    try:
        if "scenario received" not in (out / "datalink.log").read_text(encoding="utf-8", errors="replace"):
            return False
        return all("loaded '" in (out / f"{a}.log").read_text(encoding="utf-8", errors="replace") for a in agents)
    except OSError:
        return False


class StartStall(Exception):
    """시작 후 프레임이 진행하지 않는다 (준비 신호가 Core에 닿지 않음)"""


def run_one(c: Cfg, out: Path, base: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    src, uavs = scenario(c, out)
    agents = [f"agent-{i}" for i in range(c.agents)]
    pb = p0.export_scenario(src, out / "scenario.pb", ("datalink-0", *agents), c.rate)
    net = Net(base)
    # 8분할은 Core 재발행으로 시나리오를 받는 시작이 멈춘다(D-31). 파일로 직접 적재하고 준비 신호는 관측자가 대신 낸다
    feed = ["--scenario", str(pb)] if c.agents >= 8 else []
    procs: dict = {}
    res: dict = {"cfg": c.__dict__, "out": str(out)}
    obs = None
    try:
        if c.logger:
            procs["logger"] = p0.Proc("logger", [p0.exe(BUILD, "logger", "swarm_logger"), "record", "--out", str(out / "rec.mcap"), *net.args("logger")], out)
        procs["datalink"] = p0.Proc("datalink", [p0.exe(BUILD, "datalink", "swarm_datalink"), "--participant", "datalink-0", *feed, *(["--state-period", "0"] if c.state_off else []), *net.args("datalink")], out)
        for i, name in enumerate(agents):
            ents = ["--entities", "__none__"] if c.nosub else (["--entities", ",".join(uavs[i::c.agents])] if c.agents > 1 else [])
            perf = ["--perf-mode", c.mode, "--perf-warm", str(c.warm), "--perf-frames", str(c.meas)]
            if c.mode != "plain":
                perf += ["--perf-out", str(out / f"{name}.json")]
            if c.switch:
                perf += ["--perf-switch", str(c.switch)]
            if c.narrow:
                perf += ["--perf-narrow"]
            procs[name] = p0.Proc(name, [sys.executable, str(ROOT / "qa" / "perf_agent.py"), *perf, "--participant", name, *feed, *ents, *net.args(name)], out)
        time.sleep(3.0 + 1.0 * c.agents if c.agents >= 4 else 2.0 + 0.4 * c.agents)
        pin(c, procs)
        core_args = net.args("core")
        procs["core"] = p0.Proc("core", [p0.exe(BUILD, "core", "swarm_core"), "--scenario", str(pb), "--autostart", "--mode", "lockstep", "--rate", str(c.rate), *core_args], out)
        pin(c, procs)
        obs = Obs([f"tcp/127.0.0.1:{p}" for p in net.ports.values()], c)
        deadline = time.monotonic() + 420
        startup = time.monotonic() + 45
        next_chk, t_loaded, proxied = 0.0, 0.0, 0
        target0, target1 = c.warm, c.warm + c.meas
        while obs.last() < target0 and time.monotonic() < deadline:
            if any(not p.alive() for p in procs.values()):
                break
            if time.monotonic() > startup and obs.last() < 50:
                raise StartStall(c.name)
            now = time.monotonic()
            if obs.last() < 1 and now >= next_chk:
                next_chk = now + 0.5
                if loaded(out, agents):
                    t_loaded = t_loaded or now
                    if now - t_loaded >= 3.0:
                        obs.ready(["datalink-0", *agents])
                        proxied += 1
                        print(json.dumps({"name": c.name, "ready_proxy": proxied, "last": obs.last()}), flush=True)
                        t_loaded = now
            time.sleep(0.005)
        sa = snap(procs)
        f_a = obs.last()
        obs.c_on = True
        while obs.last() < target1 and time.monotonic() < deadline:
            if any(not p.alive() for p in procs.values()):
                break
            time.sleep(0.005)
        obs.c_on = False
        sb = snap(procs)
        res["ready_proxied"] = proxied
        res["dead"] = [n for n, p in procs.items() if not p.alive()]
        res["timeout"] = obs.last() < target1
        fr = [x for x in obs.frames if x[1] >= target0]
        if len(fr) >= 2:
            (t0, f0, o0), (t1, f1, o1) = fr[0], fr[-1]
            wall = t1 - t0
            res.update(frames=f1 - f0, wall_s=round(wall, 3), speed_x=round((f1 - f0) * 0.02 / wall, 3),
                       frame_ms=round(1e3 * wall / (f1 - f0), 3), overruns=o1 - o0)
        res["cpu"] = cpu_delta(sa, sb)
        if c.timeline:
            res["timeline"] = timeline(obs.ev, c, target0, target1)
        if c.count:
            n = max(1, obs.last() - f_a)
            res["msg_per_frame"] = {k: round(v / n, 2) for k, v in obs.cnt.most_common()}
            res["bytes_per_frame"] = {k: round(v / n) for k, v in obs.byt.most_common()}
            res["count_frames"] = n
        time.sleep(0.3 if c.mode == "plain" else 1.5)  # perf 파일이 쓰일 시간
        for name in agents:
            fp = out / f"{name}.json"
            if fp.exists():
                res.setdefault("agent_perf", {})[name] = json.loads(fp.read_text(encoding="utf-8"))
    finally:
        if obs is not None:
            try:
                obs.close()
            except Exception:  # noqa: BLE001
                pass
        for p in procs.values():
            p.kill()  # Proc.kill은 자기가 띄운 PID만 종료한다
            p.log.close()
    logs = {n: (out / f"{n}.log").read_text(encoding="utf-8", errors="replace") for n in procs}
    res["warnings"] = {n: sum(1 for l in t.splitlines() if "WARNING" in l or "Traceback" in l or "error" in l.lower()) for n, t in logs.items()}
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="qa/out/perf")
    ap.add_argument("--only", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--base-port", type=int, default=49000)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--meas", type=int, default=0)
    ap.add_argument("--resume", action="store_true", help="결과가 있는 실행은 건너뛴다")
    a = ap.parse_args()
    if a.list:
        print("\n".join(BY))
        return
    names = [n for n in a.only.split(",") if n] or list(BY)
    base = a.base_port
    for r in range(a.repeat):
        for n in names:
            c = BY[n]
            if a.meas:
                c = replace(c, meas=a.meas)
            d = ROOT / a.out / n / f"r{r}"
            if a.resume and (d / "result.json").exists() and json.loads((d / "result.json").read_text(encoding="utf-8")).get("speed_x"):
                continue
            res = None
            for attempt in range(2):
                try:
                    res = run_one(c, d, base)
                    res["start_stalls"] = attempt
                    (d / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
                    break
                except StartStall:
                    stall = ROOT / a.out / "_stalls" / f"{n}_r{r}_a{attempt}"
                    stall.parent.mkdir(parents=True, exist_ok=True)
                    shutil.rmtree(stall, ignore_errors=True)
                    time.sleep(1.0)
                    shutil.copytree(d, stall, ignore=shutil.ignore_patterns("*.mcap"))
                    print(json.dumps({"name": n, "r": r, "stall_attempt": attempt}), flush=True)
                finally:
                    base = 49000 + (base - 49000 + 20) % 800
            if res is None:
                continue
            cpu = res.get("cpu", {})
            print(json.dumps({"name": n, "r": r, "speed_x": res.get("speed_x"), "frame_ms": res.get("frame_ms"), "dead": res.get("dead"),
                              "timeout": res.get("timeout"), "agent_cpu": cpu.get("agent-0", {}).get("cpu_pct"), "core_cpu": cpu.get("core", {}).get("cpu_pct"),
                              "dl_cpu": cpu.get("datalink", {}).get("cpu_pct"), "sys": cpu.get("_system", {}).get("busy_pct_avg")}), flush=True)


if __name__ == "__main__":
    main()

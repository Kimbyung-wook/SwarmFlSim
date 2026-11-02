"""QA 하니스 (TC-QA-*). 프로세스 묶음을 띄우고 버스에 관측자를 붙여 이상 징후를 모은다.

scripts/run_p0_demo.py 의 Proc·Mesh·export_scenario 를 재사용한다.
"""

import importlib.util
import json
import math
import sys
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

QA = Path(__file__).resolve().parent
ROOT = QA.parent
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("run_p0_demo", ROOT / "scripts" / "run_p0_demo.py")
p0 = importlib.util.module_from_spec(_spec)
sys.modules["run_p0_demo"] = p0
_spec.loader.exec_module(p0)

GCS = "gcs-01"
BUILD = Path(__file__).resolve().parent.parent / "build" / "msvc-debug"
BASE_PORT = 17900
M_PER_DEG = 111_320.0
CT = "application/protobuf;swarm.v1."


def pb():
    from swarm.v1 import (c2_pb2, common_pb2, link_pb2, options_pb2, sim_pb2, truth_pb2)  # noqa: F401
    return sim_pb2, truth_pb2, link_pb2, c2_pb2, common_pb2, options_pb2


class Stack:
    """Logger → Datalink → Agent → Bridge → Core 묶음. 개별 프로세스를 죽였다 다시 띄울 수 있다."""

    registry: list["Stack"] = []

    def __init__(self, out: Path, scenario: Path, base_port: int = BASE_PORT, lockstep: bool = False,
                 rate: float = 1.0, record: bool = True, bridge: bool = False, bridge_port: int = 8765,
                 core_extra: list[str] | None = None, mode: str | None = None, autostart: bool = True,
                 settle: float = 2.0, hz: int | None = None):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.base, self.lockstep, self.rate = base_port, lockstep, rate
        self.mode = mode or ("lockstep" if lockstep else "realtime")
        self.autostart, self.settle = autostart, settle
        self.json = scenario
        self.pbfile = p0.export_scenario(scenario, out / "scenario.pb", ("datalink-0", "agent-0") if lockstep else (),
                                         rate)
        self.record, self.bridge, self.bridge_port = record, bridge, bridge_port
        self.core_extra = core_extra or []
        self.hz = hz
        self.ports: dict[str, int] = {}
        self.procs: dict[str, "p0.Proc"] = {}
        self.gen: Counter = Counter()
        self.mcap = out / "rec.mcap"
        Stack.registry.append(self)

    # 명령행 -------------------------------------------------------------
    def _net(self, name: str) -> list[str]:
        if name not in self.ports:
            self.ports[name] = self.base + len(self.ports)
        mine = self.ports[name]
        args = ["--no-multicast", "--listen", f"tcp/127.0.0.1:{mine}"]
        for other, port in self.ports.items():
            if other != name and (other in self.procs and self.procs[other].alive()):
                args += ["--connect", f"tcp/127.0.0.1:{port}"]
        return args

    def _cmd(self, name: str) -> list[str]:
        py = sys.executable
        # lockstep: 시나리오 재발행 수정(4e3c4c3) 확인을 위해 Datalink·Agent에는 직접 주지 않는다
        feed = [] if self.lockstep else ["--scenario", str(self.pbfile)]
        if name == "logger":
            return [p0.exe(BUILD, "logger", "swarm_logger"), "record", "--out", str(self.mcap)]
        if name == "datalink":
            return [p0.exe(BUILD, "datalink", "swarm_datalink"), *feed,
                    *(["--participant", "datalink-0"] if self.lockstep else ["--no-frame-done"])]
        if name == "agent":
            return [py, "-m", "swarm_agent.cli", *feed]
        if name == "bridge":
            return [py, "-m", "swarm_bridge.cli", "--port", str(self.bridge_port)]
        if name == "core":
            c = [p0.exe(BUILD, "core", "swarm_core"), "--scenario", str(self.pbfile)]
            if self.autostart:
                c += ["--autostart", "--mode", self.mode]
                if self.mode == "lockstep":
                    c += ["--rate", str(self.rate)]
            if self.hz:
                c += ["--hz", str(self.hz)]
            return c + self.core_extra
        raise KeyError(name)

    def start_one(self, name: str, cmd_extra: list[str] | None = None) -> None:
        self.gen[name] += 1
        tag = name if self.gen[name] == 1 else f"{name}.{self.gen[name]}"
        net = self._net(name)
        self.procs[name] = p0.Proc(tag, [*self._cmd(name), *(cmd_extra or []), *net], self.out)

    def up(self) -> "Stack":
        if self.record:
            self.start_one("logger")
        self.start_one("datalink")
        self.start_one("agent")
        if self.bridge:
            self.start_one("bridge")
        time.sleep(self.settle)
        self.start_one("core")
        return self

    def kill(self, name: str, graceful: bool = False) -> None:
        pr = self.procs[name]
        if graceful:
            pr.interrupt()
            end = time.monotonic() + 8
            while pr.alive() and time.monotonic() < end:
                time.sleep(0.2)
        pr.kill()
        pr.log.close()

    def restart(self, name: str, cmd_extra: list[str] | None = None, graceful: bool = False) -> None:
        self.kill(name, graceful)
        time.sleep(0.5)
        self.start_one(name, cmd_extra)

    def dead(self) -> list[str]:
        return [f"{n}(code {p.p.returncode})" for n, p in self.procs.items() if not p.alive()]

    def down(self) -> None:
        p0.stop(list(self.procs.values()))

    @classmethod
    def down_all(cls) -> None:
        """시험이 예외로 끝나도 이 하니스가 띄운 묶음을 모두 내린다"""
        for s in cls.registry:
            s.down()
        cls.registry.clear()

    def endpoint(self, name: str = "datalink") -> str:
        return f"tcp/127.0.0.1:{self.ports[name]}"

    def log_text(self) -> dict[str, str]:
        return {n: p.log_path.read_text(encoding="utf-8", errors="replace") for n, p in self.procs.items()}

    def __enter__(self) -> "Stack":
        return self.up()

    def __exit__(self, *a) -> None:
        self.down()


@dataclass
class Finding:
    kind: str
    detail: str
    t_wall: float = 0.0

    def __str__(self) -> str:
        return f"[{self.kind}] {self.detail}"


class Observer:
    """버스에 붙는 관측자: truth/state·sim/ctrl/status·sim/clock/tick·link/outcome·sim/param·truth/event·GCS rx"""

    def __init__(self, endpoints: list[str], jump_m: float = 400.0):
        from swarm_api import BusConfig, open_bus
        self.bus = open_bus(BusConfig(connect=endpoints, multicast_scouting=False))
        self.lock = threading.Lock()
        self.findings: list[Finding] = []
        self.counts: Counter = Counter()
        self.frames = 0
        self.last_frame: int | None = None
        self.last_t_us: int | None = None
        self.last_wall = time.monotonic()
        self.first_frame: int | None = None
        self.pos: dict[str, tuple[float, float, float]] = {}
        self.vel: dict[str, tuple[float, float, float]] = {}
        self.alive: dict[str, bool] = {}
        self.entity_n: list[int] = []
        self.status = None
        self.status_hist: list[tuple[float, int, int, int, float]] = []
        self.ticks = 0
        self.last_tick: tuple[int, int] | None = None
        self.params: dict[str, object] = {}
        self.param_log: list = []
        self.events: list[tuple[str, object]] = []
        self.taskstatus: dict[str, list[str]] = defaultdict(list)
        self.outcomes: Counter = Counter()
        self.drop_reasons: Counter = Counter()
        self.latency_us: list[int] = []
        self.link_seq: dict[tuple[str, str, str], int] = {}
        self.reorder = 0
        self.gap_frames = 0
        self.jump_m = jump_m
        self.traj: dict[str, list[tuple[int, float, float, float]]] = defaultdict(list)
        self.keep_traj = False
        self.expect_reset_until = 0.0
        self.seq = 0
        sim, truth, link, c2, common, _ = pb()
        self.m = (sim, truth, link, c2, common)
        self.subs = [
            self.bus.subscribe("truth/state", self._truth),
            self.bus.subscribe("sim/ctrl/status", self._status),
            self.bus.subscribe("sim/clock/tick", self._tick),
            self.bus.subscribe("link/outcome/**", self._outcome),
            self.bus.subscribe("sim/param/**", self._param),
            self.bus.subscribe("truth/event/**", self._event),
            self.bus.subscribe(f"swarm/{GCS}/rx/**", self._rx),
        ]

    def add(self, kind: str, detail: str) -> None:
        self.findings.append(Finding(kind, detail, time.monotonic()))

    def reset_expected(self, secs: float = 6.0) -> None:
        self.expect_reset_until = time.monotonic() + secs
        self.last_frame = self.last_t_us = None

    # 구독자 -------------------------------------------------------------
    def _truth(self, s) -> None:
        sim, truth, *_ = self.m
        try:
            f = truth.TruthFrame.FromString(s.payload)
        except Exception as e:  # noqa: BLE001
            with self.lock:
                self.add("decode", f"truth/state 해석 실패: {e}")
            return
        with self.lock:
            fr, t = f.header.frame, f.header.sim_time_us
            self.frames += 1
            self.last_wall = time.monotonic()
            if self.first_frame is None:
                self.first_frame = fr
            resetting = time.monotonic() < self.expect_reset_until
            if self.last_frame is not None and not resetting:
                if fr < self.last_frame:
                    self.add("time_regress", f"frame {self.last_frame}→{fr}")
                elif fr == self.last_frame:
                    self.counts["dup_frame"] += 1
                else:
                    self.gap_frames += fr - self.last_frame - 1
                if t < self.last_t_us:
                    self.add("time_regress", f"sim_time {self.last_t_us}→{t}")
            self.last_frame, self.last_t_us = fr, t
            self.entity_n.append(len(f.entities))
            for e in f.entities:
                p, v = e.kinematics.position, e.kinematics.velocity_ned_mps
                vals = (p.lat_deg, p.lon_deg, p.alt_m, v.x, v.y, v.z)
                if not all(math.isfinite(x) for x in vals):
                    self.add("nan_inf", f"{e.id} frame {fr}: {vals}")
                    continue
                prev = self.pos.get(e.id)
                if prev and not resetting:
                    dn = (p.lat_deg - prev[0]) * M_PER_DEG
                    de = (p.lon_deg - prev[1]) * M_PER_DEG * math.cos(math.radians(p.lat_deg))
                    if math.hypot(dn, de) > self.jump_m and e.alive:
                        self.add("pos_jump", f"{e.id} frame {fr}: {math.hypot(dn, de):.0f} m")
                self.pos[e.id] = (p.lat_deg, p.lon_deg, p.alt_m)
                self.vel[e.id] = (v.x, v.y, v.z)
                self.alive[e.id] = e.alive
                if self.keep_traj:
                    self.traj[e.id].append((fr, p.lat_deg, p.lon_deg, p.alt_m))

    def _status(self, s) -> None:
        sim, *_ = self.m
        st = sim.SimStatus.FromString(s.payload)
        with self.lock:
            if self.status is not None and st.frame_overruns < self.status.frame_overruns:
                if time.monotonic() >= self.expect_reset_until:
                    self.add("overrun_regress", f"{self.status.frame_overruns}→{st.frame_overruns}")
            self.status = st
            self.status_hist.append((time.monotonic(), st.state, st.frame, st.frame_overruns, st.rate_actual))

    def _tick(self, s) -> None:
        sim, *_ = self.m
        t = sim.ClockTick.FromString(s.payload)
        with self.lock:
            self.ticks += 1
            if self.last_tick and t.frame < self.last_tick[0] and time.monotonic() >= self.expect_reset_until:
                self.add("tick_regress", f"tick frame {self.last_tick[0]}→{t.frame}")
            self.last_tick = (t.frame, t.sim_time_us)

    def _outcome(self, s) -> None:
        sim, truth, link, *_ = self.m
        o = link.LinkOutcome.FromString(s.payload)
        with self.lock:
            kind = link.LinkOutcomeKind.Name(o.outcome).removeprefix("LINK_OUTCOME_KIND_")
            self.outcomes[kind] += 1
            if o.outcome == link.LINK_OUTCOME_KIND_DROPPED:
                self.drop_reasons[link.DropReason.Name(o.reason).removeprefix("DROP_REASON_")] += 1
            elif o.rx_time_us >= o.tx_time_us:
                self.latency_us.append(o.rx_time_us - o.tx_time_us)
            else:
                self.add("link_time", f"{o.src}→{o.dst} rx<{o.tx_time_us}")
            key = (o.src, o.dst, o.msg_type)
            prev = self.link_seq.get(key)
            if prev is not None and o.seq < prev:
                self.reorder += 1
            self.link_seq[key] = o.seq

    def _param(self, s) -> None:
        sim, *_ = self.m
        ep = sim.EntityParams.FromString(s.payload)
        with self.lock:
            self.params[f"{ep.entity_id}/{sim.ParamOwner.Name(ep.owner).removeprefix('PARAM_OWNER_').lower()}"] = ep
            self.seq += 1
            self.param_log.append(ep)

    def _event(self, s) -> None:
        with self.lock:
            self.events.append((s.key, s.payload))

    def _rx(self, s) -> None:
        sim, truth, link, c2, common = self.m
        try:
            env = link.LinkEnvelope.FromString(s.payload)
            if env.msg_type != "swarm.v1.TaskStatus":
                return
            st = c2.TaskStatus.FromString(env.payload)
        except Exception as e:  # noqa: BLE001
            with self.lock:
                self.add("decode", f"gcs rx 해석 실패: {e}")
            return
        with self.lock:
            self.taskstatus[env.header.source].append(
                f"{st.task_id}:{common.CommandState.Name(st.state).removeprefix('COMMAND_STATE_')}"
                + (f"({st.reason})" if st.reason else ""))

    # 질의 ---------------------------------------------------------------
    def wait(self, cond, timeout: float = 20.0, step: float = 0.2) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            time.sleep(step)
        return False

    def wait_frames(self, n: int, timeout: float = 60.0) -> bool:
        with self.lock:
            f0 = self.last_frame or 0
        return self.wait(lambda: (self.last_frame or 0) >= f0 + n, timeout)

    def wait_state(self, state, timeout: float = 20.0) -> bool:
        return self.wait(lambda: self.status is not None and self.status.state == state, timeout)

    def sim_s(self) -> float:
        return (self.last_t_us or 0) * 1e-6

    def stalled(self, secs: float = 4.0) -> bool:
        return time.monotonic() - self.last_wall > secs

    def snapshot(self) -> dict:
        with self.lock:
            st = self.status
            return {
                "frames": self.frames, "last_frame": self.last_frame, "sim_s": round(self.sim_s(), 2),
                "entities": (self.entity_n[-1] if self.entity_n else 0),
                "entity_min_max": (min(self.entity_n), max(self.entity_n)) if self.entity_n else (0, 0),
                "gap_frames": self.gap_frames, "dup": self.counts["dup_frame"],
                "state": (st.state if st else None), "overruns": (st.frame_overruns if st else None),
                "rate_actual": (round(st.rate_actual, 2) if st else None),
                "status_entities": (st.entity_count if st else None),
                "outcomes": dict(self.outcomes), "drops": dict(self.drop_reasons), "reorder": self.reorder,
                "findings": [str(f) for f in self.findings[:20]],
            }

    # 송신 ---------------------------------------------------------------
    def put_sim(self, build) -> None:
        sim, *_ = self.m
        cmd = sim.SimCommand(issuer="qa")
        build(cmd)
        self.bus.put("sim/ctrl/cmd", cmd.SerializeToString(), CT + "SimCommand")

    def start(self, mode: str, rate: float = 1.0, hz: int = 50, seed: int = 1) -> None:
        sim, *_ = self.m
        mm = {"realtime": sim.RUN_MODE_REALTIME, "lockstep": sim.RUN_MODE_LOCKSTEP, "freerun": sim.RUN_MODE_FREERUN}
        def b(c):
            c.start.mode, c.start.rate, c.start.frame_hz, c.start.seed = mm[mode], rate, hz, seed
        self.put_sim(b)

    def pause(self) -> None:
        self.put_sim(lambda c: c.pause.SetInParent())

    def resume(self) -> None:
        self.put_sim(lambda c: c.resume.SetInParent())

    def reset(self) -> None:
        self.reset_expected()
        self.put_sim(lambda c: c.reset.SetInParent())

    def step(self, n: int) -> None:
        self.put_sim(lambda c: setattr(c.step, "frames", n))

    def set_rate(self, r: float) -> None:
        self.put_sim(lambda c: setattr(c.set_rate, "rate", r))

    def load_scenario(self, pbfile: Path) -> None:
        sim, *_ = self.m
        sc = sim.Scenario.FromString(pbfile.read_bytes())
        self.reset_expected(8.0)
        self.put_sim(lambda c: c.load.scenario.CopyFrom(sc))

    def fault(self, entity: str, kind: str, duration: float = 0.0, clear: bool = False) -> None:
        sim, *_ = self.m
        def b(c):
            c.fault.entity_id = entity
            c.fault.fault = getattr(sim, f"FAULT_KIND_{kind}")
            c.fault.duration_s = duration
            c.fault.clear = clear
        self.put_sim(b)

    def set_params(self, entity: str, owner: str, values: dict) -> None:
        sim, *_ = self.m
        owners = {"fa": sim.PARAM_OWNER_FA, "ma": sim.PARAM_OWNER_MA, "dynamics": sim.PARAM_OWNER_DYNAMICS}
        def b(c):
            c.set_params.entity_id = entity
            c.set_params.owner = owners[owner]
            c.set_params.values.update(values)
        self.put_sim(b)

    def jam_zone(self, owner: str, lat: float, lon: float, radius_m: float, active: bool, alt=(0.0, 5000.0)) -> None:
        sim, truth, link, c2, common = self.m
        ev = truth.TruthEvent()
        ev.header.source = owner
        ev.jam_zone.owner = owner
        ev.jam_zone.active = active
        c = ev.jam_zone.area.circle
        c.center.lat_deg, c.center.lon_deg = lat, lon
        c.radius_m = radius_m
        self.bus.put("truth/event/jam_zone", ev.SerializeToString(), CT + "TruthEvent")

    def task(self, task, targets: list[str], task_id: str) -> None:
        sim, truth, link, c2, common = self.m
        from swarm.v1 import options_pb2
        with self.lock:
            t_us, frame = self.last_t_us or 0, self.last_frame or 0
        self.seq += 1
        hdr = common.Header(sim_time_us=t_us, frame=frame, source=GCS, correlation_id=task_id, seq=self.seq)
        task.header.CopyFrom(hdr)
        task.task_id = task_id
        del task.assignees[:]
        task.assignees.extend(targets)
        env = link.LinkEnvelope(header=hdr, dst=targets, iface=options_pb2.L1_INTERFACE_C2,
                                msg_type="swarm.v1.TaskCommand", payload=task.SerializeToString())
        self.bus.put(f"swarm/{GCS}/tx/c2/TaskCommand", env.SerializeToString(), CT + "LinkEnvelope")

    def move_to(self, targets, lat, lon, alt, task_id) -> None:
        c2 = self.m[3]
        t = c2.TaskCommand()
        t.move_to.destination.lat_deg, t.move_to.destination.lon_deg, t.move_to.destination.alt_m = lat, lon, alt
        self.task(t, targets, task_id)

    def hold(self, targets, lat, lon, alt, radius, task_id, racetrack: tuple[float, float] | None = None) -> None:
        t = self.m[3].TaskCommand()
        h = t.hold
        h.center.lat_deg, h.center.lon_deg, h.center.alt_m = lat, lon, alt
        h.radius_m = radius
        if racetrack:
            h.racetrack.leg_length_m, h.racetrack.axis_heading_deg = racetrack
        self.task(t, targets, task_id)

    def route(self, targets, pts: list[tuple[float, float, float]], task_id: str, recon=False, loop=False) -> None:
        t = self.m[3].TaskCommand()
        for la, lo, al in pts:
            w = t.route.waypoints.add()
            w.position.lat_deg, w.position.lon_deg, w.position.alt_m = la, lo, al
            w.acceptance_radius_m = 150.0
            if recon:
                w.recon.radius_m, w.recon.duration_s = 300.0, 10.0
        t.route.loop = loop
        self.task(t, targets, task_id)

    def close(self) -> None:
        for s in self.subs:
            try:
                s.close()
            except Exception:  # noqa: BLE001
                pass
        self.bus.close()


def off(lat: float, lon: float, n_m: float, e_m: float) -> tuple[float, float]:
    return lat + n_m / M_PER_DEG, lon + e_m / (M_PER_DEG * math.cos(math.radians(lat)))


def dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    dn = (b[0] - a[0]) * M_PER_DEG
    de = (b[1] - a[1]) * M_PER_DEG * math.cos(math.radians(a[0]))
    return math.hypot(dn, de)


class ResourceSampler(threading.Thread):
    """프로세스별 CPU·RSS 표본 (psutil)"""

    def __init__(self, stack: Stack, period: float = 2.0):
        super().__init__(daemon=True)
        self.stack, self.period, self.stop_ev = stack, period, threading.Event()
        self.samples: list[tuple[float, dict[str, tuple[float, float]]]] = []

    def run(self) -> None:
        import psutil
        cache: dict[int, psutil.Process] = {}
        while not self.stop_ev.wait(self.period):
            row = {}
            for n, p in list(self.stack.procs.items()):
                if not p.alive():
                    continue
                try:
                    # venv 런처·uv 래퍼 밑의 자식(실제 python)까지 합산한다
                    root = cache.get(p.p.pid) or psutil.Process(p.p.pid)
                    cache[p.p.pid] = root
                    cpu = mem = 0.0
                    for ps in [root] + root.children(recursive=True):
                        if ps.pid not in cache:
                            cache[ps.pid] = ps
                            ps.cpu_percent(None)
                            continue
                        cpu += cache[ps.pid].cpu_percent(None)
                        mem += ps.memory_info().rss / 1e6
                    row[n] = (cpu, mem)
                except Exception:  # noqa: BLE001
                    pass
            self.samples.append((time.monotonic(), row))

    def stop(self) -> dict:
        self.stop_ev.set()
        self.join(3)
        out = {}
        names = {n for _, r in self.samples for n in r}
        for n in names:
            cpu = [r[n][0] for _, r in self.samples if n in r]
            mem = [r[n][1] for _, r in self.samples if n in r]
            if len(mem) < 4:
                continue
            h = len(mem) // 2
            out[n] = {"cpu_avg": round(sum(cpu) / len(cpu), 1), "cpu_max": round(max(cpu), 1),
                      "rss_start_mb": round(mem[0], 1), "rss_end_mb": round(mem[-1], 1),
                      "rss_growth_2nd_half_mb": round(mem[-1] - mem[h], 1)}
        return out


def scan_logs(stack: Stack) -> list[str]:
    """프로세스 로그에서 예외·경고·치명 오류 줄을 모은다"""
    pats = ("traceback", "exception", "error", "panic", "fatal", "assert", "terminate", "warning", "overrun",
            "nan", "inf ")
    hits = []
    for n, txt in stack.log_text().items():
        for ln in txt.splitlines():
            low = ln.lower()
            if any(p in low for p in pats):
                hits.append(f"{n}: {ln.strip()[:240]}")
    return hits


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

"""Agent 런타임 (IMP-AGT-006, DEC-005, DEC-013, DEC-014).

한 프로세스가 여러 기체를 호스팅한다. 프레임 처리 순서(sim/clock/tick 하나당):
  1. 기체마다 수신 버퍼를 넘기고 ctx(frame, 시각, dt)를 갱신한다
  2. MA: 기체별 on_step(ID 순), 일괄 MA on_step_batch(플러그인 이름 순)
  3. FA: 이번 프레임에 항법 보고를 받은 기체만 step → onboard/<id>/ControlOutput
  4. lockstep이면 sim/clock/done/<participant>에 FrameDone

구독하는 키: sim/clock/tick, sim/ctrl/cmd(런타임만, MA에 노출하지 않음), 기체마다 onboard/<id>/*,
swarm/<id>/rx/**. truth/**와 link/**는 구독하지 않는다 (PRP-SIM-003).
"""

import logging
import queue
import time
import traceback
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np
from google.protobuf import json_format
from google.protobuf.message import Message

from swarm.v1 import entity_pb2, link_pb2, options_pb2, sim_pb2, vi_pb2
from swarm_api import BatchMissionAutonomy, Bus, NavBatch, Sample, keys
from swarm_api.keys import Iface

from .messages import decode, encoding, full_name, short_name
from .plugins import PluginRegistry
from .ports import C2_INBOUND
from .vehicle import Vehicle

log = logging.getLogger("swarm_agent")

L1_ENUM = {
    "c2": options_pb2.L1_INTERFACE_C2,
    "vi": options_pb2.L1_INTERFACE_VI,
    "ms": options_pb2.L1_INTERFACE_MS,
    "mp": options_pb2.L1_INTERFACE_MP,
    "md": options_pb2.L1_INTERFACE_MD,
    "p2p": options_pb2.L1_INTERFACE_P2P,
}
_PRIORITY = {"c2": 0, "p2p": 1}

# onboard/<id>/<msg> 중 런타임이 받는 것. 나머지(자기가 낸 ControlOutput 등)는 무시한다
ONBOARD_INBOUND = frozenset({"NavigationReport", "SystemStatus", "Detection",
                             "SensorActivity", "JammerActivity", "StrikeActivity"})


@dataclass
class RuntimeConfig:
    participant: str = "agent-0"
    entities: set[str] | None = None  # None이면 AutonomySpec이 있는 기체
    strict: bool = False              # 플러그인 예외를 다시 던진다 (시험용)


@dataclass
class RuntimeStats:
    ticks: int = 0
    ma_s: float = 0.0
    fa_s: float = 0.0
    frame_s: list[float] = field(default_factory=list)  # 틱 처리 시간 (최근 것만)


def _struct_dict(s) -> dict:
    return json_format.MessageToDict(s) if s.ListFields() else {}


def vehicle_rng(seed: int, entity_id: str) -> np.random.Generator:
    """시드와 기체 ID로 정해지는 난수 생성기 (lockstep 결정론)"""
    return np.random.default_rng([seed, zlib.crc32(entity_id.encode())])


# threaded 모드에서 틱을 받았는데 같은 프레임의 항법 보고가 덜 왔을 때 기다리는 최대 시간(벽시계)
NAV_WAIT_S = 0.05


class AgentRuntime:
    def __init__(self, bus: Bus, config: RuntimeConfig | None = None, registry: PluginRegistry | None = None,
                 threaded: bool = False) -> None:
        """threaded=True면 콜백은 큐에 넣기만 하고 run()이 처리한다(Zenoh). False면 콜백 안에서 바로 처리한다"""
        self.bus = bus
        self.config = config or RuntimeConfig()
        keys.check_entity_id(self.config.participant)
        self.registry = registry or PluginRegistry()
        self._queue: queue.Queue[Sample] | None = queue.Queue() if threaded else None
        # 항법 보고를 기다리는 틱과 기한 (threaded 모드만)
        self._pending_tick: tuple[sim_pb2.ClockTick, float] | None = None
        self._subs = [bus.subscribe(keys.CLOCK_TICK, self._on_sample),
                      bus.subscribe(keys.SIM_CTRL_CMD, self._on_sample)]
        self._vehicle_subs: list = []
        self.scenario: sim_pb2.Scenario | None = None
        self.vehicles: dict[str, Vehicle] = {}
        self._order: list[Vehicle] = []
        self._batches: dict[str, tuple[BatchMissionAutonomy, list[Vehicle]]] = {}
        self._initialized = False
        self._started = False
        self.seed = 0
        self.mode = sim_pb2.RUN_MODE_UNSPECIFIED
        self.stopped = False
        self.stats = RuntimeStats()
        self._tx_seq: dict[str, int] = {}
        self._warned: set[str] = set()

    # ---- 버스 입력 ----

    def _on_sample(self, s: Sample) -> None:
        if self._queue is not None:
            self._queue.put(s)
        else:
            self.handle(s)

    def handle(self, s: Sample) -> None:
        key = s.key
        if key == keys.CLOCK_TICK:
            self._on_tick(sim_pb2.ClockTick.FromString(s.payload))
        elif key == keys.SIM_CTRL_CMD:
            self._on_command(sim_pb2.SimCommand.FromString(s.payload))
        elif key.startswith("onboard/"):
            self._on_onboard(key, s.payload)
        elif key.startswith("swarm/"):
            self._on_rx(key, s.payload)

    def run(self, max_frames: int = 0, should_stop: Callable[[], bool] | None = None) -> None:
        """threaded 모드 처리 루프. Shutdown, max_frames, should_stop()로 끝난다"""
        assert self._queue is not None, "run() needs threaded=True"
        while not self.stopped and not (should_stop and should_stop()):
            timeout = 0.2
            if self._pending_tick is not None:
                timeout = max(0.0, self._pending_tick[1] - time.monotonic())
            try:
                s = self._queue.get(timeout=timeout)
            except queue.Empty:
                s = None
            if s is not None:
                self.handle(s)
            if self._pending_tick is not None and time.monotonic() >= self._pending_tick[1]:
                self._release_tick()
            if max_frames and self.stats.ticks >= max_frames:
                break

    def close(self) -> None:
        self._teardown()
        for sub in self._subs:
            sub.close()
        self._subs = []

    # ---- sim/ctrl (런타임 전용) ----

    def _on_command(self, cmd: sim_pb2.SimCommand) -> None:
        which = cmd.WhichOneof("cmd")
        if which == "load":
            if cmd.load.HasField("scenario"):
                self.load(cmd.load.scenario)
            elif cmd.load.scenario_json:
                self.warn("LoadScenario.scenario_json is deprecated (DEC-024); ignored")
        elif which == "start":
            if cmd.start.seed and not self._started:
                self._reseed(cmd.start.seed)
            self._started = True
        elif which == "reset":
            if self.scenario is not None:
                self.load(self.scenario)
        elif which == "shutdown":
            self.stopped = True

    def load(self, scenario: sim_pb2.Scenario) -> None:
        self._teardown()
        self.scenario = scenario
        self.seed = scenario.run.seed
        self._started = False
        plan = scenario.mission_plan if scenario.HasField("mission_plan") else None
        criteria = scenario.engagement_criteria if scenario.HasField("engagement_criteria") else None
        for spec in scenario.entities:
            if not self._hosts(spec):
                continue
            v = self._make_vehicle(spec, plan, criteria)
            if v is not None:
                self.vehicles[spec.id] = v
        self._order = [self.vehicles[k] for k in sorted(self.vehicles)]
        for v in self._order:
            self._vehicle_subs.append(self.bus.subscribe(f"onboard/{v.entity_id}/*", self._on_sample))
            self._vehicle_subs.append(self.bus.subscribe(keys.rx_all(v.entity_id), self._on_sample))
        log.info("loaded '%s': hosting %d vehicles", scenario.name, len(self._order))

    def _hosts(self, spec: entity_pb2.EntitySpec) -> bool:
        if self.config.entities is not None:
            return spec.id in self.config.entities
        a = spec.autonomy
        return bool(a.ma_plugin or a.fa_plugin)

    def _make_vehicle(self, spec, plan, criteria) -> Vehicle | None:
        fa_cls = self.registry.fa_class(spec.autonomy.fa_plugin)
        if fa_cls is None:
            self.warn(f"{spec.id}: FA plugin '{spec.autonomy.fa_plugin}' not found, using default")
            fa_cls = self.registry.fa_class("")
        if fa_cls is None:
            self.warn(f"{spec.id}: no FA plugin available; not hosted")
            return None
        fa_params = {"dynamics": entity_pb2.DynamicsKind.Name(spec.dynamics), "airframe": spec.airframe,
                     **_struct_dict(spec.autonomy.fa_params)}
        ma_name = spec.autonomy.ma_plugin or "hold"
        v = Vehicle(self, spec, fa_cls(), fa_params, ma_name, _struct_dict(spec.autonomy.ma_params),
                    vehicle_rng(self.seed, spec.id), plan, criteria)
        ma_cls = self.registry.ma_class(ma_name)
        if ma_cls is None:
            self.warn(f"{spec.id}: MA plugin '{ma_name}' not found; FA holds")
        elif issubclass(ma_cls, BatchMissionAutonomy):
            if ma_name not in self._batches:
                self._batches[ma_name] = (ma_cls(), [])
            self._batches[ma_name][1].append(v)
        else:
            v.ma = ma_cls()
        return v

    def _reseed(self, seed: int) -> None:
        self.seed = seed
        for v in self._order:
            v.ctx.rng = vehicle_rng(seed, v.entity_id)

    def _teardown(self) -> None:
        self._pending_tick = None
        if self._initialized:
            for v in self._order:
                if v.ma is not None:
                    self._guard(v.entity_id, v.ma.on_shutdown, v.ctx)
            for name, (plugin, members) in sorted(self._batches.items()):
                self._guard(name, plugin.on_shutdown, [m.ctx for m in members])
        for sub in self._vehicle_subs:
            sub.close()
        self._vehicle_subs = []
        self.vehicles = {}
        self._order = []
        self._batches = {}
        self._initialized = False

    # ---- onboard / rx ----

    def _on_onboard(self, key: str, payload: bytes) -> None:
        _, eid, name = key.split("/", 2)
        v = self.vehicles.get(eid)
        if v is None or name not in ONBOARD_INBOUND:
            return
        if name == "NavigationReport":
            v.nav = vi_pb2.NavigationReport.FromString(payload)
            v.nav_fresh = True
            if self._pending_tick is not None and self._navs_ready(self._pending_tick[0].frame):
                self._release_tick()
            return
        msg = decode(f"swarm.v1.{name}", payload)
        if name == "SystemStatus":
            v.system_status = msg
        elif name == "Detection":
            v.ports.ms.detection_buffer.push(msg)
        else:
            v.ports.ms.on_activity(msg)

    def _on_rx(self, key: str, payload: bytes) -> None:
        parts = key.split("/")
        if len(parts) < 5 or parts[2] != "rx":
            return
        v = self.vehicles.get(parts[1])
        if v is None:
            return
        env = link_pb2.LinkEnvelope.FromString(payload)
        if env.header.source == v.entity_id:
            return
        msg = decode(env.msg_type, env.payload)
        if msg is None:
            self.warn(f"{v.entity_id}: unknown msg_type '{env.msg_type}' on {key}")
            return
        iface = parts[3]
        if iface == "c2":
            if isinstance(msg, C2_INBOUND):
                v.ports.c2.buffer.push(msg)
            else:
                v.ports.mp.on_message(msg)
        elif iface == "p2p":
            v.ports.p2p.buffer.push(msg)
        elif iface == "mp":
            v.ports.mp.on_message(msg)

    # ---- 프레임 ----

    def _navs_ready(self, frame: int) -> bool:
        """이 프레임의 항법 보고를 받아야 할 기체(아직 보고가 없거나 직전 프레임까지 보고한 기체)가 모두 받았는가"""
        for v in self._order:
            if v.nav is None or v.nav.header.frame == frame - 1:
                return False
        return True

    def _release_tick(self) -> None:
        tick, _ = self._pending_tick
        self._pending_tick = None
        self._process_tick(tick)

    def _on_tick(self, tick: sim_pb2.ClockTick) -> None:
        # Zenoh는 키마다 다른 스레드에서 콜백을 부르므로 NavigationReport(N)가 틱(N)보다 늦게 올 수 있다.
        # threaded 모드에서는 그 기체들의 보고를 NAV_WAIT_S까지 기다린다
        if self._pending_tick is not None:
            self._release_tick()
        if self._queue is not None and self._order and not self._navs_ready(tick.frame):
            self._pending_tick = (tick, time.monotonic() + NAV_WAIT_S)
            return
        self._process_tick(tick)

    def _process_tick(self, tick: sim_pb2.ClockTick) -> None:
        t_start = time.perf_counter()
        self.mode = tick.mode
        if self._order:
            self._step(tick)
        if tick.mode == sim_pb2.RUN_MODE_LOCKSTEP:
            done = sim_pb2.FrameDone(participant=self.config.participant, frame=tick.frame)
            self.bus.put(keys.clock_done(self.config.participant), done.SerializeToString(), encoding(done))
        self.stats.ticks += 1
        fs = self.stats.frame_s
        fs.append(time.perf_counter() - t_start)
        if len(fs) > 10000:
            del fs[:5000]

    def _step(self, tick: sim_pb2.ClockTick) -> None:
        dt = tick.dt_us * 1e-6
        for v in self._order:
            v.begin_frame(tick.frame, tick.sim_time_us, dt)
        if not self._initialized:
            self._initialized = True
            for v in self._order:
                if v.ma is not None:
                    self._guard(v.entity_id, v.ma.on_init, v.ctx)
            for name, (plugin, members) in sorted(self._batches.items()):
                self._guard(name, plugin.on_init, [m.ctx for m in members])

        t0 = time.perf_counter()
        for v in self._order:
            if v.ma is not None:
                self._guard(v.entity_id, v.ma.on_step, v.ctx)
        for name, (plugin, members) in sorted(self._batches.items()):
            self._guard(name, plugin.on_step_batch, [m.ctx for m in members], nav_batch(members))
        t1 = time.perf_counter()

        for v in self._order:
            if v.nav is not None and v.nav_fresh:
                out = self._guard(v.entity_id, v.fa.step, v.nav, dt)
                if out is not None:
                    self.publish_onboard(v, out, stamp=True)
            for st in v.fa.pending_status():
                v.ports.vi.push_status(st)
            v.nav_fresh = False
        t2 = time.perf_counter()
        self.stats.ma_s += t1 - t0
        self.stats.fa_s += t2 - t1

    def _guard(self, who: str, fn, *args):
        try:
            return fn(*args)
        except Exception:
            if self.config.strict:
                raise
            tag = f"{who}:{getattr(fn, '__qualname__', fn)}"
            if tag not in self._warned:
                self._warned.add(tag)
                self.warn(f"plugin error in {tag}\n{traceback.format_exc()}")
            return None

    # ---- 버스 출력 ----

    def publish_onboard(self, v: Vehicle, msg: Message, stamp: bool = False) -> None:
        if stamp:
            v.stamp(msg)
        self.bus.put(keys.onboard(v.entity_id, short_name(msg)), msg.SerializeToString(), encoding(msg))

    def send_link(self, v: Vehicle, iface: str, msg: Message, dst: Iterable[str]) -> None:
        key = keys.tx(v.entity_id, Iface(iface), short_name(msg))
        seq = self._tx_seq.get(key, 0)
        self._tx_seq[key] = seq + 1
        env = link_pb2.LinkEnvelope(dst=list(dst), iface=L1_ENUM[iface], msg_type=full_name(msg),
                                    payload=msg.SerializeToString(), priority=_PRIORITY.get(iface, 1))
        env.header.source = v.entity_id
        env.header.frame = v.frame
        env.header.sim_time_us = v.sim_time_us
        env.header.seq = seq
        self.bus.put(key, env.SerializeToString(), encoding(env))

    def warn(self, text: str) -> None:
        log.warning(text)


def nav_batch(members: list[Vehicle]) -> NavBatch:
    n = len(members)
    lla = np.zeros((n, 3))
    vel = np.zeros((n, 3))
    valid = np.zeros(n, dtype=bool)
    for i, v in enumerate(members):
        if v.nav is None:
            continue
        k = v.nav.kinematics
        lla[i] = (k.position.lat_deg, k.position.lon_deg, k.position.alt_m)
        vel[i] = (k.velocity_ned_mps.x, k.velocity_ned_mps.y, k.velocity_ned_mps.z)
        valid[i] = v.nav_fresh
    return NavBatch(ids=[v.entity_id for v in members], lat_lon_alt=lla, velocity_ned=vel, valid=valid)

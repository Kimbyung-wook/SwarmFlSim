"""Agent 런타임 (IMP-AGT-006, DEC-005, DEC-013, DEC-014).

한 프로세스가 여러 기체를 호스팅한다. 프레임 처리 순서(sim/clock/tick 하나당):
  1. 기체마다 수신 버퍼를 넘기고 ctx(frame, 시각, dt)를 갱신한다
  2. MA: 기체별 on_step(ID 순), 일괄 MA on_step_batch(플러그인 이름 순)
  3. FA: 이번 프레임에 항법 보고를 받은 기체만 step → onboard/<id>/ControlOutput
  4. lockstep이면 sim/clock/done/<participant>에 FrameDone

구독하는 키: sim/clock/tick, sim/ctrl/cmd·sim/ctrl/scenario(런타임만, MA에 노출하지 않음, DEC-037), 기체마다 onboard/<id>/*,
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
from google.protobuf.message import Message

from swarm.v1 import entity_pb2, link_pb2, options_pb2, sim_pb2, vi_pb2
from swarm_api import BatchMissionAutonomy, Bus, NavBatch, Sample, keys
from swarm_api.keys import Iface

from .messages import decode, encoding, full_name, short_name
from .params import OWNER_KEY, ParamSet, param_defs
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


def _py_value(v):
    """Struct Value → Python. MessageToDict는 NaN·inf에서 예외를 내므로 직접 변환한다 (DEC-038)"""
    kind = v.WhichOneof("kind")
    if kind == "number_value":
        n = v.number_value
        return int(n) if n.is_integer() and abs(n) < 2**53 else n
    if kind == "string_value":
        return v.string_value
    if kind == "bool_value":
        return v.bool_value
    if kind == "struct_value":
        return {k: _py_value(x) for k, x in v.struct_value.fields.items()}
    if kind == "list_value":
        return [_py_value(x) for x in v.list_value.values]
    return None


def _struct_dict(s) -> dict:
    return {k: _py_value(x) for k, x in s.fields.items()}


def vehicle_rng(seed: int, entity_id: str) -> np.random.Generator:
    """시드와 기체 ID로 정해지는 난수 생성기 (lockstep 결정론)"""
    return np.random.default_rng([seed, zlib.crc32(entity_id.encode())])


# 적재 상태에서 EntityParams를 다시 발행하는 주기 (벽시계, DEC-035)
PARAM_PUBLISH_S = 1.0

# threaded 모드에서 틱을 받았는데 같은 프레임의 항법 보고가 덜 왔을 때 기다리는 최대 시간(벽시계)
NAV_WAIT_S = 0.05
DATALINK_PREFIX = "datalink"  # run.participants 중 이 접두어로 시작하는 것이 Datalink (DEC-040)


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
        self._nav_timeout = False
        # lockstep 수신 결정성 (DEC-040): Datalink의 FrameDone(f)을 받은 뒤에 틱 f+1을 처리하고,
        # rx는 rx_time_us <= 틱 시각일 때만 소비한다
        self._lockstep = False
        self._dl_names: tuple[str, ...] = ()
        self._dl_done: dict[str, int] = {}          # 참여자 → 처리해도 되는 다음 틱 번호
        self._ticks_seen = 0
        self._prev_tick_us: int | None = None
        self._rx_hold: dict[str, list] = {}         # 기체 → [(rx_time_us, source, seq, iface, msg)]
        self._subs = [bus.subscribe(keys.CLOCK_TICK, self._on_sample),
                      bus.subscribe(keys.SIM_CTRL_CMD, self._on_sample),
                      bus.subscribe(keys.SIM_CTRL_SCENARIO, self._on_sample)]
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
        self._pending_params: list[tuple[str, int, dict]] = []  # (entity, owner, 바꿀 값). 다음 프레임 시작에 적용
        self._param_due = 0.0
        self._sim_time_us = 0

    # ---- 버스 입력 ----

    def _on_sample(self, s: Sample) -> None:
        if self._queue is not None:
            self._queue.put(s)
        else:
            self.handle(s)

    def handle(self, s: Sample) -> None:
        """입력 하나를 처리한다. 어떤 입력도 프로세스를 죽이지 못한다 (DEC-038): 예외는 로그로 남기고 넘어간다"""
        try:
            self._handle(s)
        except Exception:
            if self.config.strict:
                raise
            self.warn(f"input on '{s.key}' dropped\n{traceback.format_exc()}")

    def _handle(self, s: Sample) -> None:
        key = s.key
        if key == keys.CLOCK_TICK:
            self._on_tick(sim_pb2.ClockTick.FromString(s.payload))
        elif key == keys.SIM_CTRL_CMD:
            self._on_command(sim_pb2.SimCommand.FromString(s.payload))
        elif key == keys.SIM_CTRL_SCENARIO:
            self._on_scenario(sim_pb2.Scenario.FromString(s.payload))
        elif key.startswith("sim/clock/done/"):
            self._on_done(sim_pb2.FrameDone.FromString(s.payload))
        elif key.startswith("onboard/"):
            self._on_onboard(key, s.payload)
        elif key.startswith("swarm/"):
            self._on_rx(key, s.payload)

    def run(self, max_frames: int = 0, should_stop: Callable[[], bool] | None = None) -> None:
        """threaded 모드 처리 루프. Shutdown, max_frames, should_stop()로 끝난다"""
        assert self._queue is not None, "run() needs threaded=True"
        while not self.stopped and not (should_stop and should_stop()):
            timeout = 0.2
            if self._pending_tick is not None and not self._nav_timeout:
                timeout = max(0.0, self._pending_tick[1] - time.monotonic())
            try:
                s = self._queue.get(timeout=timeout)
            except queue.Empty:
                s = None
            if s is not None:
                self.handle(s)
            if self._pending_tick is not None and time.monotonic() >= self._pending_tick[1]:
                self._nav_timeout = True
                self._try_release()
            self._publish_params_due()
            if max_frames and self.stats.ticks >= max_frames:
                break

    def close(self) -> None:
        self._teardown()
        for sub in self._subs:
            sub.close()
        self._subs = []

    # ---- sim/ctrl (런타임 전용) ----

    def _on_scenario(self, scenario: sim_pb2.Scenario) -> None:
        """Core가 재발행한 시나리오 (DEC-037). 이미 적재한 것과 name이 같으면 무시, 다르면 다시 적재"""
        if self.scenario is not None and self.scenario.name == scenario.name:
            return
        self.load(scenario)

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
        elif which == "set_params":
            sp = cmd.set_params
            if sp.entity_id in self.vehicles and sp.owner in OWNER_KEY:
                self._pending_params.append((sp.entity_id, sp.owner, _struct_dict(sp.values)))
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
        self._lockstep = scenario.run.mode == sim_pb2.RUN_MODE_LOCKSTEP
        if self._lockstep:
            self._dl_names = tuple(p for p in scenario.run.participants if p.startswith(DATALINK_PREFIX))
        for name in self._dl_names:
            self._vehicle_subs.append(self.bus.subscribe(keys.clock_done(name), self._on_sample))
        log.info("loaded '%s': hosting %d vehicles", scenario.name, len(self._order))
        self._publish_params()
        if scenario.run.mode == sim_pb2.RUN_MODE_LOCKSTEP:  # 준비 신호: Core는 참여자 전원의 frame 0 뒤에 첫 틱을 낸다
            self._send_done(0)

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
        fa_context = {"dynamics": entity_pb2.DynamicsKind.Name(spec.dynamics), "airframe": spec.airframe}
        fa_set = ParamSet.load("fa", spec.autonomy.fa_plugin or "default", param_defs(fa_cls),
                               _struct_dict(spec.autonomy.fa_params))
        ma_name = spec.autonomy.ma_plugin or "hold"
        ma_cls = self.registry.ma_class(ma_name)
        ma_set = ParamSet.load("ma", ma_name, param_defs(ma_cls), _struct_dict(spec.autonomy.ma_params))
        for ps in (fa_set, ma_set):
            for name, reason in ps.rejected.items():
                self.warn(f"{spec.id}: {ps.owner} param '{name}' rejected ({reason})")
        v = Vehicle(self, spec, fa_cls(), fa_set, fa_context, ma_name, ma_set,
                    vehicle_rng(self.seed, spec.id), plan, criteria)
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
        self._nav_timeout = False
        self._lockstep = False
        self._dl_names = ()
        self._dl_done = {}
        self._ticks_seen = 0
        self._prev_tick_us = None
        self._rx_hold = {}
        self._pending_params = []
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
            self._try_release()
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
        if self._lockstep:  # 다음 틱에서 rx_time_us <= 틱 시각인 것만 소비한다 (DEC-040)
            self._rx_hold.setdefault(v.entity_id, []).append(
                (env.rx_time_us, env.header.source, env.header.seq, iface, msg))
            return
        self._deliver(v, iface, msg)

    def _deliver(self, v: Vehicle, iface: str, msg: Message) -> None:
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

    def _dl_ready(self, frame: int) -> bool:
        """틱 frame을 처리하려면 Datalink의 FrameDone(frame-1)이 와 있어야 한다 (DEC-040)"""
        return all(self._dl_done.get(n, 0) >= frame for n in self._dl_names)

    def _on_done(self, d: sim_pb2.FrameDone) -> None:
        if d.participant not in self._dl_names or self._ticks_seen == 0:  # 첫 틱 전의 frame 0은 준비 신호다
            return
        self._dl_done[d.participant] = max(self._dl_done.get(d.participant, 0), d.frame + 1)
        self._try_release()

    def _try_release(self) -> None:
        if self._pending_tick is None:
            return
        frame = self._pending_tick[0].frame
        navs_ok = self._nav_timeout or self._queue is None or not self._order or self._navs_ready(frame)
        if navs_ok and self._dl_ready(frame):
            self._release_tick()

    def _release_tick(self) -> None:
        tick, _ = self._pending_tick
        self._pending_tick = None
        self._nav_timeout = False
        self._process_tick(tick)

    def _release_rx(self, sim_time_us: int | None) -> None:
        if sim_time_us is None:
            return
        for v in self._order:
            held = self._rx_hold.get(v.entity_id)
            if not held:
                continue
            due = sorted((e for e in held if e[0] <= sim_time_us), key=lambda e: e[:3])
            self._rx_hold[v.entity_id] = [e for e in held if e[0] > sim_time_us]
            for _, _, _, iface, msg in due:
                self._deliver(v, iface, msg)

    def _on_tick(self, tick: sim_pb2.ClockTick) -> None:
        # Zenoh는 키마다 다른 스레드에서 콜백을 부르므로 NavigationReport(N)가 틱(N)보다 늦게 올 수 있다.
        # threaded 모드에서는 그 기체들의 보고를 NAV_WAIT_S까지 기다린다
        if self._pending_tick is not None:
            self._release_tick()
        self._ticks_seen += 1
        navs_wait = self._queue is not None and self._order and not self._navs_ready(tick.frame)
        if navs_wait or (self._lockstep and not self._dl_ready(tick.frame)):
            self._pending_tick = (tick, time.monotonic() + NAV_WAIT_S)
            self._nav_timeout = False
            return
        self._process_tick(tick)

    def _send_done(self, frame: int) -> None:
        done = sim_pb2.FrameDone(participant=self.config.participant, frame=frame)
        self.bus.put(keys.clock_done(self.config.participant), done.SerializeToString(), encoding(done))

    def _process_tick(self, tick: sim_pb2.ClockTick) -> None:
        t_start = time.perf_counter()
        self.mode = tick.mode
        self._sim_time_us = tick.sim_time_us
        self._apply_params()
        self._publish_params_due()
        if self._order:
            self._step(tick)
        if tick.mode == sim_pb2.RUN_MODE_LOCKSTEP:
            self._send_done(tick.frame)
        self.stats.ticks += 1
        fs = self.stats.frame_s
        fs.append(time.perf_counter() - t_start)
        if len(fs) > 10000:
            del fs[:5000]

    def _step(self, tick: sim_pb2.ClockTick) -> None:
        dt = tick.dt_us * 1e-6
        if self._lockstep:
            # 이번 틱의 rx는 Datalink가 지금 내고 있을 수 있다. FrameDone이 보장된 이전 틱 시각까지만 소비한다
            self._release_rx(self._prev_tick_us)
            self._prev_tick_us = tick.sim_time_us
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

    # ---- 매개변수 (DEC-035) ----

    def _apply_params(self) -> None:
        """대기 중인 SetParams를 프레임 시작에 적용하고 알린다. 적용·거부 결과는 바로 발행한다"""
        pending, self._pending_params = self._pending_params, []
        for eid, owner, values in pending:
            v = self.vehicles.get(eid)
            if v is None:
                continue
            ps = v.fa_set if OWNER_KEY[owner] == "fa" else v.ma_set
            changed = ps.change(values)
            for name, reason in ps.rejected.items():
                self.warn(f"{eid}: {ps.owner} param '{name}' rejected ({reason})")
            if changed:
                if ps is v.fa_set:
                    self._guard(eid, v.fa.on_params, ps.values, changed)
                else:
                    v.ctx.params = ps.values
                    if self._initialized:  # on_init 전이면 on_init이 새 값을 읽는다
                        if v.ma is not None:
                            self._guard(eid, v.ma.on_params, v.ctx, changed)
                        elif v.ma_name in self._batches:
                            self._guard(eid, self._batches[v.ma_name][0].on_params, v.ctx, changed)
            self._publish_params(v, ps)

    def _publish_params(self, only: Vehicle | None = None, ps: ParamSet | None = None) -> None:
        targets = [only] if only is not None else self._order
        for v in targets:
            for s in ([ps] if ps is not None else [v.fa_set, v.ma_set]):
                msg = s.to_message(v.entity_id, self._sim_time_us)
                self.bus.put(keys.sim_param(v.entity_id, s.owner), msg.SerializeToString(), encoding(msg))
        self._param_due = time.monotonic() + PARAM_PUBLISH_S

    def _publish_params_due(self) -> None:
        if self._order and time.monotonic() >= self._param_due:
            self._publish_params()

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

"""시험용 가짜 Core·Datalink와 시나리오 생성기 (IMP-AGT-009).

InMemoryBus 위에서 Agent 런타임을 단독으로 시험한다. 실제 swarm_core·swarm_datalink를 대신한다.
- FakeCore: 2-DoF 운동학(속도 1차 지연, 선회율, 상승률)으로 적분하고 truth/state, NavigationReport, ClockTick 발행
- FakeDatalink: swarm/*/tx/** → swarm/<dst>/rx/** 즉시 전달. dst가 비면 송신자를 뺀 모든 엔티티
"""

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

from google.protobuf import struct_pb2

from swarm.v1 import c2_pb2, entity_pb2, fa_pb2, link_pb2, mp_pb2, sim_pb2, truth_pb2, vi_pb2
from swarm_api import InMemoryBus, Sample, keys, protobuf_encoding

from .geo import ned_offset, offset_geo
from .messages import decode
from .plugins import PluginRegistry
from .runtime import AgentRuntime, RuntimeConfig


_matches = lru_cache(maxsize=65536)(keys.keyexpr_matches)


class FastInMemoryBus(InMemoryBus):
    """InMemoryBus와 같고 키 일치 판정만 캐시한다 (시험 속도)"""

    def put(self, key: str, payload: bytes, encoding: str) -> None:
        if "*" in key:
            raise ValueError(f"wildcard in put key: {key!r}")
        sample = Sample(key, payload, encoding)
        for sub in list(self._subs):
            if _matches(sub.keyexpr, key):
                sub.callback(sample)

@dataclass
class _Body:
    id: str
    lat: float
    lon: float
    alt: float
    course: float
    speed: float
    climb: float = 0.0
    rate: float = 0.0


class FakeCore:
    def __init__(self, bus: InMemoryBus, scenario: sim_pb2.Scenario, frame_hz: int = 50,
                 mode: int = sim_pb2.RUN_MODE_LOCKSTEP, accel_mps2: float = 3.0) -> None:
        self.bus = bus
        self.dt_us = 1_000_000 // frame_hz
        self.mode = mode
        self.accel = accel_mps2
        self.frame = 0
        self.bodies: dict[str, _Body] = {}
        for e in scenario.entities:
            if e.dynamics not in (entity_pb2.DYNAMICS_KIND_DOF2, entity_pb2.DYNAMICS_KIND_DOF3):
                continue
            k = e.initial
            vn, ve = k.velocity_ned_mps.x, k.velocity_ned_mps.y
            self.bodies[e.id] = _Body(e.id, k.position.lat_deg, k.position.lon_deg, k.position.alt_m,
                                      math.atan2(ve, vn), math.hypot(vn, ve))
        self.controls: dict[str, fa_pb2.ControlOutput] = {}
        self.done: dict[str, int] = {}
        self.control_frames: dict[str, int] = {}
        self._subs = [bus.subscribe("onboard/*/ControlOutput", self._on_control),
                      bus.subscribe("sim/clock/done/*", self._on_done)]

    def _on_control(self, s: Sample) -> None:
        eid = s.key.split("/")[1]
        c = fa_pb2.ControlOutput.FromString(s.payload)
        self.controls[eid] = c
        self.control_frames[eid] = c.header.frame

    def _on_done(self, s: Sample) -> None:
        d = sim_pb2.FrameDone.FromString(s.payload)
        self.done[d.participant] = d.frame

    def _put(self, key: str, msg) -> None:
        self.bus.put(key, msg.SerializeToString(), protobuf_encoding(msg.DESCRIPTOR.full_name))

    def kinematics(self, b: _Body) -> entity_pb2.KinematicState:
        k = entity_pb2.KinematicState()
        k.position.lat_deg, k.position.lon_deg, k.position.alt_m = b.lat, b.lon, b.alt
        k.velocity_ned_mps.x = b.speed * math.cos(b.course)
        k.velocity_ned_mps.y = b.speed * math.sin(b.course)
        k.velocity_ned_mps.z = -b.climb
        return k

    def publish_frame(self) -> None:
        t_us = self.frame * self.dt_us
        tf = truth_pb2.TruthFrame()
        tf.header.frame, tf.header.sim_time_us = self.frame, t_us
        for b in self.bodies.values():
            st = tf.entities.add(id=b.id, alive=True)
            st.kinematics.CopyFrom(self.kinematics(b))
        self._put(keys.TRUTH_STATE, tf)
        for b in self.bodies.values():
            nav = vi_pb2.NavigationReport()
            nav.header.frame, nav.header.sim_time_us, nav.header.source = self.frame, t_us, b.id
            nav.kinematics.CopyFrom(self.kinematics(b))
            self._put(keys.onboard(b.id, "NavigationReport"), nav)
        self._put(keys.CLOCK_TICK, sim_pb2.ClockTick(frame=self.frame, sim_time_us=t_us, dt_us=self.dt_us,
                                                     mode=self.mode))

    def integrate(self) -> None:
        dt = self.dt_us * 1e-6
        for b in self.bodies.values():
            c = self.controls.get(b.id)
            if c is not None and c.WhichOneof("cmd") == "kinematic":
                k = c.kinematic
                dv = max(-self.accel * dt, min(self.accel * dt, k.speed_mps - b.speed))
                b.speed += dv
                b.rate = k.heading_rate_rps
                b.climb = k.climb_rate_mps
            b.course += b.rate * dt
            n, e = b.speed * math.cos(b.course) * dt, b.speed * math.sin(b.course) * dt
            b.lat, b.lon = (float(x) for x in offset_geo(b.lat, b.lon, n, e))
            b.alt += b.climb * dt

    def step(self, frames: int = 1) -> None:
        for _ in range(frames):
            self.publish_frame()
            self.integrate()
            self.frame += 1

    def offset_m(self, a: str, b: str) -> tuple[float, float, float]:
        """a 기준 b의 북·동·위 오프셋"""
        pa, pb = self.bodies[a], self.bodies[b]
        n, e = ned_offset(pa.lat, pa.lon, pb.lat, pb.lon)
        return float(n), float(e), pb.alt - pa.alt

    def close(self) -> None:
        for s in self._subs:
            s.close()


class FakeDatalink:
    """drop(iface, src, dst)이 True면 그 전달을 버린다"""

    def __init__(self, bus: InMemoryBus, entity_ids: Iterable[str],
                 drop: Callable[[str, str, str], bool] | None = None) -> None:
        self.bus = bus
        self.ids = sorted(entity_ids)
        self.drop = drop
        self.delivered = 0
        self.dropped = 0
        self._sub = bus.subscribe(keys.TX_ALL, self._on_tx)

    def _on_tx(self, s: Sample) -> None:
        env = link_pb2.LinkEnvelope.FromString(s.payload)
        parts = s.key.split("/")
        src, iface, msg = parts[1], parts[3], parts[4]
        dsts = list(env.dst) or [i for i in self.ids if i != src]
        env.rx_time_us = env.header.sim_time_us
        data = env.SerializeToString()
        for d in dsts:
            if self.drop is not None and self.drop(iface, src, d):
                self.dropped += 1
                continue
            self.bus.put(keys.rx(d, keys.Iface(iface), msg), data, s.encoding)
            self.delivered += 1

    def heartbeat(self, gcs: str, dst: Sequence[str], rx_time_us: int = 0, sequence: int = 0) -> None:
        """Datalink가 발생시킨 GcsHeartbeat를 swarm/<uav>/rx/c2로 바로 낸다. tx를 거치지 않는다 (DEC-078)"""
        hb = c2_pb2.GcsHeartbeat(sequence=sequence)
        hb.header.source = gcs
        env = link_pb2.LinkEnvelope(dst=list(dst), iface=1, msg_type=hb.DESCRIPTOR.full_name,
                                    payload=hb.SerializeToString(), rx_time_us=rx_time_us)
        env.header.source = gcs
        for d in dst:
            self.bus.put(keys.rx(d, keys.Iface.C2, "GcsHeartbeat"), env.SerializeToString(),
                         protobuf_encoding(env.DESCRIPTOR.full_name))

    def close(self) -> None:
        self._sub.close()


def send_c2(bus: InMemoryBus, gcs: str, msg, dst: Sequence[str] = ()) -> None:
    """GCS가 C2 메시지를 tx에 싣는다 (FakeDatalink가 rx로 전달)"""
    msg.header.source = msg.header.source or gcs
    env = link_pb2.LinkEnvelope(dst=list(dst), iface=1, msg_type=msg.DESCRIPTOR.full_name,
                                payload=msg.SerializeToString())
    env.header.source = gcs
    bus.put(keys.tx(gcs, keys.Iface.C2, msg.DESCRIPTOR.name), env.SerializeToString(),
            protobuf_encoding(env.DESCRIPTOR.full_name))


def make_scenario(n: int, ma_plugin: str = "hold", ma_params: dict | None = None, *,
                  origin: tuple[float, float, float] = (37.5, 128.0, 1500.0), spacing_m: float = 200.0,
                  speed_mps: float = 22.0, course_deg: float = 45.0, seed: int = 7,
                  mission_plan: mp_pb2.MissionPlan | None = None,
                  dynamics: int = entity_pb2.DYNAMICS_KIND_DOF2) -> sim_pb2.Scenario:
    """기체 n대(격자 배치) + GCS 1"""
    sc = sim_pb2.Scenario(schema_version="0.1", name=f"test-{n}")
    sc.run.mode, sc.run.frame_hz, sc.run.seed = sim_pb2.RUN_MODE_LOCKSTEP, 50, seed
    sc.run.participants.append("agent-0")
    gcs = sc.entities.add(id="gcs-01", kind=entity_pb2.ENTITY_KIND_GCS, dynamics=entity_pb2.DYNAMICS_KIND_STATIC)
    gcs.initial.position.lat_deg, gcs.initial.position.lon_deg = origin[0], origin[1]
    cols = max(1, math.ceil(math.sqrt(n)))
    c = math.radians(course_deg)
    for i in range(n):
        e = sc.entities.add(id=f"uav-{i + 1:03d}", kind=entity_pb2.ENTITY_KIND_UAV, side=entity_pb2.SIDE_BLUE,
                            dynamics=dynamics, controlling_gcs="gcs-01")
        lat, lon = offset_geo(origin[0], origin[1], (i // cols) * spacing_m, (i % cols) * spacing_m)
        e.initial.position.lat_deg, e.initial.position.lon_deg = float(lat), float(lon)
        e.initial.position.alt_m = origin[2]
        e.initial.velocity_ned_mps.x = speed_mps * math.cos(c)
        e.initial.velocity_ned_mps.y = speed_mps * math.sin(c)
        e.autonomy.ma_plugin = ma_plugin
        if ma_params:
            s = struct_pb2.Struct()
            s.update(ma_params)
            e.autonomy.ma_params.CopyFrom(s)
    if mission_plan is not None:
        sc.mission_plan.CopyFrom(mission_plan)
    return sc


def load_command(sc: sim_pb2.Scenario) -> sim_pb2.SimCommand:
    cmd = sim_pb2.SimCommand(issuer="test")
    cmd.load.scenario.CopyFrom(sc)
    return cmd


def put_sim_command(bus: InMemoryBus, cmd: sim_pb2.SimCommand) -> None:
    bus.put(keys.SIM_CTRL_CMD, cmd.SerializeToString(), protobuf_encoding(cmd.DESCRIPTOR.full_name))


class Harness:
    """FastInMemoryBus + FakeCore + FakeDatalink + AgentRuntime(strict). GCS gcs-01이 받은 메시지를 모은다"""

    def __init__(self, sc: sim_pb2.Scenario, *, registry: PluginRegistry | None = None,
                 drop: Callable[[str, str, str], bool] | None = None, participant: str = "agent-0",
                 entities: set[str] | None = None, mode: int = sim_pb2.RUN_MODE_LOCKSTEP, load: bool = True) -> None:
        self.bus = FastInMemoryBus()
        self.scenario = sc
        self.core = FakeCore(self.bus, sc, frame_hz=sc.run.frame_hz or 50, mode=mode)
        self.datalink = FakeDatalink(self.bus, [e.id for e in sc.entities], drop)
        self.gcs_rx: list = []
        self.bus.subscribe(keys.rx_all("gcs-01"), self._on_gcs)
        self.rt = AgentRuntime(self.bus, RuntimeConfig(participant=participant, entities=entities, strict=True),
                               registry)
        if load:
            put_sim_command(self.bus, load_command(sc))

    def _on_gcs(self, s: Sample) -> None:
        env = link_pb2.LinkEnvelope.FromString(s.payload)
        self.gcs_rx.append(decode(env.msg_type, env.payload))

    def run_s(self, seconds: float) -> None:
        self.core.step(round(seconds * 1e6 / self.core.dt_us))

    def task_states(self, task_id: str) -> list[int]:
        return [m.state for m in self.gcs_rx if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == task_id]


__all__ = ["Harness", "FastInMemoryBus", "FakeCore", "FakeDatalink", "make_scenario", "load_command", "put_sim_command", "send_c2"]

"""TC-AGT-118~125: 항법·제어 일괄 메시지 (IMP-AGT-040, DEC-081, DEC-013, REQ-PRF-002)"""

import random
import time

from swarm.v1 import fa_pb2, sim_pb2, vi_pb2
from swarm_agent import AgentRuntime, RuntimeConfig
from swarm_agent.fa import DefaultFlightAutonomy
from swarm_agent.plugins import PluginRegistry
from swarm_agent.testing import FastInMemoryBus, Harness, load_command, make_scenario, put_sim_command
from swarm_api import keys
from swarm_api.keys import MA_FORBIDDEN_PREFIXES, keyexpr_matches

A, B, C = "uav-001", "uav-002", "uav-003"


def collect(h):
    """버스에 나간 ControlBatch와 (키, 메시지) 순서를 모은다"""
    got, order = [], []

    def on_batch(s):
        got.append((s.key, fa_pb2.ControlBatch.FromString(s.payload)))
        order.append("ctrl")

    h.bus.subscribe(keys.CONTROL_BATCH_ALL, on_batch)
    h.bus.subscribe("sim/clock/done/*", lambda s: order.append("done"))
    return got, order


def nav_batch(sc, frame, ids=None):
    batch = vi_pb2.NavigationBatch()
    batch.header.frame = frame
    for e in sc.entities[1:]:
        if ids is None or e.id in ids:
            nav = batch.reports.add()
            nav.header.frame, nav.header.source = frame, e.id
            nav.kinematics.CopyFrom(e.initial)
    return batch


def tick(bus, f):
    t = sim_pb2.ClockTick(frame=f, sim_time_us=f * 20000, dt_us=20000, mode=sim_pb2.RUN_MODE_LOCKSTEP)
    bus.put(keys.CLOCK_TICK, t.SerializeToString(), "")


def test_tc_agt_118_only_vehicles_in_batch_are_fresh():
    """배치에서 빠진 기체는 FA를 돌리지 않고 틱을 막지도 않는다. MA의 항법은 마지막 값으로 남는다"""
    h = Harness(make_scenario(3, "hold"))
    got, order = collect(h)
    h.core.step(1)
    assert [c.header.source for c in got[-1][1].controls] == [A, B, C]
    h.core.nav_outage = {B}
    h.core.step(1)
    assert [c.header.source for c in got[-1][1].controls] == [A, C]
    assert order == ["ctrl", "done", "ctrl", "done"]
    assert not any(v.nav_fresh for v in h.rt.vehicles.values())
    assert h.rt.vehicles[B].ctx.ports.vi.nav().header.frame == 0
    assert h.rt.vehicles[A].ctx.ports.vi.nav().header.frame == 1
    h.core.nav_outage = set()
    h.core.step(1)
    assert [c.header.source for c in got[-1][1].controls] == [A, B, C]
    # 틱 없이 지나간 배치에 있던 기체도 다음 배치에서 빠지면 fresh가 아니다
    h.bus.put(keys.NAVIGATION_BATCH, nav_batch(h.scenario, 10, {A, B}).SerializeToString(), "")
    h.bus.put(keys.NAVIGATION_BATCH, nav_batch(h.scenario, 11, {A}).SerializeToString(), "")
    assert h.rt.vehicles[A].nav_fresh and not h.rt.vehicles[B].nav_fresh


def test_tc_agt_119_one_control_batch_per_tick_before_frame_done():
    h = Harness(make_scenario(3, "hold"), participant="agent-7")
    got, order = collect(h)
    h.core.step(3)
    assert order == ["ctrl", "done"] * 3
    assert {k for k, _ in got} == {keys.control_batch("agent-7")}
    for f, (_, b) in enumerate(got):
        assert (b.header.source, b.header.frame, b.header.sim_time_us, b.header.seq) == ("agent-7", f, f * 20000, f)
        assert [c.header.source for c in b.controls] == [A, B, C]
        assert all(c.header.frame == f and c.header.sim_time_us == f * 20000 for c in b.controls)
        assert all(c.WhichOneof("cmd") == "kinematic" for c in b.controls)
    # 이번 프레임 항법이 하나도 없어도 틱당 1건이다
    h.core.nav_outage = {A, B, C}
    h.core.step(1)
    assert len(got) == 4 and not got[-1][1].controls and got[-1][1].header.frame == 3 and order[-2:] == ["ctrl", "done"]
    put_sim_command(h.bus, sim_pb2.SimCommand(issuer="t", reset=sim_pb2.Reset()))
    h.core.step(1)
    assert got[-1][1].header.seq == 0              # 일련번호는 실행마다 처음부터 (결정성)


def test_tc_agt_120_no_echo_subscription():
    """런타임 구독은 받을 메시지뿐이다. 자기 제어·명령과 예전 기체별 항법은 받지 않는다"""
    h = Harness(make_scenario(2, "hold"))
    exprs = [s.keyexpr for s in h.rt._vehicle_subs]
    want = {keys.NAVIGATION_BATCH}
    for eid in (A, B):
        want |= {keys.rx_all(eid)} | {keys.onboard(eid, n) for n in
                                      ("SystemStatus", "Detection", "SensorActivity", "JammerActivity", "StrikeActivity")}
    assert set(exprs) == want and len(exprs) == len(want)
    for key in (keys.onboard(A, "ControlOutput"), keys.onboard(A, "NavigationReport"), keys.onboard(A, "SensorCommand"),
                keys.onboard(A, "FlightCommand"), keys.control_batch("agent-0")):
        assert not any(keyexpr_matches(e, key) for e in exprs), key
    nav = vi_pb2.NavigationReport()
    nav.header.source = A
    h.bus.put(keys.onboard(A, "NavigationReport"), nav.SerializeToString(), "")
    assert not h.rt.vehicles[A].nav_fresh and h.rt.vehicles[A].nav is None


def test_tc_agt_121_multi_participant_handles_own_vehicles_only():
    sc = make_scenario(3, "hold")
    h = Harness(sc, participant="agent-0", entities={A, C}, load=False)
    other = AgentRuntime(h.bus, RuntimeConfig(participant="agent-1", entities={B}, strict=True))
    put_sim_command(h.bus, load_command(sc))
    got, _ = collect(h)
    h.core.step(2)
    per_key = {}
    for k, b in got:
        per_key.setdefault(k, []).append([c.header.source for c in b.controls])
    assert per_key == {keys.control_batch("agent-0"): [[A, C], [A, C]], keys.control_batch("agent-1"): [[B], [B]]}
    assert sorted(h.rt.vehicles) == [A, C] and sorted(other.vehicles) == [B]
    assert all(e in h.core.controls for e in (A, B, C))
    # 다른 참여자의 기체만 담긴 배치도 이 참여자의 틱을 푼다
    h.core.nav_outage = {A, C}
    h.core.step(1)
    last = {k: [c.header.source for c in b.controls] for k, b in got[-2:]}    # 구독 호출 순서는 정해져 있지 않다
    assert last == {keys.control_batch("agent-0"): [], keys.control_batch("agent-1"): [B]}


def test_tc_agt_122_threaded_gate_is_batch_receipt():
    sc = make_scenario(2, "hold")
    bus = FastInMemoryBus()
    rt = AgentRuntime(bus, RuntimeConfig(), threaded=True)
    rt.load(sc)
    ctrl, done = [], []
    bus.subscribe(keys.CONTROL_BATCH_ALL, lambda s: ctrl.append(fa_pb2.ControlBatch.FromString(s.payload)))
    bus.subscribe(keys.clock_done("agent-0"), lambda s: done.append(time.monotonic()))
    # 틱이 먼저 와도, 한 기체가 빠진 배치여도 배치를 받으면 기한 없이 바로 처리한다
    tick(bus, 0)
    bus.put(keys.NAVIGATION_BATCH, nav_batch(sc, 0, {A}).SerializeToString(), "")
    t0 = time.monotonic()
    rt.run(max_frames=1)
    assert len(done) == 1 and done[0] - t0 < 0.04
    assert [c.header.source for c in ctrl[0].controls] == [A]
    # Reset 뒤에는 이전 실행의 배치 프레임으로 틱을 풀지 않는다
    for f in range(1, 4):
        tick(bus, f)
        bus.put(keys.NAVIGATION_BATCH, nav_batch(sc, f).SerializeToString(), "")
    rt.run(max_frames=4)
    put_sim_command(bus, sim_pb2.SimCommand(issuer="t", reset=sim_pb2.Reset()))
    tick(bus, 0)
    t0 = time.monotonic()
    rt.run(max_frames=rt.stats.ticks + 1)
    assert done[-1] - t0 >= 0.04 and not ctrl[-1].controls


def test_tc_agt_123_ma_cannot_reach_batch():
    """DEC-013: 전체 기체 항법은 MA에 보이지 않고, ports.vi.nav()는 자기 항법만 돌려준다"""
    assert "onboard_batch/" in MA_FORBIDDEN_PREFIXES
    assert keys.NAVIGATION_BATCH.startswith(MA_FORBIDDEN_PREFIXES) and keys.control_batch("a").startswith(MA_FORBIDDEN_PREFIXES)
    h = Harness(make_scenario(3, "hold"))
    h.core.step(2)
    for eid in (A, B, C):
        ports = h.rt.vehicles[eid].ctx.ports
        nav = ports.vi.nav()
        assert nav.DESCRIPTOR.name == "NavigationReport" and nav.header.source == eid and nav.header.frame == 1
        assert not any(hasattr(ports, a) for a in ("bus", "_rt", "runtime"))
        assert not any(hasattr(ports.vi, a) for a in ("nav_batch", "batch", "_rt"))


class BadSource(DefaultFlightAutonomy):
    """header.source를 틀리게 채우는 플러그인"""

    def step(self, nav, dt_s):
        out = super().step(nav, dt_s)
        if out is not None:
            out.header.source = "someone-else"
        return out


class NoOutput(DefaultFlightAutonomy):
    def step(self, nav, dt_s):
        return None


class Raises(DefaultFlightAutonomy):
    def step(self, nav, dt_s):
        raise RuntimeError("step")


def _plugin_scenario():
    sc = make_scenario(3, "hold")
    for e, name in zip(sc.entities[1:], ("bad", "none", "raises")):
        e.autonomy.fa_plugin = name
    return sc


def test_tc_agt_124_python_fa_same_path_and_source_is_vehicle():
    reg = PluginRegistry(extra_fa={"bad": BadSource, "none": NoOutput, "raises": Raises})
    h = Harness(_plugin_scenario(), registry=reg)
    h.rt.config.strict = False
    got, order = collect(h)
    h.core.step(2)
    assert order == ["ctrl", "done"] * 2           # 없는 출력·예외는 그 기체만 빠지고 나머지는 나간다
    assert [[c.header.source for c in b.controls] for _, b in got] == [[A], [A]]
    assert A in h.core.controls and "someone-else" not in h.core.controls


def test_tc_agt_125_report_order_in_batch_does_not_change_output():
    """배치 안 순서와 무관하게 ID 순으로 처리해 바이트가 같다"""
    def run(shuffle_seed):
        sc = make_scenario(6, "flocking", {"wander_deg": 3.0}, seed=11)
        h = Harness(sc)
        out = []
        h.bus.subscribe(keys.CONTROL_BATCH_ALL, lambda s: out.append(s.payload))
        if shuffle_seed is not None:
            rnd = random.Random(shuffle_seed)
            real = h.core._put

            def put(key, msg):
                if key == keys.NAVIGATION_BATCH:
                    reports = list(msg.reports)
                    rnd.shuffle(reports)
                    copy = vi_pb2.NavigationBatch()
                    copy.header.CopyFrom(msg.header)
                    copy.reports.extend(reports)
                    msg = copy
                real(key, msg)

            h.core._put = put
        h.core.step(100)
        return out

    a = run(None)
    assert len(a) == 100 and run(1) == a and run(2) == a

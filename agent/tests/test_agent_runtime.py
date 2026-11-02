"""TC-AGT-006~012: Agent 런타임 (IMP-AGT-003~006, IMP-AGT-008)"""

import threading
import time
from pathlib import Path

import pytest
from google.protobuf import json_format

from swarm.v1 import c2_pb2, fa_pb2, link_pb2, mp_pb2, options_pb2, p2p_pb2, sim_pb2, vi_pb2
from swarm_api import BatchMissionAutonomy, BusConfig, MissionAutonomy, keys, open_bus, protobuf_encoding, zenoh_available
from swarm_api.keys import MA_FORBIDDEN_PREFIXES, keyexpr_matches
from swarm_agent import AgentRuntime, PluginRegistry, RuntimeConfig
from swarm_agent.cli import parse_args, read_scenario
from swarm_agent.testing import FastInMemoryBus, Harness, load_command, make_scenario, put_sim_command, send_c2

ROOT = Path(__file__).resolve().parents[2]


class Spy(MissionAutonomy):
    """받은 모든 것을 기록하고, 프레임마다 C2·P2P를 한 번씩 보낸다"""

    instances: list["Spy"] = []

    def on_init(self, ctx):
        self.seen = []
        self.inits = 1
        Spy.instances.append(self)

    def on_step(self, ctx):
        p = ctx.ports
        self.seen.extend(("c2", m) for m in p.c2.inbox())
        self.seen.extend(("p2p", m) for m in p.p2p.inbox())
        self.seen.extend(("ms", m) for m in p.ms.detections())
        self.seen.extend(("ms", m) for m in p.ms.activities())
        if ctx.params.get("talk"):
            p.c2.send(c2_pb2.TaskStatus(task_id="t", state=3))
            p.p2p.send(p2p_pb2.PeerStatus(group_id="g"))


class Boom(MissionAutonomy):
    def on_step(self, ctx):
        raise RuntimeError("boom")


class BatchSpy(BatchMissionAutonomy):
    calls: list = []

    def on_step_batch(self, ctxs, nav):
        BatchSpy.calls.append((tuple(c.entity_id for c in ctxs), nav.valid.copy(), nav.lat_lon_alt.copy()))


def registry():
    return PluginRegistry(extra_ma={"spy": Spy, "boom": Boom, "batchspy": BatchSpy})


@pytest.fixture(autouse=True)
def _reset():
    Spy.instances.clear()
    BatchSpy.calls.clear()


def test_tc_agt_006_hosting_and_plugin_loading():
    sc = make_scenario(3, "hold")
    sc.entities[3].autonomy.Clear()  # uav-003: AutonomySpec 없음 (entities[0]은 GCS)
    h = Harness(sc)
    assert sorted(h.rt.vehicles) == ["uav-001", "uav-002"]
    v = h.rt.vehicles["uav-001"]
    assert type(v.ma).__name__ == "Hold"  # entry point swarm.ma "hold"
    assert type(v.fa).__name__ == "DefaultFlightAutonomy"  # entry point swarm.fa "default"
    # --entities로 지정하면 AutonomySpec이 없어도 맡는다
    h2 = Harness(sc, entities={"uav-003"})
    assert sorted(h2.rt.vehicles) == ["uav-003"]
    assert type(h2.rt.vehicles["uav-003"].ma).__name__ == "Hold"
    # 일괄 MA는 같은 플러그인 이름끼리 한 인스턴스
    h3 = Harness(make_scenario(4, "flocking"))
    assert list(h3.rt._batches) == ["flocking"]
    assert len(h3.rt._batches["flocking"][1]) == 4
    assert all(v.ma is None for v in h3.rt.vehicles.values())


def test_tc_agt_006_controls_and_batch_nav():
    h = Harness(make_scenario(3, "batchspy"), registry=registry())
    h.run_s(0.1)
    assert set(h.core.controls) == {"uav-001", "uav-002", "uav-003"}
    assert all(f == h.core.frame - 1 for f in h.core.control_frames.values())
    ids, valid, lla = BatchSpy.calls[-1]
    assert ids == ("uav-001", "uav-002", "uav-003") and valid.all()
    assert lla[0, 0] == pytest.approx(h.core.bodies["uav-001"].lat, abs=1e-3)


def test_tc_agt_007_lockstep_frame_done():
    h = Harness(make_scenario(2, "hold"))
    dones = []
    h.bus.subscribe("sim/clock/done/*", lambda s: dones.append((s.key, sim_pb2.FrameDone.FromString(s.payload))))
    h.core.step(5)
    assert [d.frame for _, d in dones] == [0, 1, 2, 3, 4]
    assert all(k == "sim/clock/done/agent-0" and d.participant == "agent-0" for k, d in dones)
    # ControlOutput은 같은 프레임의 FrameDone보다 먼저 나간다
    order = []
    h.bus.subscribe("onboard/*/ControlOutput", lambda s: order.append("ctrl"))
    h.bus.subscribe("sim/clock/done/*", lambda s: order.append("done"))
    h.core.step(1)
    assert order == ["ctrl", "ctrl", "done"]


def test_tc_agt_007_frame_done_without_vehicles_and_not_in_realtime():
    bus = FastInMemoryBus()
    AgentRuntime(bus, RuntimeConfig(participant="agent-host-2"))
    dones = []
    bus.subscribe("sim/clock/done/*", lambda s: dones.append(s.key))
    tick = sim_pb2.ClockTick(frame=3, dt_us=20000, mode=sim_pb2.RUN_MODE_LOCKSTEP)
    bus.put(keys.CLOCK_TICK, tick.SerializeToString(), "")
    tick.mode = sim_pb2.RUN_MODE_REALTIME
    bus.put(keys.CLOCK_TICK, tick.SerializeToString(), "")
    assert dones == ["sim/clock/done/agent-host-2"]


def test_tc_agt_007_threaded_waits_for_late_nav():
    """threaded 모드: 틱(N)이 항법 보고(N)보다 먼저 와도 그 보고를 기다려 모든 기체가 ControlOutput을 낸다"""
    bus = FastInMemoryBus()
    sc = make_scenario(2, "hold")
    rt = AgentRuntime(bus, RuntimeConfig(), threaded=True)
    rt.load(sc)
    ctrl, done = [], []
    bus.subscribe("onboard/*/ControlOutput", lambda s: ctrl.append(fa_pb2.ControlOutput.FromString(s.payload)))
    bus.subscribe(keys.clock_done("agent-0"), lambda s: done.append(time.monotonic()))
    for f in range(3):
        tick = sim_pb2.ClockTick(frame=f, sim_time_us=f * 20000, dt_us=20000, mode=sim_pb2.RUN_MODE_LOCKSTEP)
        bus.put(keys.CLOCK_TICK, tick.SerializeToString(), "")
        for e in sc.entities[1:]:
            nav = vi_pb2.NavigationReport()
            nav.header.frame = f
            nav.kinematics.CopyFrom(e.initial)
            bus.put(keys.onboard(e.id, "NavigationReport"), nav.SerializeToString(), "")
    t0 = time.monotonic()
    rt.run(max_frames=3)
    assert [c.header.frame for c in ctrl] == [0, 0, 1, 1, 2, 2]
    # 보고가 모두 오면 기한을 기다리지 않는다
    assert len(done) == 3 and done[-1] - t0 < 0.04
    # 보고가 끝내 오지 않으면 기한 뒤에 처리한다
    tick = sim_pb2.ClockTick(frame=3, sim_time_us=60000, dt_us=20000, mode=sim_pb2.RUN_MODE_LOCKSTEP)
    bus.put(keys.CLOCK_TICK, tick.SerializeToString(), "")
    t0 = time.monotonic()
    rt.run(max_frames=4)
    assert len(done) == 4 and done[-1] - t0 >= 0.04 and len(ctrl) == 6


def test_tc_agt_008_no_truth_no_ctrl_exposure():
    sc = make_scenario(3, "spy", {"talk": True})
    h = Harness(sc, registry=registry())
    handled = []
    orig = h.rt.handle
    h.rt.handle = lambda s: (handled.append(s.key), orig(s))
    h.run_s(1.0)
    subs = [s.keyexpr for s in h.bus._subs if getattr(s.callback, "__self__", None) is h.rt]
    assert subs, "runtime subscriptions"
    for expr in subs:
        for p in ("truth/state", "truth/event/kill", "link/outcome/uav-001/uav-002", "link/state/uav-001/uav-002"):
            assert not keyexpr_matches(expr, p), (expr, p)
    assert not any(k.startswith(("truth/", "link/")) for k in handled)
    # 플러그인 쪽: sim/ctrl 메시지가 어떤 포트로도 들어오지 않는다
    put_sim_command(h.bus, sim_pb2.SimCommand(issuer="x", pause=sim_pb2.Pause()))
    h.run_s(0.1)
    for spy in Spy.instances:
        assert all(m.DESCRIPTOR.full_name.split(".")[-1] not in ("SimCommand", "TruthFrame") for _, m in spy.seen)
    ports = h.rt.vehicles["uav-001"].ctx.ports
    assert not any(hasattr(ports, a) for a in ("bus", "_rt", "runtime"))
    assert MA_FORBIDDEN_PREFIXES == ("sim/ctrl/", "truth/", "link/")


def test_tc_agt_009_link_envelope_tx():
    h = Harness(make_scenario(2, "spy", {"talk": True}), registry=registry())
    tx = []
    h.bus.subscribe(keys.TX_ALL, lambda s: tx.append(s))
    h.core.step(2)
    by_key = {}
    for s in tx:
        by_key.setdefault(s.key, []).append(link_pb2.LinkEnvelope.FromString(s.payload))
    c2 = by_key["swarm/uav-001/tx/c2/TaskStatus"]
    assert [e.header.seq for e in c2] == [0, 1]
    e = c2[0]
    assert list(e.dst) == ["gcs-01"] and e.iface == options_pb2.L1_INTERFACE_C2
    assert e.msg_type == "swarm.v1.TaskStatus" and e.header.source == "uav-001" and e.header.frame == 0
    inner = c2_pb2.TaskStatus.FromString(e.payload)
    assert inner.header.source == "uav-001" and inner.task_id == "t"
    p2p = by_key["swarm/uav-002/tx/p2p/PeerStatus"][1]
    assert list(p2p.dst) == [] and p2p.iface == options_pb2.L1_INTERFACE_P2P and p2p.header.frame == 1
    assert all(s.encoding == protobuf_encoding("swarm.v1.LinkEnvelope") for s in tx)


def test_tc_agt_009_link_envelope_rx():
    h = Harness(make_scenario(2, "spy", {"talk": True}), registry=registry())
    task = c2_pb2.TaskCommand(task_id="t9", assignees=["uav-002"])
    task.hold.SetInParent()
    send_c2(h.bus, "gcs-01", task, ["uav-002"])
    # 모르는 메시지, 자기 자신이 보낸 메시지는 버린다
    bad = link_pb2.LinkEnvelope(msg_type="swarm.v1.TruthFrame", payload=b"")
    bad.header.source = "gcs-01"
    h.bus.put(keys.rx("uav-002", keys.Iface.C2, "TruthFrame"), bad.SerializeToString(), "")
    echo = link_pb2.LinkEnvelope(msg_type="swarm.v1.PeerStatus", payload=p2p_pb2.PeerStatus().SerializeToString())
    echo.header.source = "uav-002"
    h.bus.put(keys.rx("uav-002", keys.Iface.P2P, "PeerStatus"), echo.SerializeToString(), "")
    h.core.step(3)
    spy2 = next(s for s in Spy.instances if s.seen and any(m.DESCRIPTOR.name == "TaskCommand" for _, m in s.seen))
    kinds = [(port, m.DESCRIPTOR.name) for port, m in spy2.seen]
    assert ("c2", "TaskCommand") in kinds
    assert ("p2p", "PeerStatus") in kinds  # uav-001이 보낸 것 (FakeDatalink 경유)
    assert all(m.header.source != "uav-002" for port, m in spy2.seen if port == "p2p")
    assert not any(n == "TruthFrame" for _, n in kinds)
    # GCS에는 TaskStatus가 도착한다
    assert any(m.DESCRIPTOR.name == "TaskStatus" for m in h.gcs_rx)


def test_tc_agt_009_onboard_ms_and_mp_ports():
    plan = mp_pb2.MissionPlan(plan_id="p")
    plan.tasks.add(task_id="mine", assignees=["uav-001"]).hold.SetInParent()
    plan.tasks.add(task_id="other", assignees=["uav-002"]).hold.SetInParent()
    plan.formations.add(group_id="g", members=["uav-002"])
    sc = make_scenario(2, "spy", mission_plan=plan)
    sc.entities[1].payloads.add(id="sta1", type="agm_short", count=2)
    h = Harness(sc, registry=registry())
    v = h.rt.vehicles["uav-001"]
    mp = v.ports.mp.mission_plan()
    assert [t.task_id for t in mp.tasks] == ["mine"] and len(mp.formations) == 0
    from swarm.v1 import ms_pb2
    det = ms_pb2.Detection(payload_id="cam0", target_id="tgt-001")
    h.bus.put(keys.onboard("uav-001", "Detection"), det.SerializeToString(), "")
    act = ms_pb2.StrikeActivity(payload_id="sta1", state=ms_pb2.STRIKE_STATE_LAUNCHED)
    h.bus.put(keys.onboard("uav-001", "StrikeActivity"), act.SerializeToString(), "")
    h.core.step(1)
    seen = [m.DESCRIPTOR.name for s in Spy.instances for _, m in s.seen]
    assert "Detection" in seen and "StrikeActivity" in seen
    assert v.ports.ms.loadout().stores[0].count == 1
    # ms.command는 onboard/<id>/<msg>로 나간다
    got = []
    h.bus.subscribe("onboard/uav-001/SensorCommand", lambda s: got.append(s))
    v.ports.ms.command(ms_pb2.SensorCommand(payload_id="cam0", enable=True))
    assert len(got) == 1
    with pytest.raises(TypeError):
        v.ports.ms.command(c2_pb2.TaskStatus())
    # MP는 데이터링크로도 갱신된다
    rp = mp_pb2.RoutePlan(route_id="r1", entity_id="uav-001")
    env = link_pb2.LinkEnvelope(msg_type="swarm.v1.RoutePlan", payload=rp.SerializeToString())
    env.header.source = "gcs-01"
    h.bus.put(keys.rx("uav-001", keys.Iface.MP, "RoutePlan"), env.SerializeToString(), "")
    assert [r.route_id for r in v.ports.mp.route_plans()] == ["r1"]
    v.ports.md.record("x", 1.0)
    assert v.ports.md.records[-1][1:] == ("x", 1.0)


def _run_trace(seed: int, frames: int = 300) -> list[bytes]:
    sc = make_scenario(6, "flocking", {"wander_deg": 3.0}, seed=seed)
    h = Harness(sc)
    out = []
    h.bus.subscribe("onboard/*/ControlOutput", lambda s: out.append(s.payload))
    h.core.step(frames)
    return out


def test_tc_agt_010_determinism():
    a, b = _run_trace(11), _run_trace(11)
    assert a == b and len(a) == 6 * 300
    assert _run_trace(12) != a
    # Start.seed가 시나리오 시드를 덮어쓴다
    sc = make_scenario(6, "flocking", {"wander_deg": 3.0}, seed=99)
    h = Harness(sc)
    start = sim_pb2.SimCommand(issuer="t")
    start.start.seed = 11
    put_sim_command(h.bus, start)
    out = []
    h.bus.subscribe("onboard/*/ControlOutput", lambda s: out.append(s.payload))
    h.core.step(300)
    assert out == a


def test_tc_agt_011_errors_reset_shutdown():
    sc = make_scenario(2, "boom")
    h = Harness(sc, registry=registry())
    h.rt.config.strict = False
    h.core.step(3)  # 예외는 기록하고 계속한다. FA는 계속 출력한다
    assert len(h.core.controls) == 2
    put_sim_command(h.bus, sim_pb2.SimCommand(issuer="t", reset=sim_pb2.Reset()))
    assert sorted(h.rt.vehicles) == ["uav-001", "uav-002"]
    put_sim_command(h.bus, sim_pb2.SimCommand(issuer="t", shutdown=sim_pb2.Shutdown()))
    assert h.rt.stopped


def test_tc_agt_012_cli_and_scenario_files(tmp_path):
    a = parse_args(["--participant", "agent-host-1", "--entities", "uav-001,uav-002", "--entities", "uav-003",
                    "--bus", "memory", "--connect", "tcp/127.0.0.1:7447", "--no-multicast", "--zenoh-mode", "client"])
    assert a.participant == "agent-host-1" and a.connect == ["tcp/127.0.0.1:7447"] and a.no_multicast
    from swarm_agent.cli import bus_config
    cfg = bus_config(a)
    assert cfg.backend == "memory" and not cfg.multicast_scouting and cfg.zenoh_mode == "client"
    sc = make_scenario(2, "hold")
    (tmp_path / "s.pb").write_bytes(sc.SerializeToString())
    (tmp_path / "s.json").write_text(json_format.MessageToJson(sc), encoding="utf-8")
    assert read_scenario(str(tmp_path / "s.pb")) == sc
    assert read_scenario(str(tmp_path / "s.json")) == sc
    # 시나리오 JSON(swarm_scenario): 예제 20대를 flocking_basic으로 모두 맡는다
    ex = read_scenario(str(ROOT / "scenario/examples/korea_east_strike_20.json"))
    bus = FastInMemoryBus()
    rt = AgentRuntime(bus, RuntimeConfig())
    rt.load(ex)
    assert len(rt.vehicles) == 20 and list(rt._batches) == ["flocking_basic"]
    rt.close()


def test_tc_agt_012_cli_list_plugins():
    from swarm_agent import cli
    assert cli.main(["--list-plugins"]) == 0


@pytest.mark.skipif(not zenoh_available(), reason="eclipse-zenoh not installed")
def test_tc_agt_013_zenoh_threaded():
    bus = open_bus(BusConfig(backend="zenoh", multicast_scouting=False))
    try:
        rt = AgentRuntime(bus, RuntimeConfig(participant="agent-zt"), threaded=True)
        sc = make_scenario(2, "hold")
        got_ctrl, got_done = [], []
        bus.subscribe("onboard/*/ControlOutput", lambda s: got_ctrl.append(s.key))
        bus.subscribe("sim/clock/done/agent-zt", lambda s: got_done.append(sim_pb2.FrameDone.FromString(s.payload)))
        stop = threading.Event()
        th = threading.Thread(target=rt.run, kwargs={"should_stop": stop.is_set}, daemon=True)
        th.start()
        cmd = load_command(sc)
        bus.put(keys.SIM_CTRL_CMD, cmd.SerializeToString(), protobuf_encoding("swarm.v1.SimCommand"))
        deadline = time.time() + 5
        # 기체별 onboard·rx 구독 선언까지 끝나야 첫 항법 보고를 받는다
        while len(rt._vehicle_subs) < 4 and time.time() < deadline:
            time.sleep(0.01)
        for f in range(5):
            for e in sc.entities[1:]:
                nav = vi_pb2.NavigationReport()
                nav.header.frame = f
                nav.kinematics.CopyFrom(e.initial)
                bus.put(keys.onboard(e.id, "NavigationReport"), nav.SerializeToString(), "")
            tick = sim_pb2.ClockTick(frame=f, sim_time_us=f * 20000, dt_us=20000, mode=sim_pb2.RUN_MODE_LOCKSTEP)
            bus.put(keys.CLOCK_TICK, tick.SerializeToString(), "")
            t0 = time.time()
            while len(got_done) <= f and time.time() - t0 < 5:
                time.sleep(0.005)
        # 키가 다른 발행은 수신 순서가 보장되지 않으므로 ControlOutput 도착을 잠시 기다린다
        t0 = time.time()
        while len(got_ctrl) < 10 and time.time() - t0 < 2:
            time.sleep(0.005)
        stop.set()
        th.join(2)
        assert [d.frame for d in got_done] == [0, 1, 2, 3, 4]
        assert len(got_ctrl) == 10
        rt.close()
    finally:
        bus.close()

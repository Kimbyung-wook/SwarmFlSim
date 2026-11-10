"""TC-AGT-094: GcsHeartbeat의 MA C2 포트 전달 (IMP-AGT-037, DEC-078, DEC-040)"""

from swarm.v1 import sim_pb2
from swarm_agent.plugins import PluginRegistry
from swarm_agent.testing import Harness, make_scenario
from swarm_api import MissionAutonomy

UAV = "uav-001"


class Probe(MissionAutonomy):
    log: list = []

    def on_step(self, ctx):
        Probe.log.extend((ctx.frame, m.DESCRIPTOR.name, m.sequence) for m in ctx.ports.c2.inbox())


def probe_harness(mode=sim_pb2.RUN_MODE_LOCKSTEP):
    Probe.log = []
    sc = make_scenario(1, "probe")
    sc.run.mode = mode
    return Harness(sc, registry=PluginRegistry(extra_ma={"probe": Probe}), mode=mode)


def test_tc_agt_094_heartbeat_reaches_c2_port_by_rx_time():
    h = probe_harness()
    h.core.step(5)
    h.datalink.heartbeat("gcs-01", [UAV], rx_time_us=h.core.frame * h.core.dt_us, sequence=7)
    h.core.step(1)                  # 틱 5: 이전 틱 시각까지만 소비하므로 아직 안 보인다 (DEC-040)
    assert Probe.log == []
    h.core.step(1)
    assert Probe.log == [(6, "GcsHeartbeat", 7)]
    assert h.gcs_rx == [m for m in h.gcs_rx if m.DESCRIPTOR.name != "TaskStatus"]
    assert list(h.rt.vehicles[UAV].ports.mp.route_plans()) == []

"""TC-AGT-126~127: threaded 런타임 구독의 순서 보장 (IMP-AGT-041, DEC-083, D-33, DEC-005, DEC-039)"""

import time

import pytest

from swarm.v1 import sim_pb2
from swarm_agent import AgentRuntime, RuntimeConfig
from swarm_agent.testing import FastInMemoryBus, make_scenario
from swarm_api import BusConfig, keys, open_bus, zenoh_available


class SpyBus(FastInMemoryBus):
    def __init__(self) -> None:
        super().__init__()
        self.opened: list[tuple[str, bool]] = []

    def subscribe(self, keyexpr, callback, *, ordered=False):
        self.opened.append((keyexpr, ordered))
        return super().subscribe(keyexpr, callback, ordered=ordered)


def _lockstep_with_datalink(n=2):
    sc = make_scenario(n, "hold")
    sc.run.participants.append("datalink-0")
    return sc


def test_tc_agt_126_threaded_opens_every_subscription_ordered():
    bus = SpyBus()
    rt = AgentRuntime(bus, RuntimeConfig(), threaded=True)
    rt.load(_lockstep_with_datalink())
    exprs = {e for e, _ in bus.opened}
    assert {keys.CLOCK_TICK, keys.SIM_CTRL_CMD, keys.SIM_CTRL_SCENARIO, keys.NAVIGATION_BATCH,
            "onboard/*/SystemStatus", "swarm/*/rx/**", keys.clock_done("datalink-0")} <= exprs
    assert len(bus.opened) == 3 + 1 + 7 + 1 and all(o for _, o in bus.opened)
    # 콜백은 큐에 넣기만 한다: 수신 스레드에서 처리·발행하지 않는다
    done = []
    bus.subscribe("sim/clock/done/*", lambda s: done.append(s))
    tick = sim_pb2.ClockTick(frame=0, dt_us=20000, mode=sim_pb2.RUN_MODE_LOCKSTEP)
    bus.put(keys.CLOCK_TICK, tick.SerializeToString(), "")
    bus.put(keys.onboard("uav-001", "SystemStatus"), b"", "")
    assert done == [] and rt._queue.qsize() == 2 and rt.stats.ticks == 0
    rt.close()
    # threaded가 아니면 콜백이 바로 처리·발행하므로 ordered로 열지 않는다
    plain = SpyBus()
    AgentRuntime(plain, RuntimeConfig()).load(_lockstep_with_datalink())
    assert plain.opened and not any(o for _, o in plain.opened)


@pytest.mark.skipif(not zenoh_available(), reason="eclipse-zenoh not installed")
def test_tc_agt_127_zenoh_queue_keeps_core_publish_order():
    """D-33: Core 순서(임무장비 출력 → NavigationBatch → SystemStatus → 틱)가 키가 달라도 큐에 그대로 들어온다"""
    core = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", listen=["tcp/127.0.0.1:17481"], multicast_scouting=False))
    agent = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", connect=["tcp/127.0.0.1:17481"], multicast_scouting=False))
    try:
        rt = AgentRuntime(agent, RuntimeConfig(participant="agent-ord"), threaded=True)
        rt.load(make_scenario(3, "hold"))
        ids = ["uav-001", "uav-002", "uav-003"]

        def frame_keys():
            out = [keys.onboard(e, n) for e in ids for n in ("Detection", "SensorActivity")]
            return out + [keys.NAVIGATION_BATCH] + [keys.onboard(e, "SystemStatus") for e in ids] + [keys.CLOCK_TICK]

        # 구독 선언이 모두 전파될 때까지 키마다 한 번씩 받는다
        want, seen = set(frame_keys()), set()
        deadline = time.monotonic() + 5
        while seen != want and time.monotonic() < deadline:
            for k in want - seen:
                core.put(k, b"warm", "")
            time.sleep(0.05)
            while not rt._queue.empty():
                seen.add(rt._queue.get().key)
        assert seen == want
        time.sleep(0.2)
        while not rt._queue.empty():
            rt._queue.get()
        sent = []
        for f in range(80):
            for k in frame_keys():
                payload = f.to_bytes(4, "big")
                core.put(k, payload, "")
                sent.append((k, payload))
        got = []
        deadline = time.monotonic() + 10
        while len(got) < len(sent) and time.monotonic() < deadline:
            try:
                s = rt._queue.get(timeout=0.5)
            except Exception:
                continue
            got.append((s.key, s.payload))
        assert got == sent
        rt.close()
    finally:
        agent.close()
        core.close()

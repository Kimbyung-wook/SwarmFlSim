"""TC-GW-035~039: QA 29차 결함 D-35(알려지지 않은 기체), D-36(UCI 시각 = 모의 시각), D-39(external_c2 선언)"""
import datetime as dt

import pytest
import yaml
from swarm.v1 import entity_pb2

import samples as S
from conftest import CONFIG_DIR
from swarm_gateway.__main__ import _utc, build_parser
from swarm_gateway.converters.base import SimClock
from swarm_gateway.gateway import Gateway, GatewayConfig
from swarm_gateway.lacal import uci_timestamp
from test_import import _task_command
from test_inbound_plans import capture, external, mission_data, route_data

UTC = dt.timezone.utc


def _iter_timestamps(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and (k.lower().endswith("timestamp") or k == "DateTime"):
                yield f"{path}/{k}", v
            else:
                yield from _iter_timestamps(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_timestamps(v, f"{path}[{i}]")


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


# ---------------------------------------------------------------- TC-GW-035 (D-35)
UNKNOWN = "uav-999"


@pytest.mark.parametrize("name,make", [
    ("MA_TaskCommand", lambda gw: _task_command(gw, assignees=(UNKNOWN,))),
    ("MA_TaskCommand", lambda gw: _task_command(gw, assignees=(S.UAV, UNKNOWN))),   # 하나라도 모르면 전체 거부
    ("MA_RoutePlan", lambda gw: gw.envelope("MA_RoutePlan", route_data(target=UNKNOWN))),
])
def test_unknown_entity_is_rejected_and_not_published(gateway, bus, name, make):
    """시나리오·수신 보고에 없는 기체를 가리키는 외부 명령은 버스에 내지 않고 거부로 기록한다"""
    got = capture(bus)
    out = gateway.handle_external(name, make(gateway))
    assert out.status == "rejected" and UNKNOWN in out.reason and "unknown entity" in out.reason
    assert got == [] and gateway.rejections[-1] is out
    assert gateway.counters["ext_rejected"] == 1 and gateway.counters["ext_published"] == 0


def test_unknown_entity_in_mission_plan(gateway, bus):
    external(gateway, "MA_RoutePlan", route_data())
    got = capture(bus)
    out = external(gateway, "MA_MissionPlan", mission_data(target=UNKNOWN))
    assert out.status == "rejected" and UNKNOWN in out.reason and got == []


def test_known_from_scenario_or_reports_only(bus, codec):
    """알려진 기체 = 시나리오의 UAV + 이 GCS rx로 보고를 보낸 엔티티. 시나리오가 바뀌면 새로 시작한다"""
    gw = Gateway(bus, GatewayConfig(S.GCS), codec=codec, sink=lambda t, o: None)
    gw.start()
    try:
        cmd = lambda *a: gw.handle_external("MA_TaskCommand", _task_command(gw, assignees=a))  # noqa: E731
        assert cmd(S.UAV).status == "rejected"                     # 시나리오도 보고도 없다
        S.deliver(bus, S.nav())                                     # uav-001이 보고를 보냈다
        assert cmd(S.UAV).status == "published"
        assert cmd("uav-002").status == "rejected"
        S.load_scenario(bus, "uav-002", others=(("tgt-001", entity_pb2.ENTITY_KIND_GROUND_TARGET),))
        assert gw.entities.snapshot() == {"scenario": ["uav-002"], "reported": []}   # 새 시나리오: 보고 목록 비움
        assert cmd("uav-002").status == "published"
        assert cmd(S.UAV).status == "rejected"
        assert cmd("tgt-001").status == "rejected"                 # UAV가 아닌 엔티티는 명령 대상이 아니다
        assert cmd(S.GCS).status == "rejected"
        bus.put("sim/ctrl/scenario", b"\xff\xff", "application/protobuf;swarm.v1.Scenario")
        assert gw.counters["bad_scenario"] == 1 and gw.entities.known("uav-002")   # 못 읽으면 그대로
    finally:
        gw.close()


def test_rejection_is_notified_as_task_status(gateway, bus, sent):
    """거부한 작업 명령은 외부에 MA_TaskStatus(DROPPED)로 알린다 (버스에는 아무것도 나가지 않는다)"""
    got = capture(bus)
    gateway.handle_external("MA_TaskCommand", _task_command(gateway, assignees=(UNKNOWN,)))
    assert got == []
    (topic, obj), = sent
    assert topic == "swarm.c2" and next(iter(obj)) == "MA_TaskStatus"
    data = obj["MA_TaskStatus"]["MessageData"]
    assert data["ExecutionState"] == "DROPPED"
    assert data["ExecutingSystemOrPackage"]["SystemID"]["DescriptiveLabel"] == UNKNOWN
    assert UNKNOWN in data["ExecutionStateReason"]["Description"]
    gateway.to_xml(obj)                                              # 공개 XSD 통과
    assert gateway.counters["ext_rejected_notified"] == 1


async def test_unknown_entity_roundtrip_negative(cal_server, bus, codec):  # noqa: F811
    """실제 CAL Server: uav-999 명령은 tx로 나가지 않고 외부는 MA_TaskStatus(DROPPED)를 받는다"""
    from swarm_gateway.lacal import LaCalClient
    from swarm_gateway.runner import start_gateway
    from test_roundtrip import _wait

    url = f"ws://127.0.0.1:{cal_server.port}"
    running = await start_gateway(bus, GatewayConfig(S.GCS), url, codec=codec, admin_url=None)
    gw = running.gateway
    S.load_scenario(bus)
    ext = LaCalClient(url, "external_c2")
    await ext.connect()
    got, tx = [], []
    bus.subscribe("swarm/gcs-01/tx/**", tx.append)
    try:
        await ext.subscribe("MA_TaskStatus", "swarm.c2", lambda n, o: got.append(o))
        await ext.publish("swarm.c2", _task_command(gw, assignees=(UNKNOWN,)))
        await _wait(lambda: len(got) == 1)
        assert got[0]["MA_TaskStatus"]["MessageData"]["ExecutionState"] == "DROPPED"
        assert tx == [] and gw.counters["ext_rejected"] == 1
    finally:
        await ext.close()
        await running.stop()


from test_roundtrip import cal_server  # noqa: E402,F401  (fixture)


# ---------------------------------------------------------------- TC-GW-036~037 (D-36)
class FakeWall:
    def __init__(self):
        self.t = dt.datetime(2026, 11, 18, 3, 0, 0, tzinfo=UTC)

    def __call__(self):
        return self.t


def test_uci_time_follows_sim_time_across_pause_and_rate(bus, codec):
    """(Timestamp − 모의 시각)이 일시정지(벽시계만 감)·배속(모의 시각이 빨리 감)에도 일정하다"""
    wall = FakeWall()
    sent = []
    gw = Gateway(bus, GatewayConfig(S.GCS), codec=codec, sink=lambda t, o: sent.append(o))
    gw.clock.wall = wall
    gw.start()
    offsets = set()
    try:
        for sim_s, wall_s in ((1, 0), (2, 1), (3, 40), (13, 41), (14, 300)):   # 40 s 정지, 10배속, 다시 정지
            wall.t = dt.datetime(2026, 11, 18, 3, 0, 0, tzinfo=UTC) + dt.timedelta(seconds=wall_s)
            m = S.nav()
            m.header.sim_time_us = sim_s * 1_000_000
            n = len(sent)
            S.deliver(bus, m)
            assert len(sent) == n + 2                                       # NavigationReport + PositionReport
            for obj in sent[n:]:
                stamps = list(_iter_timestamps(obj))
                assert len(stamps) >= (4 if "MA_PositionReport" in obj else 1)   # 머리 + 위치·속도·자세 시각
                for _, ts in stamps:
                    offsets.add(_parse(ts) - dt.timedelta(seconds=sim_s))
    finally:
        gw.close()
    assert len(offsets) == 1


def test_sim_epoch_gives_exact_utc(bus, codec):
    epoch = dt.datetime(2026, 1, 1, tzinfo=UTC)
    sent = []
    gw = Gateway(bus, GatewayConfig(S.GCS, sim_epoch=epoch), codec=codec, sink=lambda t, o: sent.append(o))
    gw.start()
    try:
        S.deliver(bus, S.nav())                                             # sim 1.0 s
        want = uci_timestamp(epoch + dt.timedelta(seconds=1))
        assert {ts for o in sent for _, ts in _iter_timestamps(o)} == {want}
        tr = S.track_share()
        tr.header.sim_time_us, tr.observed_time_us = 5_000_000, 4_250_000
        S.deliver(bus, tr)
        ent = sent[-1]["MA_Entity"]
        assert ent["MessageHeader"]["Timestamp"] == uci_timestamp(epoch + dt.timedelta(seconds=5))
        kin = {ts for p, ts in _iter_timestamps(ent["MessageData"])}
        assert kin == {uci_timestamp(epoch + dt.timedelta(seconds=4.25))}  # 관측 시각
    finally:
        gw.close()


def test_sim_clock_anchor_and_cli():
    wall = FakeWall()
    c = SimClock(wall=wall)
    assert c.now() == wall.t                                                 # 메시지 전에는 벽시계
    assert c.at(2_000_000) == wall.t
    wall.t += dt.timedelta(hours=1)
    assert c.at(3_000_000) == c.epoch + dt.timedelta(seconds=3) and c.now() == c.at(3_000_000)
    assert c.utc(1_000_000) == c.epoch + dt.timedelta(seconds=1) and c.last_us == 3_000_000
    assert _utc("2026-01-01T00:00:00Z") == dt.datetime(2026, 1, 1, tzinfo=UTC)
    assert _utc("2026-01-01T09:00:00+09:00") == dt.datetime(2026, 1, 1, tzinfo=UTC)
    args = build_parser().parse_args(["--gcs", S.GCS, "--sim-epoch", "2026-01-01T00:00:00Z"])
    assert args.sim_epoch == dt.datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--gcs", S.GCS, "--sim-epoch", "2026-01-01T00:00:00"])   # 시간대 없음


# ---------------------------------------------------------------- TC-GW-038 (D-39)
def test_external_c2_declares_every_gateway_flow(gateway):
    """external_c2의 declared.sub = Gateway가 외부로 내는 흐름 전부 (README 교환 표 15개)"""
    cfg = yaml.safe_load((CONFIG_DIR / "lacal_server_raw.yaml").read_text(encoding="utf-8"))
    pub = {f"{u}@{gateway.config.topic(e.iface)}" for e, u in gateway.export_targets()
           if e.uci_name not in gateway.import_names()}
    ext = cfg["services"]["external_c2"]["declared"]
    assert len(pub) == 15
    assert set(ext["sub"]) == pub == set(cfg["services"]["swarm_gateway"]["declared"]["pub"])
    readme = (CONFIG_DIR.parent / "README.md").read_text(encoding="utf-8")
    for flow in pub:
        assert f"`{flow.split('@')[0]}`" in readme, flow

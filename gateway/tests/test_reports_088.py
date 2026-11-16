"""TC-GW-031~034: DEC-088 송신 4종의 외부 발행, DEC-090 상태 표현, O-20 CAL Server 선언"""
import asyncio
import math

import pytest
import yaml
from lxml import etree
from swarm.v1 import c2_pb2, common_pb2, entity_pb2, link_pb2, ms_pb2, p2p_pb2, vi_pb2
from swarm_api import keys
from swarm_api.bus import protobuf_encoding

import samples as S
from conftest import CONFIG_DIR
from swarm_gateway.gateway import GatewayConfig
from swarm_gateway.lacal import LaCalClient, schema_path
from swarm_gateway.mapping import MappingTable
from swarm_gateway.runner import start_gateway
from test_roundtrip import _wait, cal_server  # noqa: F401  (fixture)

XS = "{http://www.w3.org/2001/XMLSchema}"


def agent_envelope(msg, *, dst=(S.GCS,), priority=1, seq=7) -> link_pb2.LinkEnvelope:
    """Agent 런타임이 tx에 싣고 Datalink가 rx로 넘긴 모양 (publisher 비움, rx_time_us 채움, DEC-077)"""
    env = link_pb2.LinkEnvelope(dst=list(dst), iface=msg.DESCRIPTOR.GetOptions().Extensions[S.options_pb2.l1],
                                msg_type=msg.DESCRIPTOR.full_name, payload=msg.SerializeToString(),
                                priority=priority, rx_time_us=msg.header.sim_time_us + 30_000)
    env.header.source = msg.header.source
    env.header.sim_time_us = msg.header.sim_time_us
    env.header.seq = seq
    return env


def deliver_agent(bus, msg, **kw):
    env = agent_envelope(msg, **kw)
    bus.put(S.rx_key(msg), env.SerializeToString(), protobuf_encoding(env.DESCRIPTOR.full_name))


def _src(m, src=S.UAV, t=12_500_000):
    m.header.source = src
    m.header.sim_time_us = t
    return m


# DEC-088 송신 4종의 변형: MA가 실제로 채울 수 있는 값 조합
def approval_variants():
    return [_src(c2_pb2.ApprovalRequest(request_id="uav-001/req-1", task_id="strike-1", target_id="tgt-002",
                                        description="engage tgt-002 with sta1")),
            _src(c2_pb2.ApprovalRequest(request_id="uav-001/req-2", task_id="strike-2"))]   # 표적·설명 없음


def leader_variants():
    return [_src(p2p_pb2.LeaderUpdate(group_id="grp-a", leader="uav-003", term=12)),
            _src(p2p_pb2.LeaderUpdate(group_id="grp-a", term=0))]                          # 지도자 없음(첫 임기)


def track_variants():
    t1 = _src(p2p_pb2.TrackShare(track_id="uav-001/trk-4", target_id="tgt-002",
                                 kind=entity_pb2.ENTITY_KIND_GROUND_TARGET, observed_time_us=12_400_000))
    t1.position.lat_deg, t1.position.lon_deg, t1.position.alt_m = 37.51, 127.02, 35.0
    t1.velocity_ned_mps.x, t1.velocity_ned_mps.y = 8.0, -2.0
    t2 = _src(p2p_pb2.TrackShare(track_id="uav-001/trk-5", kind=entity_pb2.ENTITY_KIND_AIR_TARGET))   # 미식별
    t2.position.lat_deg, t2.position.lon_deg, t2.position.alt_m = -33.9, -179.9, 1200.0
    return [t1, t2]


def loadout_variants():
    full = _src(ms_pb2.StoreLoadout())
    full.stores.add(id="sta1", type="agm_short", profile="agm_generic", count=2)
    full.stores.add(id="cam0", type="camera", count=0)
    empty = _src(ms_pb2.StoreLoadout())
    empty.stores.add(id="sta1", type="agm_short", count=0)                                 # 다 쓴 뒤
    return [full, empty]


VARIANTS = {"MA_ApprovalRequest": approval_variants, "MA_LeaderUpdateRequest": leader_variants,
            "MA_Entity": track_variants, "StoreLoadoutConfiguration": loadout_variants}


@pytest.fixture(scope="module")
def xsd():
    return etree.XMLSchema(etree.parse(str(schema_path())))


# ---------------------------------------------------------------- TC-GW-031
@pytest.mark.parametrize("uci", sorted(VARIANTS))
def test_dec088_messages_export_with_agent_envelope(gateway, sent, xsd, uci):
    """Agent 모양 봉투로 온 4종이 모두 공개 XSD를 통과해 swarm.<iface>로 나간다"""
    msgs = VARIANTS[uci]()
    for m in msgs:
        deliver_agent(gateway.bus, m)
    assert [next(iter(o)) for _, o in sent] == [uci] * len(msgs)
    entry = MappingTable.from_descriptors().by_uci(uci)[0]
    assert {t for t, _ in sent} == {f"swarm.{entry.iface}"}
    for _, obj in sent:
        assert xsd.validate(etree.fromstring(gateway.to_xml(obj))), xsd.error_log
        assert obj[uci]["MessageHeader"]["Mode"] == "SIMULATION"
    assert gateway.counters["rejected"] == 0 and gateway.counters["exported"] == len(msgs)


def test_dec088_content(gateway, sent):
    for make in VARIANTS.values():
        for m in make():
            deliver_agent(gateway.bus, m)
    data = [(next(iter(o)), next(iter(o.values()))["MessageData"]) for _, o in sent]
    ids = gateway.ids
    ar1, ar2, lu1, lu2, tr1, tr2, sl1, sl2 = (d for _, d in data)
    # ApprovalRequest: 요청·작업 ID, 응답 대상 기억 (DEC-075 응답이 요청 기체로 간다)
    assert ar1["RequestID"]["DescriptiveLabel"] == "uav-001/req-1"
    assert ar1["ApprovalReferences"]["ApprovalItem"]["RequirementExecutionApproval"]["RequirementID"]["TaskID"][
        "DescriptiveLabel"] == "strike-1"
    assert gateway.ctx.approvals.get("uav-001/req-2", None) == S.UAV
    # LeaderUpdate: 지도자가 있을 때만 ProposedLeaderID, 요청 ID는 그룹·임기별
    assert lu1["Request"]["ProposedLeaderID"]["DescriptiveLabel"] == "uav-003"
    assert "ProposedLeaderID" not in lu2["Request"]
    assert lu1["RequestID"]["UUID"] != lu2["RequestID"]["UUID"]
    assert lu1["Request"]["Applicability"]["ApplicablePackageID"]["DescriptiveLabel"] == "grp-a"
    # MA_Entity: 위치(rad), 속도, 식별 표적 연결, 환경
    fp = tr1["Kinematics"]["Position"]["FixedPositionType"]["FixedPoint"]
    assert fp["Latitude"] == pytest.approx(math.radians(37.51)) and fp["Altitude"] == 35.0
    assert tr1["Kinematics"]["Velocity"]["NorthSpeed"] == 8.0 and tr1["Mobility"] == "MOVER"
    assert tr1["AssociatedID"][0]["DescriptiveLabel"] == "tgt-002"
    assert tr1["Identity"]["Environment"][0]["Environment"] == "GROUND"
    assert "AssociatedID" not in tr2 and tr2["Identity"]["Environment"][0]["Environment"] == "AIR"
    assert tr2["Source"]["SystemID"]["DescriptiveLabel"] == S.UAV
    # StoreLoadout: 스테이션별 잔량
    assert [x["Mnemonic"] for x in sl1["Loadout"]] == ["sta1:agm_shortx2", "cam0:camerax0"]
    assert [x["Mnemonic"] for x in sl2["Loadout"]] == ["sta1:agm_shortx0"]
    assert sl1["StoreLoadoutConfigurationID"] == ids.ref("loadout", S.UAV)


def test_dec088_broadcast_and_other_gcs(gateway, sent):
    """P2P 브로드캐스트(dst 여러 기체)도 GCS rx에 온 것이면 나간다. 다른 GCS의 rx는 받지 않는다"""
    m = track_variants()[0]
    deliver_agent(gateway.bus, m, dst=("uav-002", "uav-003", S.GCS))
    env = agent_envelope(m)
    gateway.bus.put(keys.rx("gcs-02", keys.Iface.P2P, "TrackShare"), env.SerializeToString(),
                    protobuf_encoding(env.DESCRIPTOR.full_name))
    assert [next(iter(o)) for _, o in sent] == ["MA_Entity"]


# ---------------------------------------------------------------- TC-GW-032
async def test_dec088_messages_reach_external_system(cal_server, bus, codec):  # noqa: F811
    """실제 CAL Server: 4종 모든 변형이 외부 구독자에게 도달하고 서버 XSD 검증을 통과한다"""
    url = f"ws://127.0.0.1:{cal_server.port}"
    running = await start_gateway(bus, GatewayConfig(S.GCS), url, codec=codec, admin_url=None)
    ext = LaCalClient(url, "external_c2")
    await ext.connect()
    got = []
    table = MappingTable.from_descriptors()
    try:
        for uci in VARIANTS:
            await ext.subscribe(uci, f"swarm.{table.by_uci(uci)[0].iface}", lambda n, o: got.append(n))
        want = []
        for uci, make in VARIANTS.items():
            for m in make():
                deliver_agent(bus, m)
                want.append(uci)
        await _wait(lambda: len(got) == len(want))
        assert sorted(got) == sorted(want)
        assert running.gateway.counters["send_failed"] == 0
    finally:
        await ext.close()
        await running.stop()


# ---------------------------------------------------------------- TC-GW-033
def _enum(name: str) -> set[str]:
    tree = etree.parse(str(schema_path()))
    (st,) = tree.getroot().findall(f"{XS}simpleType[@name='{name}']")
    return {e.get("value") for e in st.iter(f"{XS}enumeration")}


def test_dec090_states_use_public_xsd_enums_only(gateway, sent):
    """외부 상태 표현은 공개 XSD enum 그대로다. FlightCommandStatus의 EXECUTING·COMPLETED는 ACCEPTED로 보인다"""
    processing = _enum("CommandProcessingStateEnum")
    assert processing == {"RECEIVED", "ACCEPTED", "REJECTED", "CANCELED"}   # EXECUTING·COMPLETED 없음 (O-17)
    seen = {}
    for st in common_pb2.CommandState.values():
        m = S.flight_command_status()
        m.state = st
        m.command_id = f"fc-{st}"
        S.deliver(gateway.bus, m)
        seen[common_pb2.CommandState.Name(st)] = sent[-1][1]["MA_FlightCommandStatus"]["MessageData"][
            "CommandProcessingState"]
    assert set(seen.values()) <= processing
    assert seen["COMMAND_STATE_EXECUTING"] == seen["COMMAND_STATE_COMPLETED"] == "ACCEPTED"
    # 수행·완료는 상태 보고(MA_TaskStatus)에서 읽는다: 그 enum에는 EXECUTING·COMPLETED가 있다
    execution = _enum("RequirementExecutionStateEnum")
    task = {}
    for st in common_pb2.CommandState.values():
        m = S.task_status()
        m.state = st
        S.deliver(gateway.bus, m)
        task[common_pb2.CommandState.Name(st)] = sent[-1][1]["MA_TaskStatus"]["MessageData"]["ExecutionState"]
    assert set(task.values()) <= execution
    assert (task["COMMAND_STATE_EXECUTING"], task["COMMAND_STATE_COMPLETED"]) == ("EXECUTING", "COMPLETED")
    # StrikeActivity 상태도 공개 enum 안이다
    strike = set()
    for st in ms_pb2.StrikeState.values():
        m = S.strike_activity()
        m.state = st
        m.weapon_entity = f"w{st}"
        S.deliver(gateway.bus, m)
        strike.add(sent[-1][1]["StrikeActivity"]["MessageData"]["Activity"][0]["ActivityState"])
    assert strike <= _enum("ActivityStateEnum")
    assert gateway.counters["rejected"] == 0


def test_dec090_no_extension_fields(gateway, sent, codec):
    """내보내는 메시지는 XSD 요소만 쓴다: 다시 읽은 XML이 같은 JSON이 된다(표준 밖 필드가 없다)"""
    for make in S.EXPORT_SAMPLES.values():
        S.deliver(gateway.bus, make())
    for _, obj in sent:
        root = etree.fromstring(gateway.to_xml(obj))
        assert codec.xml_to_json(root) == obj


# ---------------------------------------------------------------- TC-GW-034
def test_o20_lacal_config_declares_all_gateway_messages(gateway):
    """CAL Server 설정의 declared가 Gateway가 실제로 PUB·SUB하는 것과 같다 (MA_PositionReport 포함)"""
    cfg = yaml.safe_load((CONFIG_DIR / "lacal_server.yaml").read_text(encoding="utf-8"))
    declared = cfg["services"]["swarm_gateway"]["declared"]
    pub = {f"{u}@{gateway.config.topic(e.iface)}" for e, u in gateway.export_targets()
           if e.uci_name not in gateway.import_names()}                # 받는 명령은 되돌려 보내지 않는다
    sub = {f"{e.uci_name}@{gateway.config.topic(e.iface)}" for e in gateway.import_entries()}
    assert "MA_PositionReport@swarm.vi" in declared["pub"] and "MA_PositionReport@swarm.p2p" in declared["pub"]
    assert set(declared["pub"]) == pub
    assert set(declared["sub"]) == sub
    ext = cfg["services"]["external_c2"]["declared"]
    assert set(ext["pub"]) == sub

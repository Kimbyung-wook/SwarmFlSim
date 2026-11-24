"""TC-GW-052~056: 외부 인터페이스 봉투 MA_TxDataPayloadCommand·MA_RxDataPayload (DEC-111, IMP-GW-036)"""
import uuid

import pytest
import yaml
from lxml import etree
from swarm.v1 import c2_pb2, common_pb2, link_pb2

import samples as S
from conftest import CONFIG_DIR
from swarm_gateway.envelope import RX, TX, EnvelopeError, Envelopes, message_type_name, to_ascii
from swarm_gateway.gateway import Gateway, GatewayConfig
from swarm_gateway.lacal import LaCalClient
from swarm_gateway.runner import start_gateway
from test_import import _task_command
from test_inbound_plans import route_data
from test_roundtrip import _wait, cal_server  # noqa: F401  (fixture)

C2 = "a2f74db0-1111-4222-8333-444455556666"        # 외부 C2 시스템 UUID (시험 값)
OTHER = "0badc0de-0000-4000-8000-000000000001"


def _gw(bus, codec, sent=None, **cfg):
    gw = Gateway(bus, GatewayConfig(S.GCS, envelope=True, scenario_query_attempts=0, **cfg), codec=codec,
                 sink=(lambda t, o: sent.append((t, o))) if sent is not None else None)
    gw.start()
    S.load_scenario(bus)
    return gw


def _tx_ids(bus):
    got = []
    bus.subscribe("swarm/gcs-01/tx/c2/TaskCommand",
                  lambda s: got.append(c2_pb2.TaskCommand.FromString(link_pb2.LinkEnvelope.FromString(s.payload).payload)
                                       .task_id))
    return got


# ---------------------------------------------------------------- TC-GW-052 송신 봉투
def test_outbound_is_wrapped_in_tx_envelope(bus, codec):
    sent = []
    gw = _gw(bus, codec, sent, envelope_destinations=(C2,))
    try:
        S.deliver(bus, S.task_status())
        (topic, env), = sent
        assert topic == "swarm.c2" and set(env) == {TX}
        body = env[TX]
        data = body["MessageData"]
        assert data["CommandState"] == "NEW" and data["MessageType"] == "MA_TASK_STATUS"
        assert data["Priority"] == {"Priority": 1, "PrecedenceWithinPriority": 1}
        assert data["DestinationRouting"] == "TOPIC_AND_SPECIFIC_DESTINATION"
        assert data["SpecificDestinationID"] == [{"UUID": C2}]
        raw = bytes.fromhex(data["EncodedPayload"])
        assert data["EncodedPayload"] == data["EncodedPayload"].upper() and raw.startswith(b"<?xml") and raw.isascii()
        name, inner = gw.envelopes.open_tx(env)                     # 봉투·내부 모두 XSD 통과
        assert name == "MA_TaskStatus"
        assert body["MessageHeader"] == inner[name]["MessageHeader"]  # 내부 머리 복사
        assert data["Timestamp"] == inner[name]["MessageHeader"]["Timestamp"]
        gw.to_xml(env)
        S.deliver(bus, S.task_status())
        assert sent[1][1][TX]["MessageData"]["CommandID"] != data["CommandID"]   # 매번 새 CommandID
        assert gw.counters["envelope_tx"] == 2
    finally:
        gw.close()


def test_envelope_xml_order_and_no_destination(codec):
    env = Envelopes(codec)
    gw = Gateway(None, GatewayConfig(S.GCS), codec=codec)        # type: ignore[arg-type]
    tx = env.wrap(_task_command(gw))
    assert "SpecificDestinationID" not in tx[TX]["MessageData"]
    root = etree.fromstring(codec.to_xml_bytes(tx))
    order = [etree.QName(c).localname for c in root.find("{*}MessageData")]
    assert order == ["CommandID", "CommandState", "EncodedPayload", "MessageType", "Priority", "Timestamp",
                     "DestinationRouting"]
    hdr = root.find("{*}MessageHeader/{*}SystemID/{*}UUID").text
    assert len(hdr) == 32 and "-" not in hdr                       # XML에서는 32자 hex


@pytest.mark.parametrize("name,want", [("MA_TaskCommand", "MA_TASK_COMMAND"), ("SystemStatus", "SYSTEM_STATUS"),
                                       ("PO_Activity", "PO_ACTIVITY"), ("QueryDataRequestStatus",
                                                                        "QUERY_DATA_REQUEST_STATUS"),
                                       ("MA_RxDataPayload", "MA_RX_DATA_PAYLOAD")])
def test_message_type_from_xsd(codec, name, want):
    assert message_type_name(name) == want and want in Envelopes(codec).message_types
    assert all(message_type_name(n) in Envelopes(codec).message_types for n in codec.message_names())
    with pytest.raises(EnvelopeError):
        Envelopes(codec).message_type("NotAMessage")


# ---------------------------------------------------------------- TC-GW-053 수신 봉투
def test_inbound_envelope_is_unwrapped_and_published(bus, codec):
    gw = _gw(bus, codec)
    tx = _tx_ids(bus)
    try:
        for dest in ((), (gw.system_uuid,), (OTHER, gw.system_uuid)):   # 비었거나 우리 UUID 포함
            rx = gw.envelopes.rx(_task_command(gw), C2, gw.system_uuid, list(dest))
            assert gw.handle_incoming(RX, rx).status == "published"
        assert len(tx) == 3 and gw.counters["envelope_rx"] == 3
        mp = gw.envelopes.rx(gw.envelope("MA_RoutePlan", route_data()), C2, gw.system_uuid)
        assert gw.handle_incoming(RX, mp).status == "published"
    finally:
        gw.close()


def test_inbound_not_addressed_is_ignored(bus, codec):
    gw = _gw(bus, codec)
    tx = _tx_ids(bus)
    try:
        rx = gw.envelopes.rx(_task_command(gw), C2, gw.system_uuid, [OTHER])
        out = gw.handle_incoming(RX, rx)
        assert out.status == "ignored" and tx == [] and gw.counters["envelope_not_addressed"] == 1
        assert gw.counters["rejected"] == 0                          # 거부가 아니다
    finally:
        gw.close()


def _rx_with(gw, **change):
    rx = gw.envelopes.rx(_task_command(gw), C2, gw.system_uuid)
    rx[RX]["MessageData"].update(change)
    return rx


@pytest.mark.parametrize("change,why", [
    ({"MessageType": "MA_ROUTE_PLAN"}, "does not match"),
    ({"EncodedPayload": "3C3F786D6C".lower() + "C3A9"}, "not ASCII"),
    ({"EncodedPayload": b"<MA_TaskCommand/>".hex().upper()}, "inner message invalid"),
    ({"EncodedPayload": "ZZ"}, "envelope invalid"),
])
def test_bad_envelopes_are_rejected(bus, codec, change, why):
    gw = _gw(bus, codec)
    tx = _tx_ids(bus)
    try:
        out = gw.handle_incoming(RX, _rx_with(gw, **change))
        assert out.status == "rejected" and why in out.reason and tx == []
        assert gw.counters["envelope_invalid"] == 1
    finally:
        gw.close()


def test_raw_message_needs_envelope_when_on(bus, codec):
    gw = _gw(bus, codec)
    try:
        out = gw.handle_incoming("MA_TaskCommand", _task_command(gw))
        assert out.status == "rejected" and "envelope required" in out.reason
        assert gw.inbound_names() == [RX]
    finally:
        gw.close()
    off = Gateway(bus, GatewayConfig(S.GCS, scenario_query_attempts=0), codec=codec)
    assert off.outbound({"X": {}}) == {"X": {}} and off.inbound_names() == off.import_names()


def test_rejection_notice_goes_out_in_envelope(bus, codec):
    """알려지지 않은 기체 명령(D-35) 거부의 MA_TaskStatus(DROPPED)도 봉투로 나간다"""
    sent = []
    gw = _gw(bus, codec, sent)
    try:
        rx = gw.envelopes.rx(_task_command(gw, assignees=("uav-999",)), C2, gw.system_uuid)
        assert gw.handle_incoming(RX, rx).status == "rejected"
        (topic, env), = sent
        name, inner = gw.envelopes.open_tx(env)
        assert name == "MA_TaskStatus" and inner[name]["MessageData"]["ExecutionState"] == "DROPPED"
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-054 ASCII
def test_non_ascii_strings_are_replaced(bus, codec):
    sent = []
    gw = _gw(bus, codec, sent)
    try:
        m = S.task_status()
        m.state = common_pb2.COMMAND_STATE_REJECTED
        m.reason = "거부 café"                                      # 자유 문장 필드 (DescriptiveLabel은 XSD가 이미 ASCII)
        S.deliver(bus, m)
        (_, env), = sent
        _, inner = gw.envelopes.open_tx(env)
        assert inner["MA_TaskStatus"]["MessageData"]["ExecutionStateReason"]["Description"].endswith("?? cafe")
        assert bytes.fromhex(env[TX]["MessageData"]["EncodedPayload"]).isascii()
        assert gw.counters["envelope_ascii_replaced"] == 1
    finally:
        gw.close()
    assert to_ascii({"a": ["한", "x"]}) == {"a": ["?", "x"]}


# ---------------------------------------------------------------- TC-GW-055 실제 CAL Server
async def test_envelope_roundtrip_with_cal_server(cal_server, bus, codec):  # noqa: F811
    """CAL Server: 외부가 MA_RxDataPayload로 보낸 명령이 tx로 나가고, 보고는 MA_TxDataPayloadCommand로 받는다"""
    url = f"ws://127.0.0.1:{cal_server.port}"
    running = await start_gateway(bus, GatewayConfig(S.GCS, envelope=True, envelope_destinations=(C2,)), url,
                                  codec=codec, admin_url=None, settle_s=0)
    gw = running.gateway
    S.load_scenario(bus)
    ext = LaCalClient(url, "external_c2")
    await ext.connect()
    got = []
    tx = _tx_ids(bus)
    try:
        for t in ("swarm.vi", "swarm.c2"):
            await ext.subscribe(TX, t, lambda n, o: got.append(o))
        await ext.publish("swarm.c2", gw.envelopes.rx(_task_command(gw), C2, gw.system_uuid))
        await _wait(lambda: tx == ["task-5"])
        S.deliver(bus, S.nav())
        S.deliver(bus, S.task_status())
        await _wait(lambda: len(got) >= 3)
        names = sorted(gw.envelopes.open_tx(o)[0] for o in got)
        assert names == ["MA_NavigationReport", "MA_PositionReport", "MA_TaskStatus"]
        assert all(o[TX]["MessageData"]["SpecificDestinationID"] == [{"UUID": C2}] for o in got)
        await ext.publish("swarm.c2", gw.envelopes.rx(_task_command(gw), C2, gw.system_uuid, [OTHER]))
        await _wait(lambda: gw.counters["envelope_not_addressed"] == 1)
        assert len(tx) == 1
    finally:
        await ext.close()
        await running.stop()


# ---------------------------------------------------------------- TC-GW-056 늦게 붙은 구독자·설정
def test_late_join_targets_use_envelope_name(bus, codec):
    gw = _gw(bus, codec, [])
    try:
        S.deliver(bus, S.system_status())
        assert (TX, "swarm.vi") in gw.retained.targets()
        assert [next(iter(o)) for o in gw.retained.latest(TX, "swarm.vi")] == ["SystemStatus"]   # 보낼 때 싼다
    finally:
        gw.close()


@pytest.mark.parametrize("fname,envelope", [("lacal_server.yaml", True), ("lacal_server_raw.yaml", False)])
def test_declared_flows_match_mode(codec, fname, envelope):
    gw = Gateway(None, GatewayConfig(S.GCS, envelope=envelope), codec=codec)   # type: ignore[arg-type]
    cfg = yaml.safe_load((CONFIG_DIR / fname).read_text(encoding="utf-8"))["services"]
    topics = {gw.config.topic(e.iface) for e, _ in gw.export_targets() if e.uci_name not in gw.import_names()}
    in_topics = {gw.config.topic(e.iface) for e in gw.import_entries()}
    if envelope:
        pub = {f"{TX}@{t}" for t in topics}
        sub = {f"{RX}@{t}" for t in in_topics}
    else:
        pub = {f"{u}@{gw.config.topic(e.iface)}" for e, u in gw.export_targets() if e.uci_name not in gw.import_names()}
        sub = {f"{e.uci_name}@{gw.config.topic(e.iface)}" for e in gw.import_entries()}
    assert set(cfg["swarm_gateway"]["declared"]["pub"]) == pub == set(cfg["external_c2"]["declared"]["sub"])
    assert set(cfg["swarm_gateway"]["declared"]["sub"]) == sub == set(cfg["external_c2"]["declared"]["pub"])


def test_cli_envelope_options():
    from swarm_gateway.__main__ import build_parser
    a = build_parser().parse_args(["--gcs", S.GCS])
    assert a.envelope == "on" and a.envelope_dest == []
    a = build_parser().parse_args(["--gcs", S.GCS, "--envelope", "off", "--envelope-dest", C2.replace("-", "")])
    assert a.envelope == "off" and a.envelope_dest == [str(uuid.UUID(C2))]

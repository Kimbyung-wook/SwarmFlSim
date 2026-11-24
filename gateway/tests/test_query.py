"""TC-GW-062~069: QueryDataRequest 응답 (DEC-112, IMP-GW-038·039)"""
import pytest
from lxml import etree

import samples as S
from swarm_gateway.envelope import RX, TX, Envelopes
from swarm_gateway.gateway import Gateway, GatewayConfig
from swarm_gateway.query import QUERY, QUERY_STATUS
from test_roundtrip import _wait
from test_stomp import C2, PLATFORM, broker, _start  # noqa: F401  (fixture)

RID = "7d1c3e5a-0000-4000-8000-00000000abcd"


def _gw(bus, codec, **cfg):
    sent = []
    gw = Gateway(bus, GatewayConfig(S.GCS, scenario_query_attempts=0, **cfg), codec=codec,
                 sink=lambda t, o: sent.append((t, o)))
    gw.system_uuid = PLATFORM
    gw.start()
    S.load_scenario(bus)
    return gw, sent


def _query(gw, *types, state="NEW", rid=RID, **data):
    md = {"RequestID": {"UUID": rid}, "RequestState": state, **data,
          "QueryMessage": {"MessageType": list(types)} if types else {}}
    return gw.envelope(QUERY, md)


def _statuses(sent):
    return [o[QUERY_STATUS]["MessageData"] for _, o in sent if QUERY_STATUS in o]


def _results(status):
    return status.get("Result", {}).get("Message", [])


def _ask(gw, sent, *types, **data):
    sent.clear()
    out = gw.handle_external(QUERY, _query(gw, *types, **data))
    return out, _statuses(sent)


# ---------------------------------------------------------------- TC-GW-062 최신 값으로 답함
def test_answers_with_latest_exported_values(bus, codec):
    gw, sent = _gw(bus, codec)
    try:
        S.deliver(bus, S.task_status())
        nav = S.nav()
        S.deliver(bus, nav)
        nav.kinematics.position.lat_deg = 37.6                       # 같은 기체 두 번째 보고: 최신 값만
        S.deliver(bus, nav)
        S.deliver(bus, S._h(S.nav(), "uav-002"))                     # 다른 기체
        exported = [o for _, o in sent if "MA_PositionReport" in o]
        assert len(exported) == 3 and exported[0] != exported[1]
        out, st = _ask(gw, sent, "MA_POSITION_REPORT", "MA_TASK_STATUS")
        assert out.status == "answered" and out.reason == "COMPLETED"
        assert [s["RequestProcessingState"] for s in st] == ["PROCESSING", "COMPLETED"]
        assert all(s["RequestID"] == {"UUID": RID} for s in st)      # RequestID 그대로
        res = _results(st[1])
        kinds = sorted(r["$type"] for r in res)
        assert kinds == ["MA_PositionReportMT", "MA_PositionReportMT", "MA_TaskStatusMT"]
        pos = [r["MessageData"] for r in res if r["$type"] == "MA_PositionReportMT"]
        assert pos == [o["MA_PositionReport"]["MessageData"] for o in exported[1:]]   # uav-001 두 번째, uav-002
        gw.to_xml({QUERY_STATUS: next(o[QUERY_STATUS] for _, o in sent if
                                      o[QUERY_STATUS]["MessageData"]["RequestProcessingState"] == "COMPLETED")})
        assert all(t == "swarm.c2" for t, _ in sent)
        assert gw.counters["query_rx"] == 1 and gw.counters["query.COMPLETED"] == 1
        assert not bus.published or all("/tx/" not in k for k in bus.published)   # 버스로 넘기지 않는다
    finally:
        gw.close()


def test_empty_type_list_means_all_and_no_values_yet(bus, codec):
    gw, sent = _gw(bus, codec)
    try:
        _, st = _ask(gw, sent, "SYSTEM_STATUS")
        assert st[-1]["RequestProcessingState"] == "COMPLETED" and "Result" not in st[-1]   # 아직 값 없음
        S.deliver(bus, S.system_status())
        S.deliver(bus, S.task_status())
        _, st = _ask(gw, sent)
        assert {r["$type"] for r in _results(st[-1])} >= {"SystemStatusMT", "MA_TaskStatusMT"}
        _, st = _ask(gw, sent, QueryResultLimit=1)
        assert len(_results(st[-1])) == 1
        _, st = _ask(gw, sent, "SYSTEM_STATUS", SystemID={"UUID": C2})   # SystemID는 요청한 시스템: 거르지 않는다
        assert st[-1]["RequestProcessingState"] == "COMPLETED" and len(_results(st[-1])) == 1
        _, st = _ask(gw, sent, "SYSTEM_STATUS", SystemID={"UUID": PLATFORM}, MostRecentMessagesOnly="")
        assert len(_results(st[-1])) == 1
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-063 거부
@pytest.mark.parametrize("types,data,reason,text", [
    (("WEATHER",), {}, "CAPABILITY_UNAVAILABLE", "WEATHER"),
    (("MA_TASK_COMMAND",), {}, "CAPABILITY_UNAVAILABLE", "MA_TASK_COMMAND"),   # 받는 명령은 조회 대상 아님
    (("SYSTEM_STATUS",), {"QueryIdentifiersOnly": ""}, "INVALID_INPUT_PARAMETER", "QueryIdentifiersOnly"),
    (("SYSTEM_STATUS",), {"ResultsInNative": [{"MessageType": "WEATHER", "ReceiverAddress": "x"}]},
     "CAPABILITY_UNAVAILABLE", "WEATHER"),
])
def test_unanswerable_queries_are_rejected_with_reason(bus, codec, types, data, reason, text):
    gw, sent = _gw(bus, codec)
    try:
        out, st = _ask(gw, sent, *types, **data)
        assert [s["RequestProcessingState"] for s in st] == ["REJECTED"]   # 처리하지 않으므로 하나만 (TC-GW-066)
        r = st[0]["RequestProcessingStateReason"]
        assert r["Reason"] == reason and text in r["Description"]
        assert out.reason == "REJECTED" and gw.counters["query.REJECTED"] == 1
    finally:
        gw.close()


def test_condition_and_invalid(bus, codec):
    gw, sent = _gw(bus, codec)
    try:
        q = _query(gw, "SYSTEM_STATUS")
        q[QUERY]["MessageData"]["QueryMessage"]["Query"] = {"$type": "QueryType", "Exists": {"Step": [{"Root": ""}]}}
        gw.to_xml(q)                                                 # XSD에 맞는 조건식
        sent.clear()
        gw.handle_external(QUERY, q)
        st = _statuses(sent)
        assert [s["RequestProcessingState"] for s in st] == ["REJECTED"]
        r = st[0]["RequestProcessingStateReason"]
        assert r["Reason"] == "INVALID_INPUT_PARAMETER" and r["Description"].endswith("Query condition")
        bad = _query(gw, "SYSTEM_STATUS")
        del bad[QUERY]["MessageData"]["RequestID"]
        assert gw.handle_external(QUERY, bad).status == "rejected" and gw.counters["query_invalid"] == 1
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-067 쪽 나눔
def test_results_per_page_splits_into_completed_pages(bus, codec):
    gw, sent = _gw(bus, codec)
    try:
        for uav in ("uav-001", "uav-002", "uav-003"):
            S.deliver(bus, S._h(S.system_status(), uav))
        _, st = _ask(gw, sent, "SYSTEM_STATUS", ResultsPerPage=2)
        assert [s["RequestProcessingState"] for s in st] == ["PROCESSING", "COMPLETED", "COMPLETED"]
        assert [s["QueryPagination"] for s in st[1:]] == [{"CurrentPage": 1, "TotalPages": 2},
                                                          {"CurrentPage": 2, "TotalPages": 2}]
        assert [len(_results(s)) for s in st[1:]] == [2, 1]
        for _, o in sent:
            gw.to_xml(o)                                             # 쪽마다 XSD 통과
        _, st = _ask(gw, sent, "SYSTEM_STATUS", ResultsPerPage=5)    # 한 쪽에 들어가면 나누지 않는다
        assert len(_results(st[-1])) == 3 and "QueryPagination" not in st[-1]
        assert gw.counters["query.COMPLETED"] == 3
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-068 원형 배달
def test_results_in_native_resends_messages_on_their_topic(bus, codec):
    gw, sent = _gw(bus, codec)
    try:
        S.deliver(bus, S.system_status())
        S.deliver(bus, S.task_status())
        first = [(t, o) for t, o in sent if "SystemStatus" in o]
        assert len(first) == 1
        sent.clear()
        gw.handle_external(QUERY, _query(gw, "SYSTEM_STATUS", "MA_TASK_STATUS",
                                         ResultsInNative=[{"MessageType": "SYSTEM_STATUS", "ReceiverAddress": "c2"}]))
        assert [next(iter(o)) for _, o in sent] == [QUERY_STATUS, "SystemStatus", QUERY_STATUS]
        assert [(t, o) for t, o in sent if "SystemStatus" in o] == first   # 같은 토픽, 같은 메시지
        done = _statuses(sent)[-1]
        assert done["RequestProcessingState"] == "COMPLETED"
        assert [r["$type"] for r in _results(done)] == ["MA_TaskStatusMT"]   # 원형으로 간 것은 Result에서 뺀다
        assert gw.counters["query_native"] == 1
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-069 CANCEL
def test_cancel_of_unknown_and_finished_requests(bus, codec):
    gw, sent = _gw(bus, codec)
    try:
        other = "7d1c3e5a-0000-4000-8000-00000000ffff"
        _, st = _ask(gw, sent, "SYSTEM_STATUS", state="CANCEL", rid=other)   # 받은 적 없는 요청
        assert [s["RequestProcessingState"] for s in st] == ["REJECTED"]
        assert st[0]["RequestProcessingStateReason"]["Reason"] == "UNKNOWN_ID"
        assert st[0]["RequestID"] == {"UUID": other}
        _ask(gw, sent, "SYSTEM_STATUS")                                       # 끝난 요청: 끝 상태를 다시 알린다
        _, st = _ask(gw, sent, "SYSTEM_STATUS", state="CANCEL")
        assert [s["RequestProcessingState"] for s in st] == ["COMPLETED"] and "Result" not in st[0]
        _ask(gw, sent, "WEATHER", rid=other)                                  # 거부한 요청의 CANCEL
        _, st = _ask(gw, sent, state="CANCEL", rid=other)
        assert [s["RequestProcessingState"] for s in st] == ["REJECTED"] and "RequestProcessingStateReason" not in st[0]
        _, st = _ask(gw, sent, "SYSTEM_STATUS", state="UPDATE")               # UPDATE는 NEW처럼 다시 답한다
        assert [s["RequestProcessingState"] for s in st] == ["PROCESSING", "COMPLETED"]
        for _, o in sent:
            gw.to_xml(o)
    finally:
        gw.close()


def test_excluded_messages_are_not_queryable(bus, codec):
    """5.0a 설정에서 내보내지 않는 MA_NavigationReport는 조회해도 거부한다 (DEC-110과 같은 범위)"""
    gw, sent = _gw(bus, codec, exclude_messages=("MA_NavigationReport", "MA_Entity"))
    try:
        _, st = _ask(gw, sent, "MA_NAVIGATION_REPORT")
        assert st[-1]["RequestProcessingStateReason"]["Reason"] == "CAPABILITY_UNAVAILABLE"
        assert "MA_NavigationReport" not in gw.exported_names() and "MA_PositionReport" in gw.exported_names()
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-064 봉투
def test_query_in_envelope_answered_in_envelope(bus, codec):
    gw, sent = _gw(bus, codec, envelope=True)
    try:
        S.deliver(bus, S.system_status())
        sent.clear()
        env = Envelopes(codec)
        rx = env.rx(_query(gw, "SYSTEM_STATUS"), originator=C2, receiver=PLATFORM, destinations=[PLATFORM])
        out = gw.handle_incoming(RX, rx)
        assert out.status == "answered"
        inner = [env.open_tx(o) for _, o in sent]                    # 봉투·내부 모두 XSD 통과
        assert [n for n, _ in inner] == [QUERY_STATUS, QUERY_STATUS]
        assert [o[TX]["MessageData"]["MessageType"] for _, o in sent] == ["QUERY_DATA_REQUEST_STATUS"] * 2
        assert [i[QUERY_STATUS]["MessageData"]["RequestProcessingState"] for _, i in inner] == ["PROCESSING", "COMPLETED"]
        assert _results(inner[1][1][QUERY_STATUS]["MessageData"])[0]["$type"] == "SystemStatusMT"
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-065 STOMP·LA-CAL 구독
async def test_query_over_stomp(broker, bus, codec):  # noqa: F811
    running = await _start(bus, codec, broker)
    gw = running.gateway
    try:
        S.deliver(bus, S.system_status())
        env = Envelopes(codec)
        rx = env.rx(_query(gw, "SYSTEM_STATUS"), originator=C2, receiver=PLATFORM)
        await broker.publish(f"/topic/{RX}", codec.to_xml_bytes(rx))
        await _wait(lambda: gw.counters["query.COMPLETED"] == 1)

        def statuses():
            got = [env.open_tx(codec.xml_to_json(etree.fromstring(b))) for b in broker.sent(f"/topic/{TX}")]
            return [i[QUERY_STATUS]["MessageData"]["RequestProcessingState"] for n, i in got if n == QUERY_STATUS]
        await _wait(lambda: len(statuses()) == 2)
        assert statuses() == ["PROCESSING", "COMPLETED"]
    finally:
        await running.stop()


async def test_raw_mode_subscribes_query(broker, bus, codec):  # noqa: F811
    running = await _start(bus, codec, broker, envelope=False)
    try:
        assert f"/topic/{QUERY}" in broker.subscribed()
        q = _query(running.gateway, "SYSTEM_STATUS")
        await broker.publish(f"/topic/{QUERY}", codec.to_xml_bytes(q))
        await _wait(lambda: len(broker.sent(f"/topic/{QUERY_STATUS}")) == 2)
    finally:
        await running.stop()

"""표준 적합성 점검 도구의 판정 로직 단위 시험 (TC-QA-164~171). 일부러 위반을 넣은 입력은 실패해야 한다.

uv run python -m pytest qa/conformance/tests -q
"""
from __future__ import annotations

import math
import os
import sys
from collections import Counter
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import confcommon  # noqa: E402
import findings as F  # noqa: E402
import judges as J  # noqa: E402
import static  # noqa: E402
from confcommon import FAIL, INFO, PASS  # noqa: E402

# ------------------------------------------------------------------------------------------- TC-QA-164 C1


def _proto(short, uci="", mapping="STD", l1="VI", also=()):  # noqa: ANN001, ANN202
    return {"full_name": f"swarm.v1.{short}", "short": short, "file": "x.proto", "uci_name": uci,
            "uci_also": list(also), "mapping": mapping, "l1": l1}


def _conv(short, export=True, imp=False):  # noqa: ANN001, ANN202
    return {"proto": f"swarm.v1.{short}", "cls": f"{short}Conv", "module": "m", "export": export, "import": imp}


XSD = {"MA_NavigationReport", "MA_PositionReport", "MA_TaskCommand", "MA_TaskStatus"}
REG = [{"l1": "VI", "interaction": "항법 보고", "candidates": ["MA_NavigationReport"], "cls": "STD"},
       {"l1": "C2", "interaction": "작업 명령", "candidates": ["MA_TaskCommand"], "cls": "STD"},
       {"l1": "C2", "interaction": "모르는 것", "candidates": ["MA_Unknown"], "cls": "STD"}]


def _c1(proto, conv, also=(), imp=(), observed=None):  # noqa: ANN001, ANN202
    tr = {"NavigationReport": {"imp": ["IMP-GW-001"], "tc": ["TC-GW-001"]}}
    return J.judge_c1(proto, XSD, conv, list(also), REG, tr, list(imp), observed)


def test_c1_clean_passes_and_status():
    proto = [_proto("NavigationReport", "MA_NavigationReport", also=["MA_PositionReport"]),
             _proto("TaskCommand", "MA_TaskCommand", l1="C2"), _proto("Truth", mapping="SIM", l1="UNSPECIFIED")]
    also = [{"uci": "MA_PositionReport", "cls": "P", "module": "m", "protos": [], "export": True}]
    r = _c1(proto, [_conv("NavigationReport"), _conv("TaskCommand", False, True)], also, ["MA_TaskCommand"],
            {"MA_NavigationReport"})
    assert r["verdict"] == PASS, r["fail"]
    st = {(x["uci"], x["internal"]): x["status"] for x in r["rows"]}
    assert st[("MA_NavigationReport", "NavigationReport")] == "구현·시험됨"
    assert st[("MA_TaskCommand", "TaskCommand")] == "부분"          # TRACE에 IMP·TC 없음
    assert st[("MA_Unknown", "—")] == "미구현"                       # 미구현은 실패가 아니다
    dirs = {x["uci"]: x["dir"] for x in r["rows"]}
    assert dirs["MA_TaskCommand"] == "수신" and dirs["MA_NavigationReport"] == "송신"
    assert r["summary"]["xsd_ma"] == 4 and r["summary"]["send"] == 2 and r["summary"]["recv"] == 1


def test_c1_std_without_converter_fails():
    r = _c1([_proto("NavigationReport", "MA_NavigationReport")], [])
    assert r["verdict"] == FAIL and any("STD인데 변환기가 없다" in t for t in r["fail"])


def test_c1_uci_name_not_in_xsd_fails():
    r = _c1([_proto("NavigationReport", "MA_NavReport")], [_conv("NavigationReport")])
    assert r["verdict"] == FAIL and any("XSD 최상위 요소에 없다" in t for t in r["fail"])


def test_c1_uci_also_missing_converter_or_xsd_fails():
    r = _c1([_proto("NavigationReport", "MA_NavigationReport", also=["MA_PositionReport"])], [_conv("NavigationReport")])
    assert any("uci_also MA_PositionReport 변환기가 없다" in t for t in r["fail"])
    r = _c1([_proto("NavigationReport", "MA_NavigationReport", also=["MA_Nope"])], [_conv("NavigationReport")],
            [{"uci": "MA_Nope", "cls": "P", "module": "m", "protos": [], "export": True}])
    assert any("uci_also MA_Nope이 XSD" in t for t in r["fail"])


def test_c1_converter_on_non_std_fails():
    r = _c1([_proto("Truth", mapping="SIM")], [_conv("Truth")])
    assert r["verdict"] == FAIL and any("STD가 아니다 (SIM)" in t for t in r["fail"])
    r = _c1([], [_conv("Ghost")])
    assert any("proto에 없음" in t for t in r["fail"])


def test_c1_xsd_and_registry_readers():
    xsd = static.xsd_top_elements()
    assert "MA_TaskCommand" in xsd and len(xsd) > 500
    reg = static.registry_rows((confcommon.ROOT / "docs" / "02_registry.md").read_text(encoding="utf-8"))
    assert reg and all({"l1", "interaction", "candidates", "cls"} <= set(r) for r in reg)


# ------------------------------------------------------------------------------------------- TC-QA-165 C2

def test_c2_clean_passes():
    r = J.judge_c2([{"client": "e", "name": "MA_TaskStatus", "ok": True}],
                   [{"tag": "a", "name": "MA_TaskCommand", "xsd_ok": True, "pub": "+OK", "negative": False},
                    {"tag": "neg-x", "name": "MA_TaskCommand", "xsd_ok": False, "pub": "-ERR", "negative": True}],
                   [{"tag": "neg-x", "on_bus": False, "how": "CAL Server 거부"}])
    assert r["verdict"] == PASS, r["fail"]


def test_c2_rx_xsd_failure_fails():
    r = J.judge_c2([{"client": "e", "name": "MA_TaskStatus", "ok": False}], [], [])
    assert r["verdict"] == FAIL and "XSD 재검증 실패 1/1" in r["fail"][0]


def test_c2_negative_on_bus_fails():
    r = J.judge_c2([{"client": "e", "name": "A", "ok": True}], [],
                   [{"tag": "neg-unknown", "on_bus": True, "how": "", "bus_key": "swarm/gcs-01/tx/c2/TaskCommand"}])
    assert r["verdict"] == FAIL and "버스로 나감" in r["fail"][0]


def test_c2_negative_without_rejection_record_fails():
    r = J.judge_c2([{"client": "e", "name": "A", "ok": True}], [], [{"tag": "neg-q", "on_bus": False, "how": ""}])
    assert r["verdict"] == FAIL and "거부 기록이 없다" in r["fail"][0]


def test_c2_valid_send_refused_fails():
    r = J.judge_c2([{"client": "e", "name": "A", "ok": True}],
                   [{"tag": "hold", "name": "MA_TaskCommand", "xsd_ok": True, "pub": "-ERR x", "negative": False}], [])
    assert r["verdict"] == FAIL


# ------------------------------------------------------------------------------------------- TC-QA-166 C3

def _uci_of(lat, lon, alt, vel=None, q=None):  # noqa: ANN001, ANN202
    """도구와 다른 방법으로 기대 UCI 값을 만든다(위경도 rad, 자세는 축 회전 합성)"""
    ypr = J.euler_from_quat_matrix(*q) if q else None
    return {"lat": math.radians(lat), "lon": math.radians(lon), "alt": alt, "ref": "MSL", "vel": vel, "ypr": ypr}


def _quat_ypr(yaw, pitch, roll):  # noqa: ANN001, ANN202
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    return (cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy)


def test_c3_euler_matrix_matches_known_rotations():
    for ypr in ((0.0, 0.0, 0.0), (math.pi / 2, 0.0, 0.0), (0.3, -0.2, 0.1), (-2.5, 0.4, -0.7)):
        got = J.euler_from_quat_matrix(*_quat_ypr(*ypr))
        assert all(abs(J.wrap_pi(a - b)) < 1e-12 for a, b in zip(got, ypr)), (ypr, got)
    # 북쪽(NED x)에서 동쪽으로 90° 돌린 FRD: yaw +π/2 (시계 방향 양수)
    q = (math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))
    assert abs(J.euler_from_quat_matrix(*q)[0] - math.pi / 2) < 1e-12


def _good_c3(**over):  # noqa: ANN003, ANN202
    q = _quat_ypr(0.4, 0.05, -0.1)
    bus = {"lat_deg": 37.5, "lon_deg": 128.0, "alt_m": 500.0, "vel": (1.0, 22.0, -0.5), "q": q}
    uci = _uci_of(37.5, 128.0, 500.0, (1.0, 22.0, -0.5), q)
    uci.update(over.pop("uci", {}))
    pair = {**J.compare_position(bus, uci), "who": "uav-001", "topic": "swarm.vi"}
    args = {"pos_pairs": [pair], "ts_offsets": [100.0, 100.02, 99.99],
            "ids": {"SystemID": [("uav-001", "u1"), ("uav-001", "u1"), ("uav-002", "u2")]},
            "states": [{"msg": "TaskStatus", "internal": "ACCEPTED", "external": "EXECUTION_PENDING"},
                       {"msg": "FlightCommandStatus", "internal": "EXECUTING", "external": "ACCEPTED"}],
            "routes": [{"route": "r", "sent": [(37.5, 128.0, 500.0), (37.6, 128.1, 510.0)],
                        "bus": [(37.5, 128.0, 500.0), (37.6, 128.1, 510.0)]}]}
    args.update(over)
    return J.judge_c3(**args)


def test_c3_clean_passes():
    r = _good_c3()
    assert r["verdict"] == PASS, r["fail"]


def test_c3_degrees_not_converted_fails():
    r = _good_c3(uci={"lat": 37.5, "lon": 128.0})
    assert r["verdict"] == FAIL and any("위경도" in t for t in r["fail"])


def test_c3_altitude_reference_and_value_fail():
    assert any("MSL이 아닌" in t for t in _good_c3(uci={"ref": "AGL"})["fail"])
    assert any("고도 최대 차" in t for t in _good_c3(uci={"alt": 470.0})["fail"])


def test_c3_velocity_frame_swap_fails():
    r = _good_c3(uci={"vel": (22.0, 1.0, -0.5)})            # 북·동 뒤바뀜
    assert any("NED 속도" in t for t in r["fail"])
    r = _good_c3(uci={"vel": None})                          # 속도가 있는데 빠짐
    assert any("NED 속도" in t for t in r["fail"])


def test_c3_attitude_sign_or_order_fails():
    q = _quat_ypr(0.4, 0.05, -0.1)
    yaw, pitch, roll = J.euler_from_quat_matrix(*q)
    assert any("자세" in t for t in _good_c3(uci={"ypr": (roll, pitch, yaw)})["fail"])   # 순서 XYZ로 착각
    assert any("자세" in t for t in _good_c3(uci={"ypr": (-yaw, pitch, roll)})["fail"])  # ENU식 부호


def test_c3_wall_clock_timestamp_fails():
    r = _good_c3(ts_offsets=[1.79e9 + 0.0, 1.79e9 + 12.0])  # 일시정지만큼 벽시계가 앞서 나감
    assert any("Timestamp" in t for t in r["fail"])
    assert any("Timestamp 대조 0건" in t for t in _good_c3(ts_offsets=[])["fail"])


def test_c3_uuid_inconsistency_fails():
    assert any("UUID 여러 개" in t for t in _good_c3(ids={"SystemID": [("uav-001", "a"), ("uav-001", "b")]})["fail"])
    assert any("DescriptiveLabel 여러 개" in t for t in _good_c3(ids={"TaskID": [("t1", "a"), ("t2", "a")]})["fail"])
    assert any("DescriptiveLabel 없는" in t for t in _good_c3(ids={"TaskID": [("", "a")]})["fail"])


def test_c3_state_map_mismatch_fails():
    r = _good_c3(states=[{"msg": "TaskStatus", "internal": "REJECTED", "external": "FAILED"}])
    assert r["verdict"] == FAIL and any("DEC-090" in t for t in r["fail"])
    r = _good_c3(states=[{"msg": "FlightCommandStatus", "internal": "COMPLETED", "external": "COMPLETED"}])
    assert any("DEC-090" in t for t in r["fail"])            # FCS COMPLETED는 외부 ACCEPTED


def test_c3_route_order_or_points_fail():
    sent = [(37.5, 128.0, 500.0), (37.6, 128.1, 510.0), (37.7, 128.2, 520.0)]
    r = _good_c3(routes=[{"route": "r", "sent": sent, "bus": list(reversed(sent))}])
    assert any("좌표·순서" in t for t in r["fail"])
    r = _good_c3(routes=[{"route": "r", "sent": sent, "bus": sent[:2]}])
    assert any("항로점 수" in t for t in r["fail"])


# ------------------------------------------------------------------------------------------- TC-QA-167 C4

def test_c4_keyexpr_includes():
    assert J.keyexpr_includes("swarm/*/tx/**", "swarm/uav-001/tx/c2/TaskStatus")
    assert J.keyexpr_includes("swarm/*/rx/**", "swarm/*/rx/**")
    assert not J.keyexpr_includes("swarm/*/rx/*/*", "swarm/*/rx/**")
    assert not J.keyexpr_includes("onboard/*/*", "truth/state")
    assert J.keyexpr_includes("sim/clock/done/*", "sim/clock/done/datalink-0")
    assert not J.keyexpr_includes("sim/clock/done/*", "sim/clock/done/a/b")


ALLOWED = {"pub": [{"pattern": "swarm/*/tx/*/*", "src": "t"}, {"pattern": "onboard/*/*", "src": "t"}],
           "sub": [{"pattern": "onboard/*/*", "src": "t"}, {"pattern": "sim/clock/tick", "src": "t"}]}
PROTO = {"swarm.v1.NavigationReport": {"l1": "VI", "mapping": "STD"}, "swarm.v1.TruthState": {"l1": "UNSPECIFIED",
                                                                                             "mapping": "SIM"},
         "swarm.v1.PeerAlgorithmMessage": {"l1": "P2P", "mapping": "EXT"}}


def _c4(**over):  # noqa: ANN003, ANN202
    args = {"subs": ["onboard/*/SystemStatus", "sim/clock/tick"], "puts": ["swarm/uav-001/tx/vi/NavigationReport"],
            "allowed": ALLOWED, "hosted": ["uav-001"], "imports": [{"file": "a.py", "line": 1, "module": "swarm_api",
                                                                    "names": ["MissionAlgorithm"]}],
            "port_msgs": [{"port": "VI", "dir": "MA<-", "msg": "swarm.v1.NavigationReport", "n": 3},
                          {"port": "P2P", "dir": "MA->", "msg": "swarm.v1.PeerAlgorithmMessage", "n": 1}],
            "proto": PROTO}
    args.update(over)
    return J.judge_c4(**args)


def test_c4_clean_passes():
    r = _c4()
    assert r["verdict"] == PASS, r["fail"]


def test_c4_truth_subscription_always_fails():
    r = _c4(subs=["truth/**"], allowed={"pub": ALLOWED["pub"], "sub": [{"pattern": "**", "src": "x"}]})
    assert r["verdict"] == FAIL and any("truth" in t for t in r["fail"])
    r = _c4(rx_keys={"truth/state": 5})
    assert any("truth 키" in t for t in r["fail"])


def test_c4_key_outside_contract_fails():
    assert _c4(subs=["link/outcome/**"])["verdict"] == FAIL
    assert _c4(puts=["sim/ctrl/cmd"])["verdict"] == FAIL


def test_c4_other_entity_fails_wildcard_info():
    r = _c4(puts=["swarm/uav-002/tx/vi/NavigationReport"])
    assert r["verdict"] == FAIL and any("맡지 않은 엔티티 uav-002" in t for t in r["fail"])
    r = _c4(rx_keys={"onboard/gcs-01/SystemStatus": 2})
    assert r["verdict"] == PASS and any("맡지 않은 엔티티 키" in t for t in r["info"])


def test_c4_forbidden_imports_fail():
    for mod, names in (("zenoh", []), ("swarm.v1.truth_pb2", []), ("swarm.v1", ["truth_pb2"]), ("swarm_api", ["open_bus"]),
                       ("swarm_core.x", [])):
        r = _c4(imports=[{"file": "m.py", "line": 3, "module": mod, "names": names}])
        assert r["verdict"] == FAIL, (mod, names)
    r = _c4(imports=[{"file": "m.py", "line": 3, "module": "swarm_agent.geo", "names": ["x"]}])
    assert r["verdict"] == PASS and r["info"]


def test_c4_sim_message_on_port_fails():
    r = _c4(port_msgs=[{"port": "VI", "dir": "MA<-", "msg": "swarm.v1.TruthState", "n": 1}])
    assert r["verdict"] == FAIL and any("SIM" in t for t in r["fail"])


def test_c4_contract_parse_has_agent_rows():
    rows = J.parse_contract_keys((confcommon.ROOT / "docs" / "10_contracts.md").read_text(encoding="utf-8"))
    al = J.agent_allowed(rows)
    pats = {a["pattern"] for a in al["pub"]}
    assert any(p.startswith("swarm/*/tx") for p in pats)
    assert not any(a["pattern"].startswith("truth") for a in al["sub"])


def test_c4_ma_sources_have_no_forbidden_import():
    """실제 algorithms/ 소스: 금지 import 0 (실패하면 결함으로 보고)"""
    r = _c4(imports=static.ma_imports())
    assert not any("버스·truth·Core" in t for t in r["fail"])


# ------------------------------------------------------------------------------------------- TC-QA-168 C5

def _c5(seqs=None, approvals=None, commands=None):  # noqa: ANN001, ANN202
    return J.judge_c5(seqs or {"TaskStatus(내부)": {"u/t": ["ACCEPTED", "EXECUTING", "COMPLETED"]}},
                      approvals or [], commands or [{"entity": "u", "task": "t", "src": "외부", "status_seen": True}])


def test_c5_clean_passes():
    r = _c5(seqs={"TaskStatus(내부)": {"u/t": ["ACCEPTED", "ACCEPTED", "EXECUTING", "COMPLETED"]},
                  "MA_TaskStatus(외부)": {"u/t": ["EXECUTION_PENDING", "EXECUTING", "COMPLETED"]},
                  "FlightCommandStatus(내부)": {"c": ["ACCEPTED", "COMPLETED"]},
                  "MA_FlightCommandStatus(외부)": {"c": ["RECEIVED", "ACCEPTED"]}},   # DEC-097: ACCEPTED는 끝 상태
            approvals=[{"entity": "u", "task": "t", "need": True, "response": "approved", "t_resp": 1.0, "t_exec": 1.2}])
    assert r["verdict"] == PASS, r["fail"]


def test_c5_after_terminal_fails():
    r = _c5(seqs={"FlightCommandStatus(내부)": {"c": ["REJECTED", "EXECUTING"]}})
    assert r["verdict"] == FAIL and "끝 상태 뒤" in r["fail"][0]
    r = _c5(seqs={"TaskStatus(내부)": {"u/t": ["COMPLETED", "EXECUTING"]}})
    assert r["verdict"] == FAIL


def test_c5_transition_outside_table_fails():
    assert _c5(seqs={"TaskStatus(내부)": {"u/t": ["EXECUTING", "ACCEPTED"]}})["verdict"] == FAIL
    assert _c5(seqs={"TaskStatus(내부)": {"u/t": ["CANCELLED"]}})["verdict"] == FAIL          # 첫 보고 취소
    assert _c5(seqs={"MA_TaskStatus(외부)": {"u/t": ["COMPLETED", "EXECUTING"]}})["verdict"] == FAIL


def test_c5_execution_before_approval_fails():
    for ap in ({"response": None, "t_resp": None, "t_exec": 3.0}, {"response": "rejected", "t_resp": 1.0, "t_exec": 3.0},
               {"response": "approved", "t_resp": 5.0, "t_exec": 3.0}):
        r = _c5(approvals=[{"entity": "u", "task": "t", "need": True, **ap}])
        assert r["verdict"] == FAIL, ap
    r = _c5(approvals=[{"entity": "u", "task": "t", "need": True, "response": None, "t_resp": None, "t_exec": None}])
    assert r["verdict"] == PASS                               # 승인 없이 수행하지 않으면 통과(시간 초과)


def test_c5_missing_status_fails():
    r = _c5(commands=[{"entity": "u", "task": "t", "src": "외부 hold", "status_seen": False}])
    assert r["verdict"] == FAIL and "상태 보고 없음" in r["fail"][0]


# ------------------------------------------------------------------------------------------- TC-QA-169 C6

YAML = """server_id: x
services:
  swarm_gateway:
    service: 1
    declared:
      pub: [A@swarm.vi, B@swarm.c2,
            C@swarm.ms]
      sub: [T@swarm.c2]
  external_c2:
    declared:
      pub: [T@swarm.c2]
      sub: [A@swarm.vi]  # 주석
"""


def _graph(pub_counts, sub_names):  # noqa: ANN001, ANN202
    nodes = [{"id": "s1", "kind": "service", "label": "swarm_gateway"}, {"id": "s2", "kind": "service", "label": "external_c2"}]
    edges = []
    for i, (k, n) in enumerate(pub_counts.items()):
        name, top = k.split("@")
        nodes.append({"id": f"t{i}", "kind": "topic", "message_name": name, "topic": top})
        edges.append({"kind": "pub", "source": "s1" if k != "T@swarm.c2" else "s2", "target": f"t{i}", "msg_count": n})
        if k in sub_names:
            edges.append({"kind": "sub", "source": f"t{i}", "target": "s2" if k != "T@swarm.c2" else "s1"})
    return {"nodes": nodes, "edges": edges}


def test_c6_parse_declared_multiline():
    d = J.parse_declared(YAML)
    assert d["swarm_gateway"]["pub"] == {"A@swarm.vi", "B@swarm.c2", "C@swarm.ms"}
    assert d["external_c2"]["sub"] == {"A@swarm.vi"}


def _c6(pub, subs, tap=None, ext=None, inbound=None):  # noqa: ANN001, ANN202
    flows = J.graph_flows(_graph(pub, subs))
    return J.judge_c6(J.parse_declared(YAML), flows, Counter(tap or {"A@swarm.vi": 3}), Counter(ext or {"A@swarm.vi": 3}),
                      inbound or {"MA_TaskCommand": 1})


def test_c6_clean_passes():
    r = _c6({"A@swarm.vi": 3, "B@swarm.c2": 1, "C@swarm.ms": 2, "T@swarm.c2": 1}, {"A@swarm.vi", "T@swarm.c2"})
    assert r["verdict"] == PASS, r["fail"]


def test_c6_declared_but_not_exchanged_fails():
    r = _c6({"A@swarm.vi": 3, "B@swarm.c2": 0, "C@swarm.ms": 2, "T@swarm.c2": 1}, {"A@swarm.vi", "T@swarm.c2"})
    assert any("B@swarm.c2: 선언했지만" in t for t in r["fail"])


def test_c6_undeclared_exchange_fails():
    r = _c6({"A@swarm.vi": 3, "B@swarm.c2": 1, "C@swarm.ms": 2, "T@swarm.c2": 1},
            {"A@swarm.vi", "T@swarm.c2", "C@swarm.ms"})
    assert any("external_c2 sub C@swarm.ms: 선언 밖" in t for t in r["fail"])


def test_c6_tap_count_mismatch_and_inbound_fail():
    ok = {"A@swarm.vi": 3, "B@swarm.c2": 1, "C@swarm.ms": 2, "T@swarm.c2": 1}
    r = _c6(ok, {"A@swarm.vi", "T@swarm.c2"}, tap={"A@swarm.vi": 3}, ext={"A@swarm.vi": 2})
    assert any("/tap A@swarm.vi 3건 ≠ 외부 수신 2건" in t for t in r["fail"])
    r = _c6(ok, {"A@swarm.vi", "T@swarm.c2"}, inbound={"MA_RoutePlan": 0})
    assert any("버스에 나가지 않음" in t for t in r["fail"])


# ------------------------------------------------------------------------------------------- TC-QA-170 C7·발견

def test_c7_info_unless_direct_open():
    assert J.judge_c7([], {"Agent": True}, {}, [], {})["verdict"] == INFO
    assert J.judge_c7(["x.py:3 import zenoh"], {"Agent": True}, {}, [], {})["verdict"] == FAIL
    assert J.judge_c7([], {"Agent": False}, {}, [], {})["verdict"] == FAIL


def test_c7_direct_open_patterns():
    assert static.PY_DIRECT.search("import zenoh\n") and static.PY_DIRECT.search("s = zenoh.open(cfg)")
    assert not static.PY_DIRECT.search("from swarm_api.bus import open_bus")
    assert static.CPP_DIRECT.search("auto s = zenoh::Session::open(std::move(c));")


APP_MD = """# t
## 3. 요약

| 요구 군 | 정의 볼륨 | 계 | 해당 | 부분 | 해당없음 |
|---|---|---|---|---|---|
| `GRA-X` | V | 3 | 1 | 1 | 1 |
| 계 | | 3 | 1 | 1 | 1 |

## 4. 상세

| ID | Tier | 권장 검증 | 정의 볼륨 | 판정 | 요지 | 근거 |
|---|---|---|---|---|---|---|
| GRA-X-001 | 1 | 검사 | V | 해당 | a | `scripts/run.py`가 띄운다(DEC-002, DEC-026). `open_bus` |
| GRA-X-002 | 1 | 검사 | V | 부분 | b | `uv.lock`으로 둔다, 키 `sim/ctrl/status` |
| GRA-X-003 | 1 | 검사 | V | 해당없음 | — | R1 |
"""
FILES = {"scripts/run.py", "uv.lock", "docs/x.md"}
DECS = {"DEC-002", "DEC-026"}


def test_c7_applicability_clean_passes():
    app = static.amsgra_applicability(APP_MD)
    assert [r["verdict"] for r in app["rows"]] == ["해당", "부분", "해당없음"]
    a = J.check_applicability(app, FILES, DECS)
    assert a["fail"] == [] and a["info"] == [] and len(a["rows"]) == 2
    assert a["rows"][0]["paths"] == ["scripts/run.py"] and a["rows"][1]["paths"] == ["uv.lock"]  # 키·식별자는 보지 않음
    assert J.judge_c7([], {"Agent": True}, {}, [], {}, a)["verdict"] == INFO


def test_c7_applicability_missing_basis_fails():
    app = static.amsgra_applicability(APP_MD.replace("scripts/run.py", "scripts/gone.py").replace("DEC-026", "DEC-999"))
    a = J.check_applicability(app, FILES, DECS)
    assert any("scripts/gone.py" in t for t in a["fail"]) and any("DEC-999" in t for t in a["fail"])
    assert J.judge_c7([], {"Agent": True}, {}, [], {}, a)["verdict"] == FAIL
    # 해당없음 행의 근거는 보지 않는다
    app = static.amsgra_applicability(APP_MD.replace("| R1 |", "| `nope/x.py` DEC-998 |"))
    assert J.check_applicability(app, FILES, DECS)["fail"] == []


def test_c7_applicability_summary_mismatch_is_info():
    app = static.amsgra_applicability(APP_MD.replace("| 계 | | 3 | 1 | 1 | 1 |", "| 계 | | 4 | 2 | 1 | 1 |"))
    a = J.check_applicability(app, FILES, DECS)
    assert a["fail"] == [] and a["info"] and "다르다" in a["info"][0]


def test_c7_real_applicability_and_limits_parse():
    md = static.AMSGRA_DOC.read_text(encoding="utf-8")
    app = static.amsgra_applicability(md)
    assert len(app["rows"]) == int(next(s for s in app["summary"] if s[0] == "계")[2])
    lim = static.conformance_limits((confcommon.ROOT / "docs" / "44_standards_conformance.md").read_text(encoding="utf-8"))
    assert any("자체 점검" in t for t in lim) and any("AMS-GRA에는 시험 도구가 없다" in t for t in lim)


def test_strip_numbers_keeps_entity_ids():
    a = "MA_Entity@swarm.p2p: 선언 밖 교환 (117건), uav-007-fmn-beta 36.39 s"
    b = "MA_Entity@swarm.p2p: 선언 밖 교환 (118건), uav-007-fmn-beta 36.24 s"
    assert J.strip_numbers(a) == J.strip_numbers(b) and "uav-007" in J.strip_numbers(a)
    assert J.strip_numbers("uav-007 REJECTED") != J.strip_numbers("uav-008 REJECTED")


def test_findings_unmatched_failure_is_loose():
    fnd, loose = F.attach({"C2": {"fail": ["부정 입력 neg-unknown: 버스로 나감 (k)", "새로운 실패"], "info": []}})
    assert [f["id"] for f in fnd if f["hits"]] == ["D-35"]
    assert loose == [("C2", "새로운 실패")]


# ------------------------------------------------------------------------------------------- TC-QA-171 결과 파일 쓰기

def test_write_json_retries_permission_error(tmp_path, monkeypatch):
    calls = {"n": 0}
    real = os.replace

    def flaky(a, b):  # noqa: ANN001, ANN202
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("읽는 중")
        return real(a, b)
    monkeypatch.setattr(confcommon.os, "replace", flaky)
    p = tmp_path / "ext.json"
    assert confcommon.write_json(p, {"a": 1}, delay=0.001) is True
    assert confcommon.read_json(p) == {"a": 1} and calls["n"] == 3


def test_write_json_gives_up_without_raising(tmp_path, monkeypatch):
    def always(a, b):  # noqa: ANN001, ANN202
        raise PermissionError("잠김")
    monkeypatch.setattr(confcommon.os, "replace", always)
    p = tmp_path / "ext.json"
    assert confcommon.write_json(p, {"a": 1}, retries=3, delay=0.001) is False
    assert not p.exists() and not list(tmp_path.glob("*.tmp"))


def test_read_json_default_on_missing_or_partial(tmp_path):
    assert confcommon.read_json(tmp_path / "none.json", default={"x": 0}, retries=1, delay=0.001) == {"x": 0}
    (tmp_path / "half.json").write_text('{"a": ', encoding="utf-8")
    assert confcommon.read_json(tmp_path / "half.json", default=None, retries=2, delay=0.001) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

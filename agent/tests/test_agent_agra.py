"""TC-AGT-132~137: A-GRA 송신 4종(DEC-088)과 링크 복구 재보고(DEC-089) (IMP-AGT-046~049)"""

from swarm.v1 import c2_pb2, common_pb2, entity_pb2, mp_pb2, ms_pb2, p2p_pb2, vi_pb2
from swarm_agent.geo import offset_geo
from swarm_agent.testing import Harness, make_scenario, send_c2
from swarm_api import keys
from swarm_api.bus import protobuf_encoding

S = common_pb2
ORIGIN = (37.5, 128.0, 1500.0)
A, B, C = "uav-001", "uav-002", "uav-003"
ACC, REJ, CAN = S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_REJECTED, S.COMMAND_STATE_CANCELLED


def of(h, name, eid=None):
    return [m for m in h.gcs_rx if m.DESCRIPTOR.name == name and (eid is None or m.header.source == eid)]


def move(task_id, n=20000.0, e=0.0, *assignees):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=list(assignees) or [A])
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, e)
    t.move_to.destination.lat_deg, t.move_to.destination.lon_deg = float(lat), float(lon)
    return t


def respond(h, request_id, approved, eid=A):
    send_c2(h.bus, "gcs-01", c2_pb2.ApprovalResponse(request_id=request_id, approved=approved), [eid])


def put_onboard(h, eid, msg, lag):
    msg.header.source = eid
    msg.header.frame = h.core.frame - lag        # 이번 틱에 처리될 프레임 (D-30)
    msg.header.sim_time_us = msg.header.frame * h.core.dt_us
    h.bus.put(keys.onboard(eid, msg.DESCRIPTOR.name), msg.SerializeToString(),
              protobuf_encoding(msg.DESCRIPTOR.full_name))


def beat(h, *ids):
    h.datalink.heartbeat("gcs-01", list(ids) or [A], rx_time_us=max(0, h.core.frame - 1) * h.core.dt_us)


def beating(h, seconds, *ids):
    for _ in range(round(seconds)):
        beat(h, *ids)
        h.core.step(50)


# ---- TC-AGT-132~133: 승인 요청 (IMP-AGT-046) ----

def test_tc_agt_132_approval_round_trip():
    h = Harness(make_scenario(1, "waypoint", {"approval_tasks": "move_to, hold"}))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("t1"), [A])
    h.run_s(1.0)
    req = of(h, "ApprovalRequest", A)
    assert len(req) == 1 and req[0].task_id == "t1" and req[0].request_id == f"{A}-approval-1"
    assert req[0].header.correlation_id == "t1" and req[0].description == "move_to t1"
    assert h.task_states("t1") == []                            # 응답 전에는 시작하지 않는다
    assert h.rt.vehicles[A].ma.pilot.tracker.current is None
    respond(h, "unknown-1", True)                               # 모르는 요청은 무시
    h.run_s(0.5)
    assert h.task_states("t1") == []
    respond(h, req[0].request_id, True)
    h.run_s(2.0)
    states = h.task_states("t1")
    assert states[:1] == [ACC] and S.COMMAND_STATE_EXECUTING in states
    assert h.rt.vehicles[A].ma.pilot.tracker.current.task_id == "t1"
    # 거부: REJECTED, 지금 작업은 그대로
    send_c2(h.bus, "gcs-01", move("t2", 0, 20000), [A])
    h.run_s(0.5)
    req2 = of(h, "ApprovalRequest", A)[-1]
    assert req2.task_id == "t2" and req2.request_id == f"{A}-approval-2"
    respond(h, req2.request_id, False)
    h.run_s(0.5)
    st = [m for m in of(h, "TaskStatus") if m.task_id == "t2"]
    assert [m.state for m in st] == [REJ] and st[0].reason == "approval denied"
    assert h.rt.vehicles[A].ma.pilot.tracker.current.task_id == "t1"
    assert CAN not in h.task_states("t1")
    respond(h, req2.request_id, True)                           # 끝난 요청에 다시 온 응답은 무시
    h.run_s(0.5)
    assert [m.state for m in of(h, "TaskStatus") if m.task_id == "t2"] == [REJ]


def test_tc_agt_133_approval_rules():
    # 기본: 승인 없이 바로 수행 (기존 동작)
    h = Harness(make_scenario(1, "waypoint"))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("t1"), [A])
    h.run_s(0.5)
    assert of(h, "ApprovalRequest") == [] and h.task_states("t1")[:1] == [ACC]
    # 목록에 없는 작업은 승인 없이, 시간 제한, 취소, 새 명령이 대기 작업을 밀어냄
    h = Harness(make_scenario(1, "waypoint", {"approval_tasks": "hold", "approval_timeout_s": 2.0}))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("m1"), [A])
    hold = c2_pb2.TaskCommand(task_id="h1", assignees=[A])
    hold.hold.SetInParent()
    h.run_s(0.2)
    send_c2(h.bus, "gcs-01", hold, [A])
    h.run_s(1.0)
    assert h.task_states("m1")[:1] == [ACC] and len(of(h, "ApprovalRequest")) == 1
    assert CAN not in h.task_states("m1")                       # 승인 대기 작업은 지금 작업을 밀어내지 않는다
    h.run_s(1.5)
    st = [m for m in of(h, "TaskStatus") if m.task_id == "h1"]
    assert [m.state for m in st] == [REJ] and st[0].reason == "approval timeout"
    hold.task_id = "h2"
    send_c2(h.bus, "gcs-01", hold, [A])
    h.run_s(0.2)
    cancel = c2_pb2.TaskCommand(task_id="h2", assignees=[A], cancel=True)
    send_c2(h.bus, "gcs-01", cancel, [A])
    h.run_s(0.2)
    assert h.task_states("h2") == [CAN]
    hold.task_id = "h3"
    send_c2(h.bus, "gcs-01", hold, [A])
    h.run_s(0.2)
    send_c2(h.bus, "gcs-01", move("m2"), [A])
    h.run_s(0.2)
    assert h.task_states("h3") == [CAN] and h.task_states("m2")[:1] == [ACC]
    assert [m.reason for m in of(h, "TaskStatus") if m.task_id == "h3"] == ["preempted"]
    # 계획 작업도 시작 전에 승인을 받는다. 일괄 MA(flocking)도 같은 부품
    plan = mp_pb2.MissionPlan(plan_id="p")
    plan.tasks.append(move("p1"))
    h = Harness(make_scenario(2, "flocking", {"approval_tasks": "move_to"}, mission_plan=plan))
    h.run_s(0.5)
    req = of(h, "ApprovalRequest", A)
    assert [r.task_id for r in req] == ["p1"] and h.task_states("p1") == []
    respond(h, req[0].request_id, True)
    h.run_s(0.5)
    assert h.task_states("p1")[:1] == [ACC]
    # 교전 기준 require_approval: 기본 MA가 지원하지 않는 StrikeTask는 그대로 REJECTED (요청 없음)
    sc = make_scenario(1, "waypoint")
    sc.engagement_criteria.require_approval = True
    h = Harness(sc)
    h.core.step(2)
    strike = c2_pb2.TaskCommand(task_id="s1", assignees=[A])
    strike.strike.target_id = "red-1"
    send_c2(h.bus, "gcs-01", strike, [A])
    send_c2(h.bus, "gcs-01", move("t9"), [A])
    h.run_s(0.5)
    assert h.task_states("s1") == [REJ] and of(h, "ApprovalRequest") == [] and h.task_states("t9")[:1] == [ACC]


# ---- TC-AGT-134: 리더 알림 (IMP-AGT-047) ----

def test_tc_agt_134_leader_update():
    h = Harness(make_scenario(3, "formation"))
    h.core.step(2)
    fc = c2_pb2.FormationCommand(group_id="g1", members=[A, B, C], shape=c2_pb2.FORMATION_SHAPE_LINE, spacing_m=100)
    send_c2(h.bus, "gcs-01", fc, [A, B, C])
    h.run_s(0.5)
    lu = of(h, "LeaderUpdate")
    assert [(m.header.source, m.group_id, m.leader, m.term) for m in lu] == [(A, "g1", A, 1)]
    send_c2(h.bus, "gcs-01", fc, [A, B, C])                     # 같은 리더: 다시 보내지 않는다
    h.run_s(0.5)
    assert len(of(h, "LeaderUpdate")) == 1
    fc.leader = B
    send_c2(h.bus, "gcs-01", fc, [A, B, C])
    h.run_s(0.5)
    lu = of(h, "LeaderUpdate")
    assert [(m.header.source, m.leader, m.term) for m in lu] == [(A, A, 1), (B, B, 2)]


def test_tc_agt_134b_leader_update_reaches_peers():
    got = []
    h = Harness(make_scenario(2, "formation"))
    h.bus.subscribe(keys.rx(B, keys.Iface.P2P, "LeaderUpdate"), lambda s: got.append(s.key))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", c2_pb2.FormationCommand(group_id="g", members=[A, B]), [A, B])
    h.run_s(0.5)
    assert got == [keys.rx(B, keys.Iface.P2P, "LeaderUpdate")]


# ---- TC-AGT-135: 탐지 공유 (IMP-AGT-047) ----

def _det(target, n=1000.0, t_kind=entity_pb2.ENTITY_KIND_GROUND_TARGET):
    d = ms_pb2.Detection(payload_id="eo-1", target_id=target, kind=t_kind, range_m=n)
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, 0.0)
    d.position.lat_deg, d.position.lon_deg = float(lat), float(lon)
    d.velocity_ned_mps.x = 3.0
    return d


def test_tc_agt_135_track_share():
    h = Harness(make_scenario(2, "hold", {"track_share_hz": 1.0}))
    h.core.step(3)
    for _ in range(50):                                         # 1 s 동안 매 틱 같은 표적 2개를 본다
        put_onboard(h, A, _det("red-2", 1200.0), 2)
        put_onboard(h, A, _det("red-1"), 2)
        h.core.step(1)
    ts = of(h, "TrackShare", A)
    assert len(ts) == 2 and [m.target_id for m in ts] == ["red-1", "red-2"]   # 주기마다 표적당 한 건, 표적 ID 순
    m = ts[0]
    assert m.track_id == f"{A}/red-1" and m.kind == entity_pb2.ENTITY_KIND_GROUND_TARGET and m.velocity_ned_mps.x == 3.0
    assert m.observed_time_us > 0 and abs(m.position.lat_deg - _det("red-1").position.lat_deg) < 1e-12
    h.run_s(1.0)                                                # 보낸 뒤에 본 탐지는 다음 주기에 한 번
    assert [m.target_id for m in of(h, "TrackShare", A)][2:] == ["red-1", "red-2"]
    h.run_s(2.0)                                                # 새 탐지가 없으면 보내지 않는다
    assert len(of(h, "TrackShare", A)) == 4
    # 기본은 끔
    h = Harness(make_scenario(1, "hold"))
    h.core.step(3)
    put_onboard(h, A, _det("red-1"), 2)
    h.run_s(1.5)
    assert of(h, "TrackShare") == []


# ---- TC-AGT-136: 적재 구성 보고 (IMP-AGT-048) ----

def _with_stores(n=1, count=2):
    sc = make_scenario(n, "hold")
    for e in sc.entities:
        if e.id == A:
            e.payloads.add(id="sta1", type="agm_short", profile="x", count=count)
    return sc


def test_tc_agt_136_store_loadout():
    h = Harness(_with_stores(2))
    h.run_s(1.0)
    lo = of(h, "StoreLoadout")
    assert [(m.header.source, [(s.id, s.count) for s in m.stores]) for m in lo] == [(A, [("sta1", 2)])]  # 적재 없는 B는 없음
    put_onboard(h, A, ms_pb2.StoreLoadout(stores=[entity_pb2.PayloadSpec(id="sta1", type="agm_short", profile="x",
                                                                          count=2)]), 2)
    h.run_s(0.5)
    assert len(of(h, "StoreLoadout")) == 1                     # Payload의 첫 구성이 같으면 다시 보내지 않는다
    # 발사: Payload의 StoreLoadout(잔량 1)과 StrikeActivity가 같은 프레임. 잔량을 두 번 줄이지 않는다
    put_onboard(h, A, ms_pb2.StoreLoadout(stores=[entity_pb2.PayloadSpec(id="sta1", type="agm_short", profile="x",
                                                                          count=1)]), 2)
    put_onboard(h, A, ms_pb2.StrikeActivity(payload_id="sta1", weapon_entity="w1",
                                            state=ms_pb2.STRIKE_STATE_LAUNCHED), 2)
    h.run_s(0.5)
    lo = of(h, "StoreLoadout")
    assert [m.stores[0].count for m in lo] == [2, 1]
    assert h.rt.vehicles[A].ports.ms.loadout().stores[0].count == 1
    assert lo[-1].header.source == A and lo[-1].header.frame > 0
    # Payload 구성이 없으면 런타임이 발사로 줄인 잔량을 보고한다
    h = Harness(_with_stores(1))
    h.run_s(0.5)
    put_onboard(h, A, ms_pb2.StrikeActivity(payload_id="sta1", weapon_entity="w1",
                                            state=ms_pb2.STRIKE_STATE_LAUNCHED), 2)
    h.run_s(0.5)
    assert [m.stores[0].count for m in of(h, "StoreLoadout")] == [2, 1]


# ---- TC-AGT-137: 링크 복구 재보고 (IMP-AGT-049, DEC-089) ----

def _status(h, energy):
    put_onboard(h, A, vi_pb2.SystemStatus(health=vi_pb2.HEALTH_NOMINAL, energy_frac=energy), 1)


def test_tc_agt_137_resend_on_link_recovery():
    h = Harness(_with_stores(1))
    h.core.step(2)
    _status(h, 0.9)
    beating(h, 3)
    base = {n: len(of(h, n, A)) for n in ("SystemStatus", "StoreLoadout", "FlightCapability")}
    assert base == {"SystemStatus": 1, "StoreLoadout": 1, "FlightCapability": 1}
    beating(h, 3)                                               # 평소: 늘지 않는다
    assert {n: len(of(h, n, A)) for n in base} == base
    h.run_s(4.0)                                                # 4 s 공백: 기본 시간 제한 5 s 안이라 복구가 아니다
    beating(h, 2)
    assert {n: len(of(h, n, A)) for n in base} == base
    h.run_s(6.0)                                                # 6 s 공백 → 상실, 다음 Heartbeat에 복구
    beating(h, 3)
    again = {n: len(of(h, n, A)) for n in base}
    assert again == {n: c + 1 for n, c in base.items()}         # 키마다 한 번 더, 그 뒤로는 늘지 않는다
    assert of(h, "SystemStatus", A)[-1].energy_frac == 0.9
    # MA 변수 lost_link_timeout_s를 따른다
    h = Harness(make_scenario(1, "hold", {"lost_link_timeout_s": 1.0}))
    h.core.step(2)
    _status(h, 0.8)
    beating(h, 2)
    h.run_s(2.0)
    beating(h, 1)
    assert len(of(h, "SystemStatus", A)) == 2


def test_tc_agt_137b_deterministic():
    """승인·리더·탐지·적재·복구를 모두 켠 실행 두 번의 GCS 수신이 바이트 단위로 같다 (lockstep)"""
    def run():
        sc = _with_stores(3)
        for e in sc.entities:
            if e.kind == entity_pb2.ENTITY_KIND_UAV:
                e.autonomy.ma_plugin = "formation"
                e.autonomy.ma_params.update({"approval_tasks": "move_to", "track_share_hz": 2.0,
                                             "lost_link_timeout_s": 1.0})
        h = Harness(sc)
        h.core.step(2)
        send_c2(h.bus, "gcs-01", c2_pb2.FormationCommand(group_id="g", members=[A, B, C]), [A, B, C])
        send_c2(h.bus, "gcs-01", move("t1"), [A])
        for i in range(40):
            put_onboard(h, A, _det("red-1", 1000.0 + i), 2)
            if i % 10 == 0:
                beat(h, A, B, C)
            h.core.step(5)
        req = of(h, "ApprovalRequest", A)
        respond(h, req[0].request_id, True)
        h.run_s(3.0)
        beating(h, 2, A, B, C)
        return [m.SerializeToString(deterministic=True) for m in h.gcs_rx]

    a, b = run(), run()
    assert a == b and len(a) > 10

"""TC-AGT-150~157: 기본 MA의 MS 임무 수행 PayloadTasker (IMP-AGT-060, DEC-106, OPN-079)

waypoint(와 formation 리더)가 Track·Jam·Strike를 수행하고 SearchArea·Track·Strike 중 camera를 지향한다.
표적 위치는 자기 Detection(onboard)과 P2P TrackShare로만 준다. 기체 A는 원점(37.5, 128.0, 1500 m)에서 북쪽으로 22 m/s.
"""

import math

from swarm.v1 import c2_pb2, common_pb2, entity_pb2, link_pb2, mp_pb2, ms_pb2, p2p_pb2
from swarm_agent.testing import Harness, make_scenario, send_c2
from swarm_api import keys
from swarm_api.bus import protobuf_encoding
from swarm_api.geo import ned_offset, offset_geo
from swarm_algorithms.common import PAYLOAD_TASK_PARAMS, in_area

S = common_pb2
A, B, C = "uav-001", "uav-002", "uav-003"
ORIGIN = (37.5, 128.0)
ACC, REJ, EXE, DONE, FAIL, CAN = (S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_REJECTED, S.COMMAND_STATE_EXECUTING,
                                  S.COMMAND_STATE_COMPLETED, S.COMMAND_STATE_FAILED, S.COMMAND_STATE_CANCELLED)
RED, BLUE = entity_pb2.SIDE_RED, entity_pb2.SIDE_BLUE
CAM = ("cam0", "camera", 0)
JAM = ("jam0", "jammer", 0)
AGM = ("sta1", "agm_short", 2)


def geo(n, e):
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, e)
    return float(lat), float(lon)


def scenario(stores=(CAM,), params=None, n=1, ma="waypoint", criteria=None):
    sc = make_scenario(n, ma, params or {}, course_deg=0.0)
    for e in sc.entities:
        if e.id == A:
            for sid, typ, cnt in stores:
                e.payloads.add(id=sid, type=typ, profile="x", count=cnt)
    if criteria is not None:
        sc.engagement_criteria.CopyFrom(criteria)
    return sc


class Spy:
    """onboard/<A>/SensorCommand·JammerCommand·StrikeCommand(MA → Payload)를 (frame, 메시지)로 모은다"""

    def __init__(self, h, who=A):
        self.h = h
        self.cmds = []
        for name, cls in (("SensorCommand", ms_pb2.SensorCommand), ("JammerCommand", ms_pb2.JammerCommand),
                          ("StrikeCommand", ms_pb2.StrikeCommand)):
            h.bus.subscribe(keys.onboard(who, name),
                            lambda s, cls=cls: self.cmds.append((self.h.core.frame, cls.FromString(s.payload))))

    def of(self, cls):
        return [m for _, m in self.cmds if isinstance(m, cls)]

    def sensor(self):
        out = []
        for m in self.of(ms_pb2.SensorCommand):
            p = m.pointing.WhichOneof("target")
            out.append((m.payload_id, m.enable, m.pointing.track_entity if p == "track_entity" else p))
        return out

    def jammer(self):
        return [(m.payload_id, m.enable, m.radius_m) for m in self.of(ms_pb2.JammerCommand)]


def start(sc):
    h = Harness(sc)
    spy = Spy(h)
    h.core.step(2)
    return h, spy


def put_onboard(h, msg, who=A):
    msg.header.source = who
    msg.header.frame = h.core.frame - 2
    msg.header.sim_time_us = msg.header.frame * h.core.dt_us
    h.bus.put(keys.onboard(who, msg.DESCRIPTOR.name), msg.SerializeToString(), protobuf_encoding(msg.DESCRIPTOR.full_name))


def detect(h, target, n, e, side=RED, who=A):
    d = ms_pb2.Detection(payload_id="cam0", target_id=target, kind=entity_pb2.ENTITY_KIND_GROUND_TARGET, side=side)
    d.position.lat_deg, d.position.lon_deg = geo(n, e)
    put_onboard(h, d, who)


def share(h, target, n, e, src="uav-009", dst=A):
    """다른 기체가 P2P로 보낸 TrackShare (자기 탐지가 아니다)"""
    ts = p2p_pb2.TrackShare(track_id=f"{src}/{target}", target_id=target, observed_time_us=(h.core.frame - 2) * h.core.dt_us)
    ts.position.lat_deg, ts.position.lon_deg = geo(n, e)
    ts.header.source = src
    env = link_pb2.LinkEnvelope(dst=[dst], iface=6, msg_type=ts.DESCRIPTOR.full_name, payload=ts.SerializeToString())
    env.header.source = src
    h.bus.put(keys.rx(dst, keys.Iface.P2P, "TrackShare"), env.SerializeToString(),
              protobuf_encoding(env.DESCRIPTOR.full_name))


def activity(h, payload, state, reason=""):
    put_onboard(h, ms_pb2.StrikeActivity(payload_id=payload, weapon_entity=f"{A}-w1", state=state, reason=reason))


def task(task_id, kind, **kw):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[A], lost_link_policy=kw.pop("policy", 0))
    if kind == "track":
        t.track.target_id = kw["target"]
    elif kind == "strike":
        t.strike.target_id = kw.get("target", "")
        t.strike.weapon_type = kw.get("weapon", "")
        if "aim" in kw:
            t.strike.aim_point.lat_deg, t.strike.aim_point.lon_deg = geo(*kw["aim"])
    elif kind == "jam":
        t.jam.area.circle.center.lat_deg, t.jam.area.circle.center.lon_deg = geo(*kw["at"])
        t.jam.area.circle.radius_m = kw.get("radius", 800.0)
        t.jam.duration_s = kw.get("duration", 0.0)
    elif kind == "search":
        t.search_area.area.circle.center.lat_deg, t.search_area.area.circle.center.lon_deg = geo(*kw["at"])
        t.search_area.area.circle.radius_m = kw.get("radius", 600.0)
    elif kind == "move":
        t.move_to.destination.lat_deg, t.move_to.destination.lon_deg = geo(*kw["at"])
    return t


def cancel(task_id):
    return c2_pb2.TaskCommand(task_id=task_id, assignees=[A], cancel=True)


def states(h, task_id):
    return [(m.state, m.reason) for m in h.gcs_rx
            if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == task_id and m.header.source == A]


def state_frames(h, task_id):
    return [(m.header.frame, m.state) for m in h.gcs_rx
            if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == task_id and m.header.source == A]


def dist(h, who, n, e):
    b = h.core.bodies[who]
    lat, lon = geo(n, e)
    dn, de = ned_offset(b.lat, b.lon, lat, lon)
    return math.hypot(float(dn), float(de))


def seconds(h, s, each=None):
    """s초 진행. each(h)를 1 s마다 부른다(탐지 1 Hz 모사)"""
    for _ in range(round(s)):
        if each is not None:
            each(h)
        h.core.step(50)


def md(h, name, who=A):
    return [r[2] for r in h.rt.vehicles[who].ports.md.records if r[1] == name]


# ---- TC-AGT-150: 변수 ----

def test_tc_agt_150_params():
    spec = {p.name: p for p in PAYLOAD_TASK_PARAMS}
    assert {k: v.default for k, v in spec.items()} == {"track_standoff_m": 1500.0, "track_acquire_timeout_s": 60.0,
                                                        "track_lost_s": 30.0, "strike_range_m": 3000.0}
    from swarm_algorithms.flocking import Flocking
    from swarm_algorithms.formation import Formation
    from swarm_algorithms.hold import Hold
    from swarm_algorithms.waypoint import WaypointFollower
    for cls in (WaypointFollower, Formation):
        assert set(spec) <= {p.name for p in cls.PARAMS}
    for cls in (Flocking, Hold):                       # flocking·hold에는 넣지 않는다 (DEC-106)
        assert not set(spec) & {p.name for p in cls.PARAMS}


def test_tc_agt_150a_area_and_validation():
    sq = common_pb2.Area()
    for n, e in ((0, 0), (0, 1000), (1000, 1000), (1000, 0)):
        v = sq.polygon.vertices.add()
        v.lat_deg, v.lon_deg = geo(n, e)
    assert in_area(sq, *geo(500, 500)) and not in_area(sq, *geo(500, 1500)) and not in_area(sq, *geo(-10, 500))
    h, _ = start(scenario())
    for t, why in ((task("t1", "track", target=""), "track without target_id"),
                   (task("s1", "strike"), "strike without target"),
                   (task("j1", "jam", at=(0, 0), duration=-1.0), "jam duration_s out of range")):
        send_c2(h.bus, "gcs-01", t, [A])
        h.run_s(0.2)
        assert states(h, t.task_id) == [(REJ, why)]


# ---- TC-AGT-151: Track ----

def test_tc_agt_151_track_orbit_and_follow_moving_target():
    h, spy = start(scenario())
    send_c2(h.bus, "gcs-01", task("t1", "track", target="tgt-1"), [A])
    h.run_s(0.2)
    assert spy.sensor() == [("cam0", True, "tgt-1")]                    # 시작하자마자 표적 지향
    assert states(h, "t1") == [(ACC, "")]                               # 위치를 모르면 EXECUTING 아님(찾는 중)
    seconds(h, 5)
    pos = {"n": 4000.0}
    seconds(h, 200, lambda h: detect(h, "tgt-1", pos["n"], 0.0))
    assert states(h, "t1") == [(ACC, ""), (EXE, "")]
    d = [dist(h, A, 4000.0, 0.0)]
    for _ in range(20):
        seconds(h, 5, lambda h: detect(h, "tgt-1", pos["n"], 0.0))
        d.append(dist(h, A, 4000.0, 0.0))
    assert 1300.0 < min(d) and max(d) < 1700.0                          # 둘레 1500 m 선회
    # 표적이 동쪽으로 움직이면(10 m/s) 선회 중심을 옮긴다
    pos["e"] = 0.0

    def moving(h):
        pos["e"] += 10.0
        detect(h, "tgt-1", pos["n"], pos["e"])

    seconds(h, 300, moving)
    assert 1000.0 < dist(h, A, pos["n"], pos["e"]) < 2100.0
    assert states(h, "t1")[-1] == (EXE, "")                             # 끝나지 않는다
    send_c2(h.bus, "gcs-01", cancel("t1"), [A])
    h.run_s(0.2)
    assert states(h, "t1")[-1] == (CAN, "") and spy.sensor()[-1] == ("cam0", False, None)


def test_tc_agt_151a_track_not_found_and_lost():
    h, spy = start(scenario())
    send_c2(h.bus, "gcs-01", task("t1", "track", target="tgt-1"), [A])
    h.run_s(59.5)
    assert states(h, "t1") == [(ACC, "")]
    h.run_s(1.0)
    assert states(h, "t1") == [(ACC, ""), (FAIL, "target not found")]
    assert spy.sensor() == [("cam0", True, "tgt-1"), ("cam0", False, None)]
    # 한 번 보고 30 s 넘게 갱신이 없으면 놓침
    h2, _ = start(scenario(params={"track_lost_s": 10.0}))
    send_c2(h2.bus, "gcs-01", task("t2", "track", target="tgt-1"), [A])
    h2.run_s(1.0)
    detect(h2, "tgt-1", 3000.0, 0.0)
    h2.run_s(9.5)
    assert states(h2, "t2") == [(ACC, ""), (EXE, "")]
    h2.run_s(1.0)
    assert states(h2, "t2")[-1] == (FAIL, "target lost")
    # 다른 표적의 탐지는 쓰지 않는다
    h3, _ = start(scenario(params={"track_acquire_timeout_s": 5.0}))
    send_c2(h3.bus, "gcs-01", task("t3", "track", target="tgt-1"), [A])
    seconds(h3, 7, lambda h: detect(h, "tgt-2", 3000.0, 0.0))
    assert states(h3, "t3") == [(ACC, ""), (FAIL, "target not found")]


def test_tc_agt_151b_track_share_only_without_camera():
    """camera가 없으면 센서 명령 없이 받은 TrackShare만으로 추적한다 (DEC-013: 자기 탐지·P2P만)"""
    h, spy = start(scenario(stores=()))
    send_c2(h.bus, "gcs-01", task("t1", "track", target="tgt-1"), [A])
    seconds(h, 150, lambda h: share(h, "tgt-1", 3000.0, 2000.0))
    assert states(h, "t1") == [(ACC, ""), (EXE, "")] and spy.cmds == []
    assert 1000.0 < dist(h, A, 3000.0, 2000.0) < 2100.0


# ---- TC-AGT-152: Jam ----

def test_tc_agt_152_jam_on_circle_for_duration():
    h, spy = start(scenario(stores=(CAM, JAM)))
    send_c2(h.bus, "gcs-01", task("j1", "jam", at=(3000.0, 0.0), radius=800.0, duration=60.0), [A])
    h.run_s(30.0)
    assert spy.jammer() == [] and states(h, "j1") == [(ACC, "")]       # 원 밖: 아직 안 켠다
    assert spy.sensor() == []                                           # Jam은 센서를 쓰지 않는다
    h.run_s(150.0)
    (f_on, on), = [(f, m) for f, m in spy.cmds if isinstance(m, ms_pb2.JammerCommand)][:1]
    assert (on.payload_id, on.enable, on.radius_m) == ("jam0", True, 0.0) and on.header.correlation_id == "j1"
    sf = state_frames(h, "j1")
    assert [s for _, s in sf] == [ACC, EXE, DONE]
    assert abs(sf[1][0] - f_on) <= 2                                   # 켤 때 EXECUTING
    assert abs((sf[2][0] - sf[1][0]) * 0.02 - 60.0) < 1.0               # 원 위에서 60 s
    assert spy.jammer() == [("jam0", True, 0.0), ("jam0", False, 0.0)]


def test_tc_agt_152a_jam_until_cancel_preempt_and_no_jammer():
    h, spy = start(scenario(stores=(JAM,)))
    send_c2(h.bus, "gcs-01", task("j1", "jam", at=(3000.0, 0.0)), [A])
    h.run_s(400.0)
    assert states(h, "j1") == [(ACC, ""), (EXE, "")] and spy.jammer() == [("jam0", True, 0.0)]   # duration 0: 유지
    send_c2(h.bus, "gcs-01", cancel("j1"), [A])
    h.run_s(0.2)
    assert states(h, "j1")[-1] == (CAN, "") and spy.jammer()[-1] == ("jam0", False, 0.0)
    # 선점: 다른 작업이 오면 끈다
    send_c2(h.bus, "gcs-01", task("j2", "jam", at=(3000.0, 0.0)), [A])
    h.run_s(200.0)
    assert spy.jammer()[-1] == ("jam0", True, 0.0)
    send_c2(h.bus, "gcs-01", task("m1", "move", at=(0.0, 0.0)), [A])
    h.run_s(0.2)
    assert states(h, "j2")[-1] == (CAN, "preempted") and spy.jammer()[-1] == ("jam0", False, 0.0)
    # jammer가 없으면 실패
    h2, spy2 = start(scenario(stores=(CAM,)))
    send_c2(h2.bus, "gcs-01", task("j3", "jam", at=(3000.0, 0.0)), [A])
    h2.run_s(0.5)
    assert states(h2, "j3") == [(ACC, ""), (FAIL, "no jammer")] and spy2.cmds == []


# ---- TC-AGT-153: Strike ----

def hostile(**kw):
    c = mp_pb2.EngagementCriteria(hostile_sides=[RED], require_approval=kw.get("approval", False))
    for name in ("weapons_free", "no_strike"):
        for n, e, r in kw.get(name, ()):
            a = getattr(c, name).add()
            a.circle.center.lat_deg, a.circle.center.lon_deg = geo(n, e)
            a.circle.radius_m = r
    return c


def strike_run(criteria=None, side=RED, stores=(CAM, AGM), params=None, weapon="agm_short", seconds_=260):
    h, spy = start(scenario(stores=stores, criteria=criteria, params=params))
    send_c2(h.bus, "gcs-01", task("s1", "strike", target="tgt-1", weapon=weapon), [A])
    seconds(h, seconds_, lambda h: detect(h, "tgt-1", 8000.0, 0.0, side))
    return h, spy


def test_tc_agt_153_strike_approach_launch_and_reach():
    h, spy = strike_run(hostile())
    shots = spy.of(ms_pb2.StrikeCommand)
    assert len(shots) == 1
    cmd = shots[0]
    assert (cmd.payload_id, cmd.target_id, cmd.header.correlation_id) == ("sta1", "tgt-1", "s1")
    assert not cmd.HasField("aim_point")
    assert spy.sensor() == [("cam0", True, "tgt-1")]
    assert states(h, "s1") == [(ACC, ""), (EXE, "")]
    assert md(h, "strike_command") == ["s1"]
    activity(h, "sta1", ms_pb2.STRIKE_STATE_LAUNCHED)
    h.run_s(0.5)
    activity(h, "sta1", ms_pb2.STRIKE_STATE_IMPACT)
    h.run_s(0.5)
    assert states(h, "s1") == [(ACC, ""), (EXE, ""), (DONE, "")]
    assert spy.sensor()[-1] == ("cam0", False, None)
    assert len(spy.of(ms_pb2.StrikeCommand)) == 1


def test_tc_agt_153a_launch_distance_and_aim_point():
    h, spy = start(scenario(stores=(AGM,)))
    send_c2(h.bus, "gcs-01", task("s1", "strike", aim=(6000.0, 0.0)), [A])   # 좌표만: 진영 확인 없음
    d = []
    while not spy.of(ms_pb2.StrikeCommand) and h.core.frame < 50 * 400:
        d.append(dist(h, A, 6000.0, 0.0))
        h.core.step(1)
    cmd = spy.of(ms_pb2.StrikeCommand)[0]
    assert cmd.HasField("aim_point") and cmd.target_id == "" and spy.sensor() == []
    assert 2950.0 < d[-1] <= 3000.0 + 22.0 * 0.06                     # 범위에 든 틱에 발사
    assert states(h, "s1") == [(ACC, ""), (EXE, "")]


def test_tc_agt_153b_engagement_criteria_rejects():
    cases = [
        (hostile(), BLUE, "target not hostile"),
        (hostile(no_strike=[(8000.0, 0.0, 500.0)]), RED, "in no strike area"),
        (hostile(weapons_free=[(0.0, 8000.0, 1000.0)]), RED, "outside weapons free"),
    ]
    for crit, side, why in cases:
        h, spy = strike_run(crit, side)
        assert states(h, "s1") == [(ACC, ""), (REJ, why)], why
        assert spy.of(ms_pb2.StrikeCommand) == [] and spy.sensor()[-1] == ("cam0", False, None)
    h, spy = strike_run(hostile(weapons_free=[(8000.0, 0.0, 1000.0)]), RED)   # 허용 구역 안이면 발사
    assert len(spy.of(ms_pb2.StrikeCommand)) == 1
    # 받은 TrackShare뿐이라 진영을 모르면 다가가며 기다리다 거부
    h, spy = start(scenario(stores=(AGM,), criteria=hostile(), params={"track_acquire_timeout_s": 20.0}))
    send_c2(h.bus, "gcs-01", task("s1", "strike", target="tgt-1"), [A])
    seconds(h, 260, lambda h: share(h, "tgt-1", 8000.0, 0.0))
    assert states(h, "s1") == [(ACC, ""), (REJ, "target side unknown")] and spy.of(ms_pb2.StrikeCommand) == []


def test_tc_agt_153c_approval_denied_no_store_missed():
    c2 = c2_pb2
    # 승인 거부: 다가가지도, 발사하지도 않는다 (TaskTracker, DEC-088)
    h, spy = start(scenario(stores=(CAM, AGM), criteria=hostile(approval=True)))
    send_c2(h.bus, "gcs-01", task("s1", "strike", target="tgt-1"), [A])
    h.run_s(1.0)
    req = [m for m in h.gcs_rx if m.DESCRIPTOR.name == "ApprovalRequest"]
    assert [(r.task_id, r.target_id) for r in req] == [("s1", "tgt-1")] and spy.cmds == []
    send_c2(h.bus, "gcs-01", c2.ApprovalResponse(request_id=req[0].request_id, approved=False), [A])
    h.run_s(1.0)
    assert states(h, "s1") == [(REJ, "approval denied")] and spy.cmds == []
    # 승인되면 수행한다
    h, spy = start(scenario(stores=(CAM, AGM), criteria=hostile(approval=True)))
    send_c2(h.bus, "gcs-01", task("s1", "strike", target="tgt-1"), [A])
    h.run_s(1.0)
    rid = next(m for m in h.gcs_rx if m.DESCRIPTOR.name == "ApprovalRequest").request_id
    send_c2(h.bus, "gcs-01", c2.ApprovalResponse(request_id=rid, approved=True), [A])
    seconds(h, 260, lambda h: detect(h, "tgt-1", 8000.0, 0.0))
    assert len(spy.of(ms_pb2.StrikeCommand)) == 1 and states(h, "s1") == [(ACC, ""), (EXE, "")]
    # 잔량 없음
    h, spy = strike_run(hostile(), stores=(CAM, ("sta1", "agm_short", 0)))
    assert states(h, "s1") == [(ACC, ""), (FAIL, "no store")] and spy.of(ms_pb2.StrikeCommand) == []
    # 빗나감·발사 거부
    for st, why in ((ms_pb2.STRIKE_STATE_MISSED, "missed"), (ms_pb2.STRIKE_STATE_REJECTED, "strike rejected: no lock")):
        h, spy = strike_run(hostile())
        activity(h, "sta1", st, "no lock" if st == ms_pb2.STRIKE_STATE_REJECTED else "")
        h.run_s(0.5)
        assert states(h, "s1")[-1] == (FAIL, why)


def test_tc_agt_153d_not_found():
    h, spy = start(scenario(stores=(CAM, AGM), params={"track_acquire_timeout_s": 10.0}))
    send_c2(h.bus, "gcs-01", task("s1", "strike", target="tgt-1"), [A])
    h.run_s(11.0)
    assert states(h, "s1") == [(ACC, ""), (FAIL, "target not found")] and spy.of(ms_pb2.StrikeCommand) == []


# ---- TC-AGT-154: 센서 지향(SearchArea)과 작업 전환 ----

def test_tc_agt_154_search_sensor_and_switch():
    h, spy = start(scenario(stores=(CAM, JAM)))
    send_c2(h.bus, "gcs-01", task("a1", "search", at=(2000.0, 0.0), radius=600.0), [A])
    h.run_s(0.2)
    (cmd,) = spy.of(ms_pb2.SensorCommand)
    c = cmd.pointing.geo_point
    assert cmd.enable and cmd.pointing.WhichOneof("target") == "geo_point"
    assert (c.lat_deg, c.lon_deg) == geo(2000.0, 0.0)
    h.run_s(400.0)
    assert states(h, "a1")[-1] == (DONE, "") and spy.sensor()[-1] == ("cam0", False, None)
    # Track → Jam 선점: 센서를 끄고 원 위에서 재밍
    send_c2(h.bus, "gcs-01", task("t1", "track", target="tgt-1"), [A])
    h.run_s(1.0)
    send_c2(h.bus, "gcs-01", task("j1", "jam", at=(0.0, 3000.0)), [A])
    h.run_s(0.2)
    assert spy.sensor()[-2:] == [("cam0", True, "tgt-1"), ("cam0", False, None)]
    assert states(h, "t1")[-1] == (CAN, "preempted")
    h.run_s(200.0)
    assert spy.jammer() == [("jam0", True, 0.0)]


# ---- TC-AGT-155: 링크 상실 중 ----

def beat(h):
    h.datalink.heartbeat("gcs-01", [A], rx_time_us=max(0, h.core.frame - 1) * h.core.dt_us)


def test_tc_agt_155_lost_link_no_launch_payloads_off_then_resume():
    resume = c2_pb2.LOST_LINK_POLICY_RESUME_ON_RECOVERY
    h, spy = start(scenario(stores=(CAM, AGM)))
    seconds(h, 2, beat)
    send_c2(h.bus, "gcs-01", task("s1", "strike", target="tgt-1", policy=resume), [A])
    h.run_s(10.0)                                                      # 끊김: 5 s 뒤 상실 선회
    assert md(h, "lost_link_action") == ["hold"]
    assert spy.sensor() == [("cam0", True, "tgt-1"), ("cam0", False, None)]   # 선회 중 센서 끔
    seconds(h, 30, lambda h: share(h, "tgt-1", 1000.0, 0.0))           # 범위 안 표적을 알아도
    assert spy.of(ms_pb2.StrikeCommand) == []                          # 상실 선회 중에는 발사하지 않는다
    seconds(h, 7, lambda h: (beat(h), share(h, "tgt-1", 1000.0, 0.0)))  # 복구 확정(5 s) 뒤 재개
    assert md(h, "lost_link_action") == ["hold", "resume"]
    assert spy.sensor()[-1] == ("cam0", True, "tgt-1")                 # 재개하면 다시 켠다
    assert len(spy.of(ms_pb2.StrikeCommand)) == 1


def test_tc_agt_155a_lost_link_jam_off_unless_continue():
    def run(policy):
        h, spy = start(scenario(stores=(JAM,)))
        seconds(h, 2, beat)
        send_c2(h.bus, "gcs-01", task("j1", "jam", at=(0.0, 0.0), radius=600.0, policy=policy), [A])
        seconds(h, 200, beat)
        assert spy.jammer() == [("jam0", True, 0.0)]
        h.run_s(10.0)
        return h, spy

    h, spy = run(c2_pb2.LOST_LINK_POLICY_HOLD_UNTIL_COMMAND)
    assert md(h, "lost_link_action") == ["hold"] and spy.jammer()[-1] == ("jam0", False, 0.0)
    h, spy = run(c2_pb2.LOST_LINK_POLICY_CONTINUE)
    assert md(h, "lost_link_action") == ["continue"] and spy.jammer() == [("jam0", True, 0.0)]
    # 재개하면 원 위에서 다시 켠다
    h, spy = run(c2_pb2.LOST_LINK_POLICY_RESUME_ON_RECOVERY)
    seconds(h, 100, beat)
    assert md(h, "lost_link_action") == ["hold", "resume"]
    assert spy.jammer() == [("jam0", True, 0.0), ("jam0", False, 0.0), ("jam0", True, 0.0)]
    # EXECUTING은 한 번 낸다. 두 번째는 복구 때 런타임이 마지막 상태를 다시 보낸 것(DEC-101(1), 같은 프레임 헤더)
    assert [s for _, s in state_frames(h, "j1")] == [ACC, EXE, EXE] and len(set(state_frames(h, "j1"))) == 2


# ---- TC-AGT-156: formation 리더 Track, 추종기가 따른다 ----

def test_tc_agt_156_formation_leader_tracks_followers_follow():
    h, spy = start(scenario(stores=(CAM,), n=3, ma="formation"))
    fc = c2_pb2.FormationCommand(group_id="g1", members=[A, B, C], leader=A, shape=c2_pb2.FORMATION_SHAPE_LINE,
                                 spacing_m=150.0)
    send_c2(h.bus, "gcs-01", fc, [A, B, C])
    h.run_s(20.0)
    send_c2(h.bus, "gcs-01", task("t1", "track", target="tgt-1"), [A])
    seconds(h, 400, lambda h: detect(h, "tgt-1", 6000.0, 1000.0))
    assert states(h, "t1") == [(ACC, ""), (EXE, "")] and spy.sensor() == [("cam0", True, "tgt-1")]
    assert 1200.0 < dist(h, A, 6000.0, 1000.0) < 1800.0
    for f in (B, C):
        n, e, _ = h.core.offset_m(A, f)
        assert math.hypot(n, e) < 400.0, f                          # 리더 곁에 붙어 있다
        assert 900.0 < dist(h, f, 6000.0, 1000.0) < 2100.0
        err = md(h, "slot_error_m", f)[-60:]
        assert sorted(err)[len(err) // 2] < 150.0, f


# ---- TC-AGT-157: 결정성 ----

def test_tc_agt_157_deterministic():
    def once():
        h, spy = start(scenario(stores=(CAM, JAM, AGM), criteria=hostile()))
        send_c2(h.bus, "gcs-01", task("t1", "track", target="tgt-1"), [A])
        seconds(h, 60, lambda h: detect(h, "tgt-1", 4000.0, 0.0))
        send_c2(h.bus, "gcs-01", task("j1", "jam", at=(4000.0, 0.0), duration=20.0), [A])
        h.run_s(120.0)
        send_c2(h.bus, "gcs-01", task("s1", "strike", target="tgt-1"), [A])
        seconds(h, 60, lambda h: detect(h, "tgt-1", 6000.0, 0.0))
        activity(h, "sta1", ms_pb2.STRIKE_STATE_IMPACT)
        h.run_s(1.0)
        b = h.core.bodies[A]
        return ([m.SerializeToString() for m in h.gcs_rx], [(f, m.SerializeToString()) for f, m in spy.cmds],
                list(h.rt.vehicles[A].ports.md.records), (b.lat, b.lon))

    a, b = once(), once()
    assert a == b
    assert len(a[1]) >= 5

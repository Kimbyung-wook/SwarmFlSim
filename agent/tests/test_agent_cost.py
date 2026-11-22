"""TC-AGT-128~131, 142: 틱 단계별 계측과 총비용 절감 (IMP-AGT-042~045, DEC-086), 기체별 구독 (IMP-AGT-052, DEC-100)"""

import json
import math
import random

import numpy as np

from swarm.v1 import link_pb2, ms_pb2, vi_pb2
from swarm_agent import fa as fa_mod
from swarm_agent.fa import DefaultFlightAutonomy
from swarm_api.geo import course_rad, ned_offset, ned_offset_s, offset_geo, wrap_pi, wrap_pi_s
from swarm_agent.ports import FrameBuffer
from swarm_agent.profiling import ENV, input_class
from swarm_agent.reporting import ChangeReporter, activity_terminal
from swarm_agent.testing import Harness, make_scenario
from swarm_api import Sample, keys

A, B, C = "uav-001", "uav-002", "uav-003"


def _per_key(got, skip=("sim/param/", "sim/ctrl/")):
    """InMemoryBus는 구독자 사이 호출 순서가 정해지지 않으므로 키별 순서로 비교한다. 벽시계 주기 재발행(sim/param)은 뺀다"""
    out = {}
    for k, p in got:
        if not k.startswith(skip):
            out.setdefault(k, []).append(p)
    return out


# ---- TC-AGT-128 계측 (IMP-AGT-042) ----

def test_tc_agt_128_profile_off_by_default_and_phase_split(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert Harness(make_scenario(2, "hold")).rt._prof is None
    out = tmp_path / "prof.json"
    monkeypatch.setenv(ENV, str(out))
    h = Harness(make_scenario(3, "hold"))
    prof = h.rt._prof
    assert prof is not None
    prof.skip, prof.flush_every = 10, 0
    h.core.step(10 + 150)
    h.rt.close()
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["ticks"] == 160 and d["period"] == 50
    s = d["summary"]
    assert s["all"]["frames"] == 150 and s["phase0"]["frames"] == 3 and s["phase4"]["frames"] == 3
    assert s["other"]["frames"] == 144
    for stage in ("tick_total", "fa", "ma", "begin_frame", "report_activity", "publish_controls", "send_done",
                  "in:nav_batch", "in:tick"):
        assert stage in s["all"]["ms_per_frame"], stage
    assert s["all"]["n_per_frame"]["in:nav_batch"] == 1.0 and s["all"]["n_per_frame"]["tick_total"] == 1.0
    # 1 Hz 주기 보고(NavigationReport)는 위상 0 프레임의 보고 송신 수로 센다
    assert s["phase0"]["n_per_frame"]["report_activity"] >= 3
    assert s["other"]["n_per_frame"]["report_activity"] < s["phase0"]["n_per_frame"]["report_activity"]
    assert input_class(keys.onboard(A, "SystemStatus")) == "onboard:SystemStatus"
    assert input_class(keys.rx(A, "c2", "GcsHeartbeat")) == "rx:c2:GcsHeartbeat"


def test_tc_agt_128_profile_does_not_change_outputs(tmp_path, monkeypatch):
    """계측을 켜도 버스에 나가는 내용은 바이트 단위로 같다"""
    def run(with_prof):
        if with_prof:
            monkeypatch.setenv(ENV, str(tmp_path / "p.json"))
        else:
            monkeypatch.delenv(ENV, raising=False)
        h = Harness(make_scenario(3, "hold"))
        got = []
        h.bus.subscribe("**", lambda s: got.append((s.key, s.payload)))
        h.core.step(120)
        return _per_key(got)
    assert run(False) == run(True)


# ---- TC-AGT-129 스칼라 좌표 함수 (IMP-AGT-044) ----

def test_tc_agt_129_scalar_geo_bit_identical():
    rng = np.random.default_rng(3)
    n = 20000
    lat0, lon0 = rng.uniform(-80, 80, n), rng.uniform(-179, 179, n)
    lat, lon = lat0 + rng.normal(0, 0.5, n), lon0 + rng.normal(0, 0.5, n)
    for i in range(n):
        a = tuple(float(x) for x in ned_offset(float(lat0[i]), float(lon0[i]), float(lat[i]), float(lon[i])))
        assert ned_offset_s(float(lat0[i]), float(lon0[i]), float(lat[i]), float(lon[i])) == a
    angles = [*rng.uniform(-40, 40, n), *rng.normal(0, 3, n), math.pi, -math.pi, 0.0, 2 * math.pi, -2 * math.pi, 3 * math.pi]
    for x in angles:
        assert wrap_pi_s(float(x)) == float(wrap_pi(float(x)))
    vn, ve = rng.normal(0, 30, n), rng.normal(0, 30, n)
    for i in range(n):
        assert math.atan2(float(ve[i]), float(vn[i])) == float(course_rad(float(vn[i]), float(ve[i])))


def _commands():
    out = []
    c = vi_pb2.FlightCommand(command_id="w")
    for i, (n, e) in enumerate([(3000, 500), (2000, 4000), (-1500, 2500), (0, 0)]):
        wp = c.waypoint.waypoints.add()
        la, lo = offset_geo(37.5, 128.0, n, e)
        wp.position.lat_deg, wp.position.lon_deg, wp.position.alt_m = float(la), float(lo), 1500 + 100 * i
    out.append(c)
    c = vi_pb2.FlightCommand(command_id="o")
    la, lo = offset_geo(37.5, 128.0, 2000, 1000)
    c.curve.orbit.center.lat_deg, c.curve.orbit.center.lon_deg, c.curve.orbit.radius_m = float(la), float(lo), 800
    out.append(c)
    c = vi_pb2.FlightCommand(command_id="r")
    la, lo = offset_geo(37.5, 128.0, 1500, -1000)
    rt = c.curve.racetrack
    rt.center.lat_deg, rt.center.lon_deg, rt.radius_m, rt.leg_length_m = float(la), float(lo), 700, 2500
    out.append(c)
    return out


def _fly(cmd, steps=3000):
    fa = DefaultFlightAutonomy()
    fa.on_init(A, {})
    fa.on_command(cmd)
    lat, lon, alt, chi, v = 37.5, 128.0, 1450.0, 0.3, 22.0
    out = []
    for _ in range(steps):
        nav = vi_pb2.NavigationReport()
        k = nav.kinematics
        k.position.lat_deg, k.position.lon_deg, k.position.alt_m = lat, lon, alt
        k.velocity_ned_mps.x, k.velocity_ned_mps.y = v * math.cos(chi), v * math.sin(chi)
        o = fa.step(nav, 0.02)
        out.append(o.SerializeToString() + b"|" + b"".join(s.SerializeToString() for s in fa.pending_status()))
        kc = o.kinematic
        chi += kc.heading_rate_rps * 0.02
        v += (kc.speed_mps - v) * 0.05
        alt += kc.climb_rate_mps * 0.02
        la, lo = offset_geo(lat, lon, v * math.cos(chi) * 0.02, v * math.sin(chi) * 0.02)
        lat, lon = float(la), float(lo)
    return out


def test_tc_agt_129_fa_outputs_same_as_numpy_path(monkeypatch):
    """경유점·선회·레이스트랙 폐루프 비행에서 FA 출력이 NumPy 함수를 쓸 때와 바이트 단위로 같다"""
    fast = [_fly(c) for c in _commands()]
    monkeypatch.setattr(fa_mod, "ned_offset_s", lambda *a: tuple(float(x) for x in ned_offset(*a)))
    monkeypatch.setattr(fa_mod, "wrap_pi_s", lambda a: float(wrap_pi(a)))
    ref = [_fly(c) for c in _commands()]
    assert fast == ref


# ---- TC-AGT-130·142 기체별 구독 (IMP-AGT-052, DEC-100. IMP-AGT-043 대체) ----

def test_tc_agt_142_per_vehicle_subscriptions_only():
    """모두 맡든 일부만 맡든 구독은 맡은 기체 키뿐이고 엔티티 자리 와일드카드가 없다"""
    sc = make_scenario(3, "hold")
    for hosted in (None, {A, B, C}, {A, C}):
        rt = Harness(sc, entities=hosted).rt if hosted is not None else Harness(sc).rt
        exprs = [s.keyexpr for s in rt._vehicle_subs]
        mine = set(rt.vehicles)
        assert not [e for e in exprs if e.split("/")[1] == "*"], exprs
        assert {e.split("/")[1] for e in exprs if e.startswith(("swarm/", "onboard/"))} == mine
        assert sum(e.startswith("swarm/") for e in exprs) == len(mine)


def test_tc_agt_142_other_entities_not_delivered():
    """맡지 않은 기체·GCS 앞 수신과 탑재 출력은 Agent 구독에 닿지 않는다 (버스가 아예 건네지 않는다)"""
    h = Harness(make_scenario(3, "hold"), entities={A, B})
    seen = []
    handle = h.rt.handle
    h.rt.handle = lambda s: (seen.append(s.key), handle(s))[1]
    others = [keys.rx("gcs-01", "vi", "NavigationReport"), keys.rx("gcs-01", "c2", "TaskStatus"),
              keys.rx(C, "c2", "GcsHeartbeat"), keys.onboard(C, "SystemStatus"), keys.onboard("gcs-01", "SystemStatus")]
    env = link_pb2.LinkEnvelope(msg_type="swarm.v1.GcsHeartbeat")   # 시험 도구(GCS 수신 기록)도 해석할 수 있는 값
    env.header.source = "gcs-01"
    for k in others:
        h.bus.put(k, env.SerializeToString(), "")
    assert seen == []
    mine = [keys.rx(A, "c2", "GcsHeartbeat"), keys.onboard(B, "SystemStatus")]
    for k in mine:
        h.bus.put(k, b"", "")
    assert seen == mine


def test_tc_agt_130_defensive_drop_kept():
    """구독과 별개로, 맡지 않은 기체·GCS 앞 입력이 handle로 와도 해석·계수 없이 버린다"""
    h = Harness(make_scenario(2, "hold"))
    rt = h.rt
    st = vi_pb2.SystemStatus()
    st.header.source, st.header.frame = "uav-999", 5
    rt.handle(Sample(keys.onboard("uav-999", "SystemStatus"), st.SerializeToString(), ""))
    rt.handle(Sample(keys.onboard("gcs-01", "SystemStatus"), b"\xff\xff", ""))   # 해석하면 예외가 날 바이트
    env = link_pb2.LinkEnvelope(msg_type="swarm.v1.NavigationReport")
    env.header.source = A
    rt.handle(Sample(keys.rx("gcs-01", "vi", "NavigationReport"), env.SerializeToString(), ""))
    rt.handle(Sample(keys.rx("uav-999", "c2", "GcsHeartbeat"), b"\xff", ""))
    assert rt._onboard_hold == {} and rt._rx_hold == {} and rt._rx_count == {}
    assert "uav-999" not in rt.vehicles


# ---- TC-AGT-131 보고·버퍼 빠른 경로 (IMP-AGT-045) ----

class _RefReporter:
    """IMP-AGT-045 전의 ChangeReporter.due (비교 기준)"""

    def __init__(self, terminal):
        self.r = ChangeReporter(terminal)

    def note(self, k, m):
        self.r.note(k, m)

    def due(self, t, gap, period=None):
        r = self.r
        if period is not None and r._period != period:
            r._period = period
            ks = set(r.state)
        else:
            ks = {k for k in r.dirty if k not in r.sent or t - r.sent[k] >= gap}
        out = []
        for k in sorted(ks):
            msg = r.state[k][1]
            out.append(msg)
            r.sent[k] = t
            if r._terminal(k, msg):
                del r.state[k]
        r.dirty -= ks
        for k in [k for k, tt in r.sent.items() if k not in r.state and t - tt >= gap]:
            del r.sent[k]
        return out


def test_tc_agt_131_change_reporter_fast_path_equivalent():
    rnd = random.Random(5)
    for trial in range(30):
        new, ref = ChangeReporter(activity_terminal), _RefReporter(activity_terminal)
        t = 0
        for step in range(400):
            t += 20000
            for _ in range(rnd.choice((0, 0, 0, 1, 2))):
                w = rnd.choice(("w1", "w2", "w3"))
                m = ms_pb2.StrikeActivity(payload_id="p", weapon_entity=w,
                                          state=rnd.choice((ms_pb2.STRIKE_STATE_IMPACT, ms_pb2.STRIKE_STATE_MISSED, 1, 2)))
                k = ("StrikeActivity", "p", w)
                new.note(k, m)
                ref.note(k, m)
            period = t // 1_000_000 if trial % 2 else None
            a = [x.SerializeToString() for x in new.due(t, 100_000, period)]
            b = [x.SerializeToString() for x in ref.due(t, 100_000, period)]
            assert a == b
            assert new.sent == ref.r.sent and set(new.state) == set(ref.r.state) and new.dirty == ref.r.dirty


def test_tc_agt_131_frame_buffer_flip():
    b = FrameBuffer()
    b.flip()
    assert b.take() == [] and b.peek() == []
    b.push(1)
    b.push(2)
    b.flip()
    assert b.peek() == [1, 2]
    b.flip()
    assert b.take() == []
    b.push(3)
    b.flip()
    first = b.take()
    b.flip()
    assert first == [3] and b.take() == []

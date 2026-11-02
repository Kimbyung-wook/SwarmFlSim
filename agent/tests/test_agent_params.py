"""TC-AGT-029~033: 기체별 매개변수 PARAMS·SetParams·EntityParams (IMP-AGT-021~022, DEC-035, REQ-CFG-003)"""

from swarm.v1 import sim_pb2
from swarm_agent.testing import Harness, load_command, make_scenario, put_sim_command
from swarm_api import ParamLayer, keys

UAV = "uav-001"


class Rec:
    """sim/param/** 수신 기록: (키, EntityParams)"""

    def __init__(self, bus) -> None:
        self.msgs: list[tuple[str, sim_pb2.EntityParams]] = []
        self.sub = bus.subscribe(keys.SIM_PARAM_ALL, lambda s: self.msgs.append((s.key, sim_pb2.EntityParams.FromString(s.payload))))

    def last(self, entity: str, owner: str) -> sim_pb2.EntityParams:
        return [m for k, m in self.msgs if k == keys.sim_param(entity, owner)][-1]

    def count(self, entity: str, owner: str) -> int:
        return len([1 for k, _ in self.msgs if k == keys.sim_param(entity, owner)])


def start(sc: sim_pb2.Scenario):
    h = Harness(sc, load=False)
    rec = Rec(h.bus)
    put_sim_command(h.bus, load_command(sc))
    h.run_s(0.2)
    return h, rec


def set_params(h: Harness, entity: str, owner: int, **values) -> None:
    cmd = sim_pb2.SimCommand(issuer="test")
    cmd.set_params.entity_id, cmd.set_params.owner = entity, owner
    cmd.set_params.values.update(values)
    put_sim_command(h.bus, cmd)


def vals(msg: sim_pb2.EntityParams) -> dict:
    return dict(msg.values)


def test_tc_agt_029_defaults_and_published_specs():
    h, rec = start(make_scenario(2, "waypoint"))
    fa, ma = rec.last(UAV, "fa"), rec.last(UAV, "ma")
    assert fa.owner == sim_pb2.PARAM_OWNER_FA and fa.plugin == "default" and fa.entity_id == UAV
    assert ma.owner == sim_pb2.PARAM_OWNER_MA and ma.plugin == "waypoint"
    assert vals(fa)["k_heading"] == 0.8 and vals(fa)["racetrack_guidance"] == "dubins"
    assert vals(ma) == {"acceptance_m": 80.0, "hold_radius_m": 300.0, "speed_mps": 0.0}
    spec = {s.name: s for s in fa.specs}
    assert spec["max_bank_deg"].layer == int(ParamLayer.AIRFRAME) and spec["k_heading"].layer == int(ParamLayer.CONTROL)
    assert spec["racetrack_guidance"].layer == int(ParamLayer.GUIDANCE)
    assert not spec["max_bank_deg"].runtime and spec["k_heading"].runtime
    assert spec["k_heading"].min == 0.0 and spec["k_heading"].max == 10.0 and spec["k_heading"].default_value.number_value == 0.8
    assert {s.name for s in ma.specs} == {"acceptance_m", "hold_radius_m", "speed_mps"}
    assert not fa.rejected and not ma.rejected
    # 기체마다 FA·MA 각각 게시한다
    assert {k for k, _ in rec.msgs} >= {keys.sim_param(u, o) for u in ("uav-001", "uav-002") for o in ("fa", "ma")}
    # 기본값이 플러그인에 전달된다
    assert h.rt.vehicles[UAV].ctx.params["acceptance_m"] == 80.0


def test_tc_agt_030_scenario_override_and_rejection():
    sc = make_scenario(1, "waypoint", {"acceptance_m": 150.0, "bogus": 1.0, "hold_radius_m": 99999999.0})
    sc.entities[1].autonomy.fa_params.update({"k_heading": 1.5, "max_speed_mps": 40.0, "k_altitude": "x"})
    h, rec = start(sc)
    fa, ma = rec.last(UAV, "fa"), rec.last(UAV, "ma")
    assert vals(ma)["acceptance_m"] == 150.0 and vals(ma)["hold_radius_m"] == 300.0  # 범위 밖 → 기본값 유지
    assert {r.name: r.reason for r in ma.rejected} == {"bogus": "unknown", "hold_radius_m": "range"}
    assert vals(fa)["k_heading"] == 1.5 and vals(fa)["max_speed_mps"] == 40.0 and vals(fa)["k_altitude"] == 0.3
    assert {r.name: r.reason for r in fa.rejected} == {"k_altitude": "type"}
    v = h.rt.vehicles[UAV]
    assert v.ctx.params["acceptance_m"] == 150.0 and v.fa.p["k_heading"] == 1.5
    assert v.ma.pilot.acceptance_m == 150.0


def test_tc_agt_031_runtime_change_fa():
    h, rec = start(make_scenario(2, "hold"))
    n0 = rec.count(UAV, "fa")
    set_params(h, UAV, sim_pb2.PARAM_OWNER_FA, k_heading=2.0, racetrack_guidance="vector_field")
    h.run_s(0.1)
    fa = rec.last(UAV, "fa")
    assert vals(fa)["k_heading"] == 2.0 and vals(fa)["racetrack_guidance"] == "vector_field"
    assert not fa.rejected and rec.count(UAV, "fa") > n0
    fa_impl = h.rt.vehicles[UAV].fa
    assert fa_impl.p["k_heading"] == 2.0 and fa_impl.race_guidance == "vector_field"
    # 다른 기체는 그대로
    assert h.rt.vehicles["uav-002"].fa.p["k_heading"] == 0.8


def test_tc_agt_032_runtime_rejection_reasons():
    h, rec = start(make_scenario(1, "hold"))
    set_params(h, UAV, sim_pb2.PARAM_OWNER_FA, max_speed_mps=50.0, k_heading=99.0, k_altitude="x", nope=1.0,
               k_orbit=3.0)
    h.run_s(0.1)
    fa = rec.last(UAV, "fa")
    assert {r.name: r.reason for r in fa.rejected} == {"max_speed_mps": "not_runtime", "k_heading": "range",
                                                        "k_altitude": "type", "nope": "unknown"}
    assert vals(fa)["max_speed_mps"] == 35.0 and vals(fa)["k_heading"] == 0.8
    assert vals(fa)["k_orbit"] == 3.0  # 유효한 항목은 같은 명령에서 적용된다
    # 다음 변경은 거부 목록을 새로 채운다
    set_params(h, UAV, sim_pb2.PARAM_OWNER_FA, k_altitude=0.5)
    h.run_s(0.1)
    assert not rec.last(UAV, "fa").rejected
    # 이 에이전트가 맡지 않은 기체와 Dynamics 소유자는 무시한다
    n = len(rec.msgs)
    set_params(h, "uav-999", sim_pb2.PARAM_OWNER_FA, k_heading=1.0)
    set_params(h, UAV, sim_pb2.PARAM_OWNER_DYNAMICS, k_heading=1.0)
    h.run_s(0.1)
    assert vals(rec.last(UAV, "fa"))["k_heading"] == 0.8


def test_tc_agt_033_runtime_change_ma_and_periodic_publish():
    h, rec = start(make_scenario(1, "waypoint"))
    pilot = h.rt.vehicles[UAV].ma.pilot
    set_params(h, UAV, sim_pb2.PARAM_OWNER_MA, acceptance_m=200.0, speed_mps=25.0, group="x")
    h.run_s(0.1)
    ma = rec.last(UAV, "ma")
    assert vals(ma)["acceptance_m"] == 200.0 and vals(ma)["speed_mps"] == 25.0
    assert {r.name: r.reason for r in ma.rejected} == {"group": "unknown"}
    assert pilot.acceptance_m == 200.0 and pilot.speed_mps == 25.0
    assert h.rt.vehicles[UAV].ctx.params["acceptance_m"] == 200.0
    # 1 s(벽시계)마다 다시 게시한다
    n = rec.count(UAV, "ma")
    h.rt._param_due = 0.0
    h.run_s(0.1)
    assert rec.count(UAV, "ma") > n


def test_tc_agt_033_undeclared_plugin_policy():
    """PARAMS가 없는 플러그인: 시나리오 값은 그대로 전달, 실행 중 변경은 모두 unknown"""
    from swarm_api import MissionAutonomy, AgentContext
    from swarm_agent import PluginRegistry

    class Legacy(MissionAutonomy):
        def on_init(self, ctx: AgentContext) -> None:
            self.seen = dict(ctx.params)

        def on_step(self, ctx: AgentContext) -> None:
            ctx.ports.c2.inbox()

    reg = PluginRegistry(extra_ma={"legacy": Legacy})
    sc = make_scenario(1, "legacy", {"foo": 1.0})
    h = Harness(sc, load=False, registry=reg)
    rec = Rec(h.bus)
    put_sim_command(h.bus, load_command(sc))
    h.run_s(0.2)
    assert h.rt.vehicles[UAV].ma.seen == {"foo": 1.0}
    assert not rec.last(UAV, "ma").specs
    set_params(h, UAV, sim_pb2.PARAM_OWNER_MA, foo=2.0)
    h.run_s(0.1)
    assert {r.name: r.reason for r in rec.last(UAV, "ma").rejected} == {"foo": "unknown"}


def test_tc_agt_034_ma_plugins_declare_params_and_react():
    """4개 MA 모두 PARAMS를 선언하고 on_params로 내부 값을 바꾼다"""
    h, rec = start(make_scenario(2, "flocking"))
    names = {s.name for s in rec.last(UAV, "ma").specs}
    assert {"cruise_mps", "w_sep", "w_align", "w_coh", "group"} <= names
    set_params(h, UAV, sim_pb2.PARAM_OWNER_MA, cruise_mps=30.0, w_sep=3.0)
    h.run_s(0.1)
    ag = h.rt.vehicles[UAV].ma if h.rt.vehicles[UAV].ma is not None else h.rt._batches["flocking"][0]
    assert ag.agents[UAV].p["cruise_mps"] == 30.0 and ag.agents[UAV].p["w_sep"] == 3.0
    assert ag.agents["uav-002"].p["cruise_mps"] == 22.0

    h, rec = start(make_scenario(2, "formation"))
    set_params(h, UAV, sim_pb2.PARAM_OWNER_MA, k_p=0.2, leader_timeout_s=5.0, hold_radius_m=500.0)
    h.run_s(0.1)
    f = h.rt.vehicles[UAV].ma
    assert f.k_p == 0.2 and f.timeout_s == 5.0 and f.pilot.hold_radius_m == 500.0
    assert vals(rec.last(UAV, "ma"))["k_p"] == 0.2

    h, rec = start(make_scenario(1, "hold"))
    ho = h.rt.vehicles[UAV].ma
    assert ho.sent
    set_params(h, UAV, sim_pb2.PARAM_OWNER_MA, orbit_radius_m=500.0)
    h.run_s(0.2)
    assert ho.orbit_radius_m == 500.0 and ho.sent  # 새 값으로 다시 명령했다


def test_tc_agt_035_choices_published_and_rejected():
    """문자열 열거형 racetrack_guidance: ParamSpec.choices 게시, 시나리오·실행 중 잘못된 값은 choice 거부 (DEC-036)"""
    sc = make_scenario(1, "hold")
    sc.entities[1].autonomy.fa_params.update({"racetrack_guidance": "foo"})
    h, rec = start(sc)
    fa = rec.last(UAV, "fa")
    spec = {s.name: s for s in fa.specs}
    assert list(spec["racetrack_guidance"].choices) == ["dubins", "vector_field"]
    assert not spec["k_heading"].choices
    assert {r.name: r.reason for r in fa.rejected} == {"racetrack_guidance": "choice"}
    assert vals(fa)["racetrack_guidance"] == "dubins"  # 거부되면 기본값, on_init 예외 없음
    set_params(h, UAV, sim_pb2.PARAM_OWNER_FA, racetrack_guidance="bar")
    h.run_s(0.1)
    fa = rec.last(UAV, "fa")
    assert {r.name: r.reason for r in fa.rejected} == {"racetrack_guidance": "choice"}
    assert h.rt.vehicles[UAV].fa.race_guidance == "dubins"
    set_params(h, UAV, sim_pb2.PARAM_OWNER_FA, racetrack_guidance="vector_field")
    h.run_s(0.1)
    assert not rec.last(UAV, "fa").rejected and h.rt.vehicles[UAV].fa.race_guidance == "vector_field"

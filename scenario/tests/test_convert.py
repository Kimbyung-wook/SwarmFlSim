import json

import pytest
from google.protobuf.descriptor import FieldDescriptor

from swarm.v1 import c2_pb2, common_pb2, entity_pb2, mp_pb2, sim_pb2
from swarm_scenario import from_dict, from_proto, schema, sim_commands, to_dict, to_proto
from swarm_scenario.enums import full_to_short


# TC-SCN-004: JSON → proto 변환
def test_entities(doc):
    sc = from_dict(doc)
    assert len(sc.entities) == len(doc["entities"])
    gcs = sc.entity("gcs-01")
    assert gcs.kind == entity_pb2.ENTITY_KIND_GCS and gcs.dynamics == entity_pb2.DYNAMICS_KIND_STATIC

    uav = sc.entity("uav-001")
    src = doc["entities"][1]
    assert uav.kind == entity_pb2.ENTITY_KIND_UAV and uav.side == entity_pb2.SIDE_BLUE
    assert uav.dynamics == entity_pb2.DYNAMICS_KIND_DOF2
    assert uav.initial.position.lat_deg == src["initial"]["position"]["lat_deg"]
    assert uav.initial.velocity_ned_mps.x == src["initial"]["velocity_ned_mps"]["x"]
    assert uav.controlling_gcs == "gcs-01"
    assert uav.autonomy.ma_plugin == "flocking_basic"
    assert uav.autonomy.ma_params["group"] == "alpha"
    assert [(p.id, p.type, p.count) for p in uav.payloads] == [("cam0", "camera", 0), ("sta1", "agm_short", 2)]

    fpv = next(p for e in sc.entities for p in e.payloads if p.type == "fpv")
    assert fpv.overrides["max_speed_mps"] == 40.0

    scripted = sc.entity("tgt-004")
    assert scripted.dynamics == entity_pb2.DYNAMICS_KIND_SCRIPTED and len(scripted.script_path) == 3


def test_run_and_map(doc):
    sc = from_dict(doc)
    assert sc.start == sim_pb2.Start(mode=sim_pb2.RUN_MODE_LOCKSTEP, rate=10.0, frame_hz=50, seed=20261101)
    assert sc.duration_s == 1800.0
    assert sc.origin == common_pb2.Geodetic(lat_deg=37.37, lon_deg=128.39, alt_m=500.0)
    assert sc.extent.south_deg == 37.0

    del doc["run"]["rate"]
    assert from_dict(doc).start.rate == 1.0


def test_mission_and_engagement(doc):
    sc = from_dict(doc)
    plan = sc.mission_plan
    assert plan.plan_id == "plan-001"
    assert [t.WhichOneof("task") for t in plan.tasks] == ["search_area", "move_to", "strike", "jam"]
    assert len(plan.tasks[0].search_area.area.polygon.vertices) == 4
    assert plan.tasks[1].move_to.HasField("speed_mps")
    assert plan.tasks[2].strike.weapon_type == "agm_short"
    assert plan.formations[0].shape == c2_pb2.FORMATION_SHAPE_WEDGE
    assert len(plan.formations[0].members) == 10

    ec = sc.engagement_criteria
    assert list(ec.hostile_sides) == [entity_pb2.SIDE_RED]
    assert ec.require_approval
    assert ec.no_strike[0].WhichOneof("shape") == "circle"

    del doc["mission_plan"], doc["engagement_criteria"]
    sc = from_dict(doc)
    assert sc.mission_plan is None and sc.engagement_criteria is None


# TC-SCN-005: proto → JSON 역변환 (GUI ⇄ 파일 같은 형식, REQ-CFG-002)
def test_round_trip(doc):
    sc = from_dict(doc)
    again = from_dict(json.loads(json.dumps(to_dict(sc))))
    assert again.entities == sc.entities
    assert again.mission_plan == sc.mission_plan
    assert again.engagement_criteria == sc.engagement_criteria
    assert again.start == sc.start and again.origin == sc.origin and again.extent == sc.extent


def test_gui_edit_round_trip(doc):
    """GUI가 proto를 고쳐도 JSON으로 저장·재적재된다"""
    sc = from_dict(doc)
    sc.entity("uav-003").initial.position.alt_m = 2000.0
    sc.entities.append(entity_pb2.EntitySpec(
        id="tgt-005", kind=entity_pb2.ENTITY_KIND_GROUND_TARGET, side=entity_pb2.SIDE_RED,
        dynamics=entity_pb2.DYNAMICS_KIND_STATIC,
        initial=entity_pb2.KinematicState(position=common_pb2.Geodetic(lat_deg=37.9, lon_deg=128.9))))
    out = to_dict(sc)
    assert out["entities"][-1]["kind"] == "ground_target"
    assert from_dict(out).entity("uav-003").initial.position.alt_m == 2000.0


def test_to_dict_rejects_invalid(doc):
    sc = from_dict(doc)
    sc.entities[1].id = "bad id"
    with pytest.raises(ValueError):
        to_dict(sc)


# TC-SCN-006: sim/ctrl/cmd 명령 생성
def test_sim_commands(doc):
    load, start = sim_commands(doc, issuer="ui-01")
    assert load.issuer == "ui-01" and load.WhichOneof("cmd") == "load"
    assert load.load.scenario_json == ""
    assert to_dict(from_proto(load.load.scenario)) == to_dict(from_dict(doc))
    assert start.WhichOneof("cmd") == "start" and start.start.mode == sim_pb2.RUN_MODE_LOCKSTEP
    assert sim_pb2.SimCommand.FromString(load.SerializeToString()) == load


# TC-SCN-007: 스키마와 proto의 필드·열거값이 어긋나지 않는다
_SCHEMA_TO_PROTO = {
    "Geodetic": common_pb2.Geodetic,
    "Vec3": common_pb2.Vec3,
    "Quaternion": common_pb2.Quaternion,
    "Area": common_pb2.Area,
    "KinematicState": entity_pb2.KinematicState,
    "PayloadSpec": entity_pb2.PayloadSpec,
    "AutonomySpec": entity_pb2.AutonomySpec,
    "EntitySpec": entity_pb2.EntitySpec,
    "MissionPlan": mp_pb2.MissionPlan,
    "EngagementCriteria": mp_pb2.EngagementCriteria,
    "FormationCommand": c2_pb2.FormationCommand,
    "TaskCommand": c2_pb2.TaskCommand,
    "MapSpec": sim_pb2.MapSpec,
    "RunSpec": sim_pb2.RunSpec,
}
_ENUMS = {
    "EntityKind": entity_pb2.EntityKind,
    "Side": entity_pb2.Side,
    "DynamicsKind": entity_pb2.DynamicsKind,
    "RunMode": sim_pb2.RunMode,
    "FormationShape": c2_pb2.FormationShape,
}


@pytest.mark.parametrize("name", sorted(_SCHEMA_TO_PROTO))
def test_schema_fields_match_proto(name):
    props = set(schema()["$defs"][name]["properties"])
    fields = {f.name for f in _SCHEMA_TO_PROTO[name].DESCRIPTOR.fields} - {"header"}
    assert props == fields


@pytest.mark.parametrize("name", sorted(_ENUMS))
def test_schema_enums_match_proto(name):
    desc = _ENUMS[name].DESCRIPTOR
    proto = {full_to_short(desc, v.name) for v in desc.values if v.number != 0}
    assert set(schema()["$defs"][name]["enum"]) == proto


def test_scalar_field_types():
    """스키마의 수 타입이 proto 스칼라 형식과 맞다"""
    defs = schema()["$defs"]
    ints = {FieldDescriptor.TYPE_UINT32, FieldDescriptor.TYPE_UINT64, FieldDescriptor.TYPE_INT32}
    for name, cls in _SCHEMA_TO_PROTO.items():
        for f in cls.DESCRIPTOR.fields:
            prop = defs[name]["properties"].get(f.name, {})
            if f.type in ints:
                assert prop.get("type") == "integer", (name, f.name)
            elif f.type == FieldDescriptor.TYPE_DOUBLE:
                assert prop.get("type") == "number", (name, f.name)


def test_scenario_top_level_matches_proto():
    """TC-SCN-007: 최상위 필드 = swarm.v1.Scenario (DEC-024)"""
    assert set(schema()["properties"]) == {f.name for f in sim_pb2.Scenario.DESCRIPTOR.fields}


# TC-SCN-008: Scenario ⇄ swarm.v1.Scenario 왕복, lockstep 참여자 (DEC-024, DEC-025)
def test_proto_round_trip(doc):
    doc = dict(doc, run=dict(doc["run"], participants=["agent-host-1", "datalink-0"]))
    sc = from_dict(doc)
    msg = to_proto(sc)
    assert list(msg.run.participants) == ["agent-host-1", "datalink-0"]
    assert len(msg.entities) == len(doc["entities"])
    back = sim_pb2.Scenario.FromString(msg.SerializeToString())
    assert to_dict(from_proto(back)) == to_dict(sc)

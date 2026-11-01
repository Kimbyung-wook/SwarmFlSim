import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from swarm_scenario import ScenarioError, check, schema, validate
from swarm_scenario.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _uav(doc: dict, n: int = 1) -> dict:
    return next(e for e in doc["entities"] if e["id"] == f"uav-{n:03d}")


# TC-SCN-001: 스키마 자체와 예제 시나리오가 유효하다
def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(schema())


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.name)
def test_examples_valid(path):
    assert validate(json.loads(path.read_text(encoding="utf-8"))) == []


def test_example_composition(doc):
    kinds = [e["kind"] for e in doc["entities"]]
    assert kinds.count("uav") >= 20 and kinds.count("gcs") == 1 and kinds.count("ground_target") >= 2


# TC-SCN-002: 스키마 위반을 경로와 함께 보고한다
def _drop_name(d): del d["name"]
def _bad_id(d): _uav(d)["id"] = "UAV_1"
def _long_id(d): _uav(d)["id"] = "uav-" + "1" * 40
def _frame_hz(d): d["run"]["frame_hz"] = 30
def _typo(d): _uav(d)["initail"] = _uav(d).pop("initial")
def _kind(d): _uav(d)["kind"] = "helicopter"
def _full_enum(d): _uav(d)["kind"] = "ENTITY_KIND_UAV"
def _weapon_count(d): _uav(d)["payloads"][1].pop("count")
def _scripted(d): next(e for e in d["entities"] if e["dynamics"] == "scripted").pop("script_path")
def _two_tasks(d): d["mission_plan"]["tasks"][0]["hold"] = {}
def _no_task(d): d["mission_plan"]["tasks"][0].pop("search_area")
def _realtime_rate(d): d["run"].update(mode="realtime", rate=2.0)
def _lat(d): _uav(d)["initial"]["position"]["lat_deg"] = 91.0
def _no_entities(d): d["entities"] = []
def _version(d): d["schema_version"] = "9.9"
def _area_both(d):
    a = d["engagement_criteria"]["no_strike"][0]
    a["polygon"] = {"vertices": [a["circle"]["center"]] * 3}


@pytest.mark.parametrize("mutate,path", [
    (_drop_name, ""),
    (_bad_id, "/entities/1/id"),
    (_long_id, "/entities/1/id"),
    (_frame_hz, "/run/frame_hz"),
    (_typo, "/entities/1"),
    (_kind, "/entities/1/kind"),
    (_full_enum, "/entities/1/kind"),
    (_weapon_count, "/entities/1/payloads/1"),
    (_scripted, "/entities/24"),
    (_two_tasks, "/mission_plan/tasks/0"),
    (_no_task, "/mission_plan/tasks/0"),
    (_realtime_rate, "/run/rate"),
    (_lat, "/entities/1/initial/position/lat_deg"),
    (_no_entities, "/entities"),
    (_version, "/schema_version"),
    (_area_both, "/engagement_criteria/no_strike/0"),
], ids=lambda v: getattr(v, "__name__", v))
def test_schema_violations(doc, mutate, path):
    mutate(doc)
    issues = validate(doc)
    assert issues, "위반이 검출되어야 한다"
    assert path in [i.path for i in issues], issues
    with pytest.raises(ScenarioError):
        check(doc)


# TC-SCN-003: 의미 검증 (참조 무결성, 범위)
def _dup_id(d): _uav(d, 2)["id"] = "uav-001"
def _outside(d): _uav(d)["initial"]["position"]["lon_deg"] = 127.0
def _not_korea(d): d["map"]["extent"]["west_deg"] = 120.0
def _origin(d): d["map"]["origin"]["lat_deg"] = 36.5
def _extent_order(d): d["map"]["extent"]["south_deg"] = 38.5
def _gcs_ref(d): _uav(d)["controlling_gcs"] = "uav-002"
def _gcs_missing(d): _uav(d)["controlling_gcs"] = "gcs-09"
def _dup_payload(d): _uav(d)["payloads"][1]["id"] = "cam0"
def _assignee(d): d["mission_plan"]["tasks"][1]["assignees"].append("uav-999")
def _target(d): d["mission_plan"]["tasks"][2]["strike"]["target_id"] = "tgt-999"
def _dup_task(d): d["mission_plan"]["tasks"][1]["task_id"] = "task-001"
def _leader(d): d["mission_plan"]["formations"][0]["leader"] = "uav-020"
def _member(d): d["mission_plan"]["formations"][1]["members"].append("uav-999")
def _script_out(d): next(e for e in d["entities"] if e["dynamics"] == "scripted")["script_path"][1]["lat_deg"] = 39.0
def _custom(d):
    d["mission_plan"]["formations"][0].update(shape="custom", custom_offsets_m=[{"x": 1.0}])


@pytest.mark.parametrize("mutate,path", [
    (_dup_id, "/entities/2/id"),
    (_outside, "/entities/1/initial/position"),
    (_not_korea, "/map/extent"),
    (_origin, "/map/origin"),
    (_extent_order, "/map/extent"),
    (_gcs_ref, "/entities/1/controlling_gcs"),
    (_gcs_missing, "/entities/1/controlling_gcs"),
    (_dup_payload, "/entities/1/payloads/1/id"),
    (_assignee, "/mission_plan/tasks/1/assignees/10"),
    (_target, "/mission_plan/tasks/2/strike/target_id"),
    (_dup_task, "/mission_plan/tasks/1/task_id"),
    (_leader, "/mission_plan/formations/0/leader"),
    (_member, "/mission_plan/formations/1/members/10"),
    (_script_out, "/entities/24/script_path/1"),
    (_custom, "/mission_plan/formations/0/custom_offsets_m"),
], ids=lambda v: getattr(v, "__name__", v))
def test_semantic_violations(doc, mutate, path):
    mutate(doc)
    issues = validate(doc)
    assert path in [i.path for i in issues], issues


def test_cli_validate(tmp_path, doc, capsys):
    good = EXAMPLES / "korea_east_strike_20.json"
    _frame_hz(doc)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    assert main(["validate", str(good)]) == 0
    assert main(["validate", str(good), str(bad)]) == 1
    assert "/run/frame_hz" in capsys.readouterr().out

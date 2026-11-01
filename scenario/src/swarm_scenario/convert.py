"""IMP-SCN-003: 시나리오 JSON ⇄ proto 변환 (REQ-CFG-001/002).

JSON → EntitySpec·MissionPlan·EngagementCriteria·Start, 그리고 역변환.
역변환이 있어 GUI(proto 객체)와 파일(JSON)이 같은 형식을 공유한다.
IMP-SCN-006: Scenario ⇄ swarm.v1.Scenario. Core에는 proto로 보낸다 (DEC-024).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.protobuf import json_format
from google.protobuf.message import Message

from swarm.v1 import common_pb2, entity_pb2, mp_pb2, sim_pb2

from .enums import from_proto_json, full_to_short, short_to_full, to_proto_json
from .validate import check

SCHEMA_VERSION = "0.1"


@dataclass
class MapExtent:
    south_deg: float
    north_deg: float
    west_deg: float
    east_deg: float


@dataclass
class Scenario:
    name: str
    origin: common_pb2.Geodetic
    extent: MapExtent
    start: sim_pb2.Start
    entities: list[entity_pb2.EntitySpec]
    description: str = ""
    duration_s: float | None = None
    participants: list[str] = field(default_factory=list)
    mission_plan: mp_pb2.MissionPlan | None = None
    engagement_criteria: mp_pb2.EngagementCriteria | None = None

    def entity(self, entity_id: str) -> entity_pb2.EntitySpec:
        return next(e for e in self.entities if e.id == entity_id)


def _parse[M: Message](obj: dict[str, Any], msg: M) -> M:
    json_format.ParseDict(to_proto_json(msg.DESCRIPTOR, obj), msg)
    return msg


def _dump(msg: Message) -> dict[str, Any]:
    d = json_format.MessageToDict(msg, preserving_proto_field_name=True)
    return from_proto_json(msg.DESCRIPTOR, d)


_RUN_MODE = sim_pb2.RunMode.DESCRIPTOR


def from_dict(doc: dict[str, Any]) -> Scenario:
    """검증 후 변환한다. 유효하지 않으면 ScenarioError"""
    check(doc)
    run = doc["run"]
    start = sim_pb2.Start(
        mode=sim_pb2.RunMode.Value(short_to_full(_RUN_MODE, run["mode"])),
        rate=float(run.get("rate", 1.0)),
        frame_hz=run["frame_hz"],
        seed=run["seed"],
    )
    return Scenario(
        name=doc["name"],
        description=doc.get("description", ""),
        origin=_parse(doc["map"]["origin"], common_pb2.Geodetic()),
        extent=MapExtent(**doc["map"]["extent"]),
        start=start,
        duration_s=run.get("duration_s"),
        participants=list(run.get("participants", [])),
        entities=[_parse(e, entity_pb2.EntitySpec()) for e in doc["entities"]],
        mission_plan=_parse(doc["mission_plan"], mp_pb2.MissionPlan()) if "mission_plan" in doc else None,
        engagement_criteria=(_parse(doc["engagement_criteria"], mp_pb2.EngagementCriteria())
                             if "engagement_criteria" in doc else None),
    )


def to_dict(sc: Scenario) -> dict[str, Any]:
    """Scenario → 시나리오 JSON 객체. 결과는 스키마를 만족한다"""
    run: dict[str, Any] = {
        "mode": full_to_short(_RUN_MODE, sim_pb2.RunMode.Name(sc.start.mode)),
        "frame_hz": sc.start.frame_hz,
        "seed": sc.start.seed,
        "rate": sc.start.rate,
    }
    if sc.duration_s is not None:
        run["duration_s"] = sc.duration_s
    if sc.participants:
        run["participants"] = list(sc.participants)
    doc: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "name": sc.name}
    if sc.description:
        doc["description"] = sc.description
    doc["map"] = {"origin": _dump(sc.origin), "extent": vars(sc.extent).copy()}
    doc["run"] = run
    doc["entities"] = [_dump(e) for e in sc.entities]
    if sc.mission_plan is not None:
        doc["mission_plan"] = _dump(sc.mission_plan)
    if sc.engagement_criteria is not None:
        doc["engagement_criteria"] = _dump(sc.engagement_criteria)
    check(doc)
    return doc


def load(path: str | Path) -> Scenario:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def to_proto(sc: Scenario) -> sim_pb2.Scenario:
    msg = sim_pb2.Scenario(
        schema_version=SCHEMA_VERSION,
        name=sc.name,
        description=sc.description,
        map=sim_pb2.MapSpec(origin=sc.origin, extent=sim_pb2.MapExtent(**vars(sc.extent))),
        run=sim_pb2.RunSpec(
            mode=sc.start.mode,
            frame_hz=sc.start.frame_hz,
            seed=sc.start.seed,
            rate=sc.start.rate,
            duration_s=sc.duration_s or 0.0,
            participants=sc.participants,
        ),
        entities=sc.entities,
    )
    if sc.mission_plan is not None:
        msg.mission_plan.CopyFrom(sc.mission_plan)
    if sc.engagement_criteria is not None:
        msg.engagement_criteria.CopyFrom(sc.engagement_criteria)
    return msg


def from_proto(msg: sim_pb2.Scenario) -> Scenario:
    run = msg.run
    e = msg.map.extent
    return Scenario(
        name=msg.name,
        description=msg.description,
        origin=common_pb2.Geodetic.FromString(msg.map.origin.SerializeToString()),
        extent=MapExtent(e.south_deg, e.north_deg, e.west_deg, e.east_deg),
        start=sim_pb2.Start(mode=run.mode, rate=run.rate, frame_hz=run.frame_hz, seed=run.seed),
        duration_s=run.duration_s or None,
        participants=list(run.participants),
        entities=list(msg.entities),
        mission_plan=msg.mission_plan if msg.HasField("mission_plan") else None,
        engagement_criteria=msg.engagement_criteria if msg.HasField("engagement_criteria") else None,
    )


def sim_commands(doc: dict[str, Any], issuer: str) -> list[sim_pb2.SimCommand]:
    """Core에 보낼 sim/ctrl/cmd 순서: LoadScenario → Start"""
    sc = from_dict(doc)
    return [
        sim_pb2.SimCommand(issuer=issuer, load=sim_pb2.LoadScenario(scenario=to_proto(sc))),
        sim_pb2.SimCommand(issuer=issuer, start=sc.start),
    ]

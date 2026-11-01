"""IMP-SCN-002: 시나리오 검증기. JSON Schema 검증 후 의미 검증을 한다 (REQ-CFG-002, PRP-CFG-001)."""

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

# DEC-016: 한반도 전역 (제주 남단 ~ 함경북도 북단, 서해 ~ 독도)
KOREA_BOUNDS = {"south_deg": 33.0, "north_deg": 43.1, "west_deg": 124.0, "east_deg": 131.9}


@dataclass(frozen=True)
class Issue:
    path: str  # JSON Pointer (예: /entities/3/id)
    message: str

    def __str__(self) -> str:
        return f"{self.path or '/'}: {self.message}"


class ScenarioError(ValueError):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("invalid scenario:\n" + "\n".join(f"  {i}" for i in issues))


@cache
def schema() -> dict[str, Any]:
    text = resources.files("swarm_scenario").joinpath("schema/scenario.schema.json").read_text(encoding="utf-8")
    return json.loads(text)


@cache
def _validator() -> Draft202012Validator:
    Draft202012Validator.check_schema(schema())
    return Draft202012Validator(schema())


def _pointer(parts) -> str:
    return "".join(f"/{p}" for p in parts)


def _inside(extent: dict[str, float], pos: dict[str, Any]) -> bool:
    return (extent["south_deg"] <= pos["lat_deg"] <= extent["north_deg"]
            and extent["west_deg"] <= pos["lon_deg"] <= extent["east_deg"])


def _semantic(doc: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    extent = doc["map"]["extent"]

    if not (extent["south_deg"] < extent["north_deg"] and extent["west_deg"] < extent["east_deg"]):
        issues.append(Issue("/map/extent", "south < north, west < east 이어야 한다"))
    if not (KOREA_BOUNDS["south_deg"] <= extent["south_deg"] and extent["north_deg"] <= KOREA_BOUNDS["north_deg"]
            and KOREA_BOUNDS["west_deg"] <= extent["west_deg"] and extent["east_deg"] <= KOREA_BOUNDS["east_deg"]):
        issues.append(Issue("/map/extent", f"한반도 범위 {KOREA_BOUNDS} 밖이다 (DEC-016)"))
    if not _inside(extent, doc["map"]["origin"]):
        issues.append(Issue("/map/origin", "맵 범위 밖이다"))

    kinds: dict[str, str] = {}
    for i, ent in enumerate(doc["entities"]):
        base = f"/entities/{i}"
        if ent["id"] in kinds:
            issues.append(Issue(f"{base}/id", f"중복 ID {ent['id']!r}"))
        kinds.setdefault(ent["id"], ent["kind"])
        if not _inside(extent, ent["initial"]["position"]):
            issues.append(Issue(f"{base}/initial/position", "맵 범위 밖이다"))
        for j, p in enumerate(ent.get("script_path", [])):
            if not _inside(extent, p):
                issues.append(Issue(f"{base}/script_path/{j}", "맵 범위 밖이다"))
        seen: set[str] = set()
        for j, pl in enumerate(ent.get("payloads", [])):
            if pl["id"] in seen:
                issues.append(Issue(f"{base}/payloads/{j}/id", f"기체 안에서 중복 {pl['id']!r}"))
            seen.add(pl["id"])

    for i, ent in enumerate(doc["entities"]):
        gcs = ent.get("controlling_gcs")
        if gcs is not None and kinds.get(gcs) != "gcs":
            issues.append(Issue(f"/entities/{i}/controlling_gcs", f"GCS 엔티티 {gcs!r}가 없다"))

    def check_ref(path: str, eid: str) -> None:
        if eid not in kinds:
            issues.append(Issue(path, f"없는 엔티티 {eid!r}"))

    plan = doc.get("mission_plan", {})
    task_ids: set[str] = set()
    for i, task in enumerate(plan.get("tasks", [])):
        base = f"/mission_plan/tasks/{i}"
        if task["task_id"] in task_ids:
            issues.append(Issue(f"{base}/task_id", f"중복 task_id {task['task_id']!r}"))
        task_ids.add(task["task_id"])
        for j, a in enumerate(task["assignees"]):
            check_ref(f"{base}/assignees/{j}", a)
        for kind in ("track", "strike"):
            if kind in task:
                check_ref(f"{base}/{kind}/target_id", task[kind]["target_id"])

    for i, form in enumerate(plan.get("formations", [])):
        base = f"/mission_plan/formations/{i}"
        for j, m in enumerate(form["members"]):
            check_ref(f"{base}/members/{j}", m)
        if "leader" in form and form["leader"] not in form["members"]:
            issues.append(Issue(f"{base}/leader", "leader는 members에 있어야 한다"))
        if form["shape"] == "custom" and len(form["custom_offsets_m"]) != len(form["members"]):
            issues.append(Issue(f"{base}/custom_offsets_m", "members와 개수가 같아야 한다"))

    return issues


def validate(doc: Any) -> list[Issue]:
    """문제 목록을 돌려준다. 비어 있으면 유효하다."""
    errors = sorted(_validator().iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))
    issues = [Issue(_pointer(e.absolute_path), e.message) for e in errors]
    if issues:
        return issues  # 구조가 틀리면 의미 검증을 하지 않는다
    return _semantic(doc)


def check(doc: Any) -> None:
    issues = validate(doc)
    if issues:
        raise ScenarioError(issues)

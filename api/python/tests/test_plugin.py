"""TC-API-006: 매개변수 선언·해석 (DEC-035)"""

from swarm_api import ParamDef, ParamLayer, resolve_params

DEFS = (
    ParamDef("k_orbit", 2.0, ParamLayer.GUIDANCE, min=0.0, max=10.0),
    ParamDef("racetrack_guidance", "dubins", ParamLayer.GUIDANCE),
    ParamDef("max_bank_deg", 35.0, ParamLayer.AIRFRAME, unit="deg", runtime=False),
    ParamDef("avoid", True, ParamLayer.BEHAVIOR),
)


def test_defaults_and_overrides():
    values, rejected = resolve_params(DEFS, {}, {"k_orbit": 3, "avoid": False})
    assert values == {"k_orbit": 3.0, "racetrack_guidance": "dubins", "max_bank_deg": 35.0, "avoid": False}
    assert rejected == {}


def test_rejections_keep_previous_value():
    base, _ = resolve_params(DEFS, {}, {"k_orbit": 4.0})
    values, rejected = resolve_params(
        DEFS, base,
        {"k_orbit": 11.0, "racetrack_guidance": 1, "max_bank_deg": 40.0, "avoid": 1, "nope": 1.0},
        running=True,
    )
    assert rejected == {"k_orbit": "range", "racetrack_guidance": "type", "max_bank_deg": "not_runtime",
                        "avoid": "type", "nope": "unknown"}
    assert values == base


def test_not_runtime_allowed_at_load():
    values, rejected = resolve_params(DEFS, {}, {"max_bank_deg": 40.0})
    assert values["max_bank_deg"] == 40.0 and not rejected

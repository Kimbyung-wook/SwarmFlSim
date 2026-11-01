"""TC-API-001: 키 생성과 키 표현식 일치 판정"""

import pytest

from swarm_api import keys
from swarm_api.keys import Iface, keyexpr_matches


def test_builders():
    assert keys.tx("uav-001", Iface.VI, "NavigationReport") == "swarm/uav-001/tx/vi/NavigationReport"
    assert keys.rx("gcs-01", Iface.C2, "TaskStatus") == "swarm/gcs-01/rx/c2/TaskStatus"
    assert keys.onboard("uav-001", "ControlOutput") == "onboard/uav-001/ControlOutput"
    assert keys.link_state("uav-002", "uav-001") == "link/state/uav-001/uav-002"


@pytest.mark.parametrize("bad", ["UAV-001", "uav", "uav/001", "uav-*", "-uav-1", "a" * 30 + "-123"])
def test_invalid_entity_id(bad):
    with pytest.raises(ValueError):
        keys.check_entity_id(bad)


@pytest.mark.parametrize(
    ("expr", "key", "expected"),
    [
        ("swarm/*/tx/**", "swarm/uav-001/tx/vi/FlightCommand", True),
        ("swarm/*/tx/**", "swarm/uav-001/rx/vi/FlightCommand", False),
        ("swarm/uav-001/rx/**", "swarm/uav-001/rx/c2/TaskCommand", True),
        ("swarm/uav-001/rx/**", "swarm/uav-002/rx/c2/TaskCommand", False),
        ("truth/**", "truth/state", True),
        ("truth/**", "truth", True),
        ("sim/clock/tick", "sim/clock/tick", True),
        ("sim/*", "sim/clock/tick", False),
        ("link/outcome/*/gcs-01", "link/outcome/uav-003/gcs-01", True),
    ],
)
def test_keyexpr_matches(expr, key, expected):
    assert keyexpr_matches(expr, key) is expected

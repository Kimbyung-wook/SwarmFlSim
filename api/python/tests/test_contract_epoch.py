"""TC-API-010: 모의 시각 기준 RunSpec.epoch_utc_us (DEC-098, 계약 0.20.0)"""
import swarm_api
from swarm.v1 import sim_pb2


def test_contract_version():
    assert swarm_api.CONTRACT_VERSION == "0.20.0"


def test_epoch_field_roundtrip_and_default():
    sc = sim_pb2.Scenario()
    assert sc.run.epoch_utc_us == 0  # 0 = 비어 있음, Core가 적재 때 채움
    sc.run.epoch_utc_us = 1_767_225_600_000_000  # 2026-01-01T00:00:00Z
    back = sim_pb2.Scenario.FromString(sc.SerializeToString())
    assert back.run.epoch_utc_us == 1_767_225_600_000_000

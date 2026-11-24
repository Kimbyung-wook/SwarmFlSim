"""TC-GW-070~073: 운용자 6016 번호표로 무장·플랫폼 종류 싣기 (IMP-GW-040, DEC-051·DEC-068)

시험의 번호(1001 등)는 형식만 맞춘 시험 값이다. MIL-STD-6016의 실제 번호가 아니다.
"""
import datetime as dt
from pathlib import Path

import pytest
from lxml import etree
from swarm.v1 import entity_pb2

import samples as S
from swarm_gateway.__main__ import build_parser, gateway_config
from swarm_gateway.codes import CodeTable, PlatformCode, StoreCode
from swarm_gateway.gateway import Gateway, GatewayConfig
from swarm_gateway.lacal import schema_path

EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "codes.example.yaml"
TEST_CODES = CodeTable(stores={"agm_short": StoreCode(1001, "GROUND"), "aam_short": StoreCode(1002, "AIR")},
                       platforms={"FPV": PlatformCode(2001, threat="UNMANNED_AIRCRAFT"),
                                  "MISSILE": PlatformCode(2002, "AIR", "AIR_TO_SURFACE_MISSILE")})


@pytest.fixture(scope="module")
def xsd():
    return etree.XMLSchema(etree.parse(str(schema_path())))


def _run(bus, codec, codes: CodeTable, *msgs):
    sent = []
    gw = Gateway(bus, GatewayConfig(S.GCS, scenario_query_attempts=0, codes=codes,
                                    sim_epoch=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)), codec=codec,
                 sink=lambda t, o: sent.append((t, o)))
    gw.start()
    try:
        S.load_scenario(bus)
        for m in msgs:
            S.deliver(bus, m)
        return gw, {name: o[name]["MessageData"] for _, o in sent for name in o}, [o for _, o in sent]
    finally:
        gw.close()


def _loadout():
    m = S.store_loadout()                     # sta1 agm_short x2
    m.stores.add(id="sta2", type="aam_short", count=0)
    m.stores.add(id="cam0", type="camera", count=0)
    m.stores.add(id="fpv1", type="fpv", count=3)   # 번호표에 없는 종류
    return m


def _track(kind):
    m = S.track_share()
    m.kind = kind
    return m


def _check(gw, objs, xsd):
    """XSD 통과, 다시 읽으면 같은 값"""
    for o in objs:
        xml = gw.to_xml(o)
        assert xsd.validate(etree.fromstring(xml)), xsd.error_log
        assert gw.codec.xml_to_json(etree.fromstring(xml)) == o


# ---------------------------------------------------------------- TC-GW-070 번호표 없음 = 그 전과 같다
def test_without_codes_output_is_unchanged(bus, codec, xsd):
    msgs = (_loadout(), _track(entity_pb2.ENTITY_KIND_FPV), _track(entity_pb2.ENTITY_KIND_MISSILE))
    gw, data, objs = _run(bus, codec, CodeTable(), *msgs)
    assert data["StoreLoadoutConfiguration"]["Loadout"] == [
        {"Mnemonic": "sta1:agm_shortx2"}, {"Mnemonic": "sta2:aam_shortx0"},
        {"Mnemonic": "cam0:camerax0"}, {"Mnemonic": "fpv1:fpvx3"}]
    ident = data["MA_Entity"]["Identity"]
    assert set(ident) == {"Standard", "Environment", "IdentityTimestamp"}
    assert ident["Standard"] == [{"StandardIdentity": "UNKNOWN", "Confidence": 50.0}]
    _check(gw, objs, xsd)
    example = CodeTable.load(EXAMPLE)          # 예시 파일은 빈 표: 번호 없음
    assert not example and example == CodeTable()
    _, data2, _ = _run(bus, codec, example, *msgs)
    assert data2 == data


# ---------------------------------------------------------------- TC-GW-071 탑재 Hardpoint
def test_store_codes_add_hardpoints(bus, codec, xsd):
    gw, data, objs = _run(bus, codec, TEST_CODES, _loadout())
    lo = data["StoreLoadoutConfiguration"]["Loadout"]
    assert [x["Mnemonic"] for x in lo] == ["sta1:agm_shortx2", "sta2:aam_shortx0", "cam0:camerax0", "fpv1:fpvx3"]
    mission = {"StoreType": {"StoreType": 1001, "StoreCategory": "GROUND"}, "Mnemonic": "agm_short"}
    assert lo[0]["Hardpoint"] == [{"$type": "StoreLoadoutItemType", "Location": i, "PossibleStore": [{"Mission": mission}]} for i in (1, 2)]
    assert all("Hardpoint" not in x for x in lo[1:])    # 잔량 0, 번호표에 없는 종류
    _check(gw, objs, xsd)


# ---------------------------------------------------------------- TC-GW-072 트랙 Platform
@pytest.mark.parametrize("kind,platform", [
    (entity_pb2.ENTITY_KIND_FPV,
     {"PlatformType": 2001, "PlatformTypeCategory": "AIR", "ThreatType": "UNMANNED_AIRCRAFT", "Confidence": 100.0}),
    (entity_pb2.ENTITY_KIND_MISSILE,
     {"PlatformType": 2002, "PlatformTypeCategory": "AIR", "ThreatType": "AIR_TO_SURFACE_MISSILE", "Confidence": 100.0}),
    (entity_pb2.ENTITY_KIND_UAV, None),                 # 번호표에 없는 종류
])
def test_platform_codes_add_platform_identity(bus, codec, xsd, kind, platform):
    gw, data, objs = _run(bus, codec, TEST_CODES, _track(kind))
    ident = data["MA_Entity"]["Identity"]
    assert ident["Standard"] == [{"StandardIdentity": "UNKNOWN", "Confidence": 50.0}]   # 식별 규칙 그대로
    assert ident["Environment"] == [{"Environment": "AIR", "Confidence": 100.0}]
    assert ident.get("Platform") == ([platform] if platform else None)
    _check(gw, objs, xsd)


def test_platform_without_threat(bus, codec, xsd):
    codes = CodeTable(platforms={"GROUND_TARGET": PlatformCode(7)})
    gw, data, objs = _run(bus, codec, codes, S.track_share())
    assert data["MA_Entity"]["Identity"]["Platform"] == [
        {"PlatformType": 7, "PlatformTypeCategory": "GROUND", "Confidence": 100.0}]
    _check(gw, objs, xsd)


# ---------------------------------------------------------------- TC-GW-073 번호표 읽기·검사
def test_code_table_loading_and_checks(tmp_path, codec):
    f = tmp_path / "codes.yaml"
    f.write_text("stores:\n  agm_short: {store_type: 5, category: GROUND}\n"
                 "platforms:\n  fpv: {platform_type: 6, threat: UNMANNED_AIRCRAFT}\n", encoding="utf-8")
    t = CodeTable.load(f).check(codec)
    assert t.stores == {"agm_short": StoreCode(5, "GROUND")}
    assert t.platforms == {"FPV": PlatformCode(6, "", "UNMANNED_AIRCRAFT")}
    assert CodeTable.load("") == CodeTable() and CodeTable.from_dict(None) == CodeTable()
    for bad in ({"stores": {"x": {"store_type": -1, "category": "AIR"}}},
                {"stores": {"x": {"store_type": 2 ** 32, "category": "AIR"}}},
                {"stores": {"x": {"store_type": "1", "category": "AIR"}}},
                {"stores": {"x": {"store_type": 1}}},
                {"platforms": {"UAV": {"platform_type": 1, "colour": "x"}}},
                {"weapons": {}}):
        with pytest.raises(ValueError):
            CodeTable.from_dict(bad)
    for bad in ({"stores": {"x": {"store_type": 1, "category": "SPACE"}}},       # StoreCategoryEnum에 없음
                {"platforms": {"UAV": {"platform_type": 1, "category": "ORBIT"}}},
                {"platforms": {"UAV": {"platform_type": 1, "threat": "DRONE"}}}):
        with pytest.raises(ValueError):
            CodeTable.from_dict(bad).check(codec)
    args = build_parser().parse_args(["--gcs", "gcs-01", "--codes", str(f)])
    assert gateway_config(args).codes == t
    assert gateway_config(build_parser().parse_args(["--gcs", "gcs-01"])).codes == CodeTable()

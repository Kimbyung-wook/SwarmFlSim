"""P5 페이로드 예제 시나리오 시험 (TC-SCN-012, TC-SCN-013). 근거: DEC-046, DEC-017, DEC-019"""
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from swarm_scenario import validate
from swarm_scenario.cli import main

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "scenario" / "examples" / "p5_payload_demo_5.json"
PROFILES = ROOT / "payload" / "profiles"
ID_MAX = 25  # 무장 ID wpn-<id>-NN이 32자를 넘지 않게 한다 (OPN-040)


@pytest.fixture(scope="module")
def p5() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _by_kind(doc: dict, kind: str) -> list[dict]:
    return [e for e in doc["entities"] if e["kind"] == kind]


def _dist_m(a: dict, b: dict) -> float:
    dn = (a["lat_deg"] - b["lat_deg"]) * 111_320.0
    de = (a["lon_deg"] - b["lon_deg"]) * 111_320.0 * math.cos(math.radians(a["lat_deg"]))
    return math.hypot(dn, de)


# TC-SCN-012: 스키마·의미 검증을 통과하고 P5 구성(고정익 4~6, 표적, 재머, 재정의)을 만족한다
def test_p5_valid_and_composition(p5):
    assert validate(p5) == []
    uavs = _by_kind(p5, "uav")
    assert 4 <= len(uavs) <= 6 and all(u["dynamics"] == "dof2" for u in uavs)
    assert len(_by_kind(p5, "gcs")) == 1
    ground, air = _by_kind(p5, "ground_target"), _by_kind(p5, "air_target")
    assert 2 <= len(ground) <= 3 and len(air) == 1
    assert all(t["dynamics"] == "scripted" for t in ground + air)
    assert len(_by_kind(p5, "jammer_site")) == 1


def test_p5_payload_mix(p5):
    types = {pl["type"] for u in _by_kind(p5, "uav") for pl in u.get("payloads", [])}
    assert {"camera", "aam_short", "agm_short", "fpv"} <= types
    overridden = [pl for e in p5["entities"] for pl in e.get("payloads", []) if "overrides" in pl]
    assert len(overridden) == 1 and overridden[0]["type"] == "camera"


def test_p5_ids_and_profiles(p5):
    assert all(len(e["id"]) <= ID_MAX for e in p5["entities"])
    lib = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in PROFILES.glob("*.json")}
    for e in p5["entities"]:
        for pl in e.get("payloads", []):
            assert pl["profile"] in lib[pl["type"]]["profiles"], (e["id"], pl)
            for k in pl.get("overrides", {}):  # 재정의 키는 프로파일 매개변수여야 한다
                assert k in lib[pl["type"]]["profiles"][pl["profile"]], (e["id"], k)


def test_p5_jammer_covers_route(p5):
    jam = _by_kind(p5, "jammer_site")[0]
    radius = json.loads((PROFILES / "jammer.json").read_text(encoding="utf-8"))["profiles"][
        jam["payloads"][0]["profile"]]["radius_m"]
    # 아군 첫 기체가 초기 속도 방향으로 직진하는 경로가 재머 반경 안을 지난다
    u = _by_kind(p5, "uav")[0]
    p0, v = u["initial"]["position"], u["initial"]["velocity_ned_mps"]
    speed = math.hypot(v["x"], v["y"])
    inside = 0
    for s in range(0, 2400, 10):
        pt = {"lat_deg": p0["lat_deg"] + v["x"] * s / 111_320.0,
              "lon_deg": p0["lon_deg"] + v["y"] * s / (111_320.0 * math.cos(math.radians(p0["lat_deg"])))}
        inside += _dist_m(pt, jam["initial"]["position"]) <= radius
    assert speed > 0 and 0 < inside < 240, "경로의 일부만 덮어야 한다"


# TC-SCN-013: swarm_core가 변환한 .pb를 적재하고 시작해 지정 프레임까지 진행한다
def _core_exe() -> Path | None:
    for build in ("msvc-debug", "msvc-release", "linux-debug", "linux-release", "mingw-debug"):
        for name in ("swarm_core.exe", "swarm_core"):
            p = ROOT / "build" / build / "core" / name
            if p.exists():
                return p
    return shutil.which("swarm_core") and Path(shutil.which("swarm_core"))


def test_p5_core_loads_and_runs(tmp_path):
    exe = _core_exe()
    if exe is None:
        pytest.skip("swarm_core 빌드가 없다")
    pb = tmp_path / "p5.pb"
    assert main(["export", str(EXAMPLE), "--out", str(pb)]) == 0
    r = subprocess.run([str(exe), "--scenario", str(pb), "--bus", "memory", "--autostart", "--mode", "freerun",
                        "--rate", "0", "--frames", "1000"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120, env=os.environ)
    assert r.returncode == 0, r.stderr
    assert "loaded scenario 'p5-payload-demo-5', 11 entities" in r.stderr
    assert "rejected" not in r.stderr
    assert "stopped at frame 1000" in r.stderr

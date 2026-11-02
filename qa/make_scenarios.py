"""QA 시나리오 생성기 (TC-QA-001~). qa/scenarios/*.json 을 만든다.

uv run python qa/make_scenarios.py

시나리오는 서로 성격이 다르다 (docs/21_qa_report.md §2).
- s1 소규모 편대(3-DoF 6대, formation MA)
- s2 20대 군집 + 다수 임무(hold·route·racetrack·recon)
- s3 불완전 링크(손실·지연·사거리·대역폭 프로파일, 먼 기체)
- s4 적/표적 포함 센서·무장 선언(Core는 탐지·무장을 아직 모사하지 않는다)
- s5 2-DoF/3-DoF 혼합 이종 기체(airframe 혼합, flocking)
- s6 부하(50대, 100대)
"""

import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent / "scenarios"
LAT0, LON0 = 37.4, 127.4
M_LAT = 111_320.0


def off(n_m: float, e_m: float, alt: float | None = None, lat0: float = LAT0, lon0: float = LON0) -> dict:
    d = {"lat_deg": round(lat0 + n_m / M_LAT, 7),
         "lon_deg": round(lon0 + e_m / (M_LAT * math.cos(math.radians(lat0))), 7)}
    if alt is not None:
        d["alt_m"] = alt
    return d


def base(name: str, desc: str, mode: str = "lockstep", rate: float = 4.0, seed: int = 20261103,
         extent_m: float = 40_000.0, duration_s: float = 1800.0) -> dict:
    dlat = extent_m / M_LAT
    dlon = extent_m / (M_LAT * math.cos(math.radians(LAT0)))
    return {
        "schema_version": "0.1", "name": name, "description": desc,
        "map": {"origin": {"lat_deg": LAT0, "lon_deg": LON0, "alt_m": 100.0},
                "extent": {"south_deg": LAT0 - dlat, "north_deg": LAT0 + dlat,
                           "west_deg": LON0 - dlon, "east_deg": LON0 + dlon}},
        "run": {"mode": mode, "frame_hz": 50, "seed": seed, "rate": 1.0 if mode == "realtime" else rate,
                "duration_s": duration_s},
        "entities": [gcs()],
    }


def gcs(eid: str = "gcs-01") -> dict:
    return {"id": eid, "kind": "gcs", "side": "blue", "dynamics": "static",
            "initial": {"position": off(0, 0, 100.0)}, "link_profile": "gcs_default"}


def uav(eid: str, n: float, e: float, alt: float = 1200.0, dyn: str = "dof2", airframe: str = "skywalker_x8",
        ma: str = "waypoint", ma_params: dict | None = None, link: str = "uav_default", speed: float = 20.0,
        heading_deg: float = 0.0, fa_params: dict | None = None, payloads: list | None = None,
        side: str = "blue", gcs_id: str = "gcs-01") -> dict:
    hd = math.radians(heading_deg)
    d = {"id": eid, "kind": "uav", "side": side, "dynamics": dyn, "airframe": airframe,
         "initial": {"position": off(n, e, alt),
                     "velocity_ned_mps": {"x": round(speed * math.cos(hd), 3), "y": round(speed * math.sin(hd), 3),
                                          "z": 0.0}},
         "autonomy": {"ma_plugin": ma, "ma_params": ma_params or {"hold_radius_m": 200, "acceptance_m": 80}},
         "link_profile": link, "controlling_gcs": gcs_id}
    if fa_params:
        d["autonomy"]["fa_params"] = fa_params
    if payloads:
        d["payloads"] = payloads
    return d


def ids(prefix: str, a: int, b: int) -> list[str]:
    return [f"{prefix}-{i:03d}" for i in range(a, b + 1)]


def s1_formation6() -> dict:
    sc = base("qa-s1-formation6", "소규모 편대: 3-DoF 6대, formation MA(리더 uav-001, wedge)", rate=4.0)
    members = ids("uav", 1, 6)
    for i, m in enumerate(members):
        sc["entities"].append(uav(m, -300.0, (i - 2.5) * 150.0, dyn="dof3", ma="formation",
                                  ma_params={"group": "alpha", "leader_speed_mps": 20.0}))
    sc["mission_plan"] = {
        "plan_id": "plan-s1",
        "tasks": [{"task_id": "s1-leg1", "assignees": ["uav-001"],
                   "route": {"waypoints": [{"position": off(3000, 0, 1200.0), "acceptance_radius_m": 150.0},
                                           {"position": off(3000, 3000, 1200.0), "acceptance_radius_m": 150.0},
                                           {"position": off(0, 3000, 1200.0), "acceptance_radius_m": 150.0}]}}],
        "formations": [{"group_id": "alpha", "members": members, "leader": "uav-001", "shape": "wedge",
                       "spacing_m": 120.0}],
    }
    return sc


def s2_swarm20() -> dict:
    sc = base("qa-s2-swarm20", "20대 군집 + 임무 4종(hold·route·racetrack·search_area)", rate=4.0)
    for i in range(1, 21):
        sc["entities"].append(uav(f"uav-{i:03d}", -1500.0 + (i - 1) // 10 * 800, ((i - 1) % 10 - 4.5) * 300.0))
    tasks = [
        {"task_id": "s2-hold", "assignees": ids("uav", 1, 5),
         "hold": {"center": off(2500, -1500, 1200.0), "radius_m": 300.0, "direction": "cw"}},
        {"task_id": "s2-route", "assignees": ids("uav", 6, 10),
         "route": {"waypoints": [{"position": off(2000, 1000, 1300.0), "acceptance_radius_m": 150.0},
                                 {"position": off(3000, 2000, 1300.0), "speed_mps": 22.0,
                                  "loiter": {"duration_s": 30.0, "radius_m": 250.0}},
                                 {"position": off(2000, 3000, 1100.0),
                                  "recon": {"radius_m": 400.0, "duration_s": 40.0}}]}},
        {"task_id": "s2-racetrack", "assignees": ids("uav", 11, 15),
         "hold": {"center": off(3500, 0, 1250.0), "radius_m": 300.0,
                  "racetrack": {"leg_length_m": 1200.0, "axis_heading_deg": 90.0}}},
        {"task_id": "s2-recon", "assignees": ids("uav", 16, 20),
         "search_area": {"area": {"circle": {"center": off(1500, 2500), "radius_m": 800.0},
                                  "min_alt_m": 0.0, "max_alt_m": 3000.0}}},
    ]
    sc["mission_plan"] = {"plan_id": "plan-s2", "tasks": tasks}
    return sc


def s3_link() -> dict:
    sc = base("qa-s3-link", "불완전 링크: 손실·지연·짧은 사거리·좁은 대역폭 프로파일과 80 km 밖 기체", rate=2.0)
    sc["link_profiles"] = [
        {"name": "qa_lossy", "base": "uav_default",
         "ge": {"p_gb": 0.2, "p_bg": 0.2, "loss_good": 0.05, "loss_bad": 0.9}},
        {"name": "qa_slow", "base": "uav_default", "latency_ms": 800.0, "jitter_ms": 300.0},
        {"name": "qa_short", "base": "uav_default", "max_range_m": 3000.0},
        {"name": "qa_narrow", "base": "uav_default", "bandwidth_bps": 2000.0, "queue_len": 5},
    ]
    profiles = ["uav_default", "qa_lossy", "qa_slow", "qa_short", "qa_narrow", "uav_default"]
    for i in range(1, 13):
        sc["entities"].append(uav(f"uav-{i:03d}", ((i - 1) // 4) * 500.0 - 500.0, ((i - 1) % 4 - 1.5) * 500.0,
                                  link=profiles[(i - 1) % len(profiles)],
                                  ma="flocking" if i > 8 else "waypoint",
                                  ma_params={} if i > 8 else {"hold_radius_m": 200, "acceptance_m": 80}))
    # 80 km 떨어진 기체: 지도 밖은 아니고 사거리 밖
    far = uav("uav-013", 0.0, 35_000.0)
    sc["entities"].append(far)
    return sc


def s4_engage() -> dict:
    sc = base("qa-s4-engage", "적/표적 + 센서·무장 선언. Core는 탐지·무장을 아직 모사하지 않는다(WP8 미구현)", rate=2.0)
    pay = [{"id": "cam0", "type": "camera"}, {"id": "jam0", "type": "jammer"},
           {"id": "agm0", "type": "agm_short", "count": 2, "overrides": {"max_range_m": 8000.0}},
           {"id": "aam0", "type": "aam_short", "count": 2}]
    for i in range(1, 7):
        sc["entities"].append(uav(f"uav-{i:03d}", -500.0, (i - 3.5) * 300.0, dyn="dof3", payloads=pay))
    sc["entities"] += [
        {"id": "tgt-001", "kind": "ground_target", "side": "red", "dynamics": "static",
         "initial": {"position": off(6000, 0, 120.0)}},
        {"id": "tgt-002", "kind": "ground_target", "side": "red", "dynamics": "scripted",
         "initial": {"position": off(6000, 1000, 120.0), "velocity_ned_mps": {"x": 8.0, "y": 0.0, "z": 0.0}},
         "script_path": [off(6000, 1000, 120.0), off(7000, 1000, 120.0), off(7000, 2500, 120.0)]},
        {"id": "tgt-003", "kind": "air_target", "side": "red", "dynamics": "scripted",
         "initial": {"position": off(5000, -2000, 800.0), "velocity_ned_mps": {"x": 0.0, "y": 25.0, "z": 0.0}},
         "script_path": [off(5000, -2000, 800.0), off(5000, 3000, 800.0)]},
        {"id": "site-01", "kind": "jammer_site", "side": "red", "dynamics": "static",
         "initial": {"position": off(4000, 500, 100.0)}},
        {"id": "wpn-uav-001-01", "kind": "missile", "side": "blue", "dynamics": "scripted",
         "initial": {"position": off(-500, -450, 1200.0)},
         "script_path": [off(-500, -450, 1200.0), off(6000, 0, 130.0)]},
        {"id": "fpv-001", "kind": "fpv", "side": "blue", "dynamics": "dof3", "airframe": "skywalker_x8",
         "initial": {"position": off(-200, 0, 300.0), "velocity_ned_mps": {"x": 18.0, "y": 0.0, "z": 0.0}},
         "autonomy": {"ma_plugin": "hold"}, "link_profile": "fpv_default", "controlling_gcs": "gcs-01"},
    ]
    sc["mission_plan"] = {"plan_id": "plan-s4", "tasks": [
        {"task_id": "s4-search", "assignees": ids("uav", 1, 3),
         "search_area": {"area": {"circle": {"center": off(6000, 500), "radius_m": 1500.0}, "min_alt_m": 0.0,
                                  "max_alt_m": 3000.0}}},
        {"task_id": "s4-strike", "assignees": ["uav-004"], "strike": {"target_id": "tgt-001", "weapon_type": "agm_short"}},
        {"task_id": "s4-jam", "assignees": ["uav-005"],
         "jam": {"area": {"circle": {"center": off(4000, 500), "radius_m": 2000.0}}, "duration_s": 120.0}},
        {"task_id": "s4-track", "assignees": ["uav-006"], "track": {"target_id": "tgt-003"}},
    ]}
    sc["engagement_criteria"] = {
        "hostile_sides": ["red"], "require_approval": True,
        "weapons_free": [{"circle": {"center": off(6000, 500), "radius_m": 8000.0}}],
        "no_strike": [{"circle": {"center": off(7000, 2500), "radius_m": 500.0}}]}
    return sc


def s5_mixed() -> dict:
    sc = base("qa-s5-mixed", "2-DoF/3-DoF 혼합, skywalker_x8/aerosonde 혼합, hold·waypoint·flocking 혼합", rate=4.0)
    mas = ["waypoint", "hold", "flocking", "waypoint"]
    for i in range(1, 17):
        dyn = "dof2" if i % 2 else "dof3"
        af = "skywalker_x8" if i <= 8 else "aerosonde"
        sc["entities"].append(uav(f"uav-{i:03d}", ((i - 1) // 4) * 400.0 - 600.0, ((i - 1) % 4 - 1.5) * 400.0,
                                  dyn=dyn, airframe=af, ma=mas[(i - 1) % 4],
                                  ma_params={} if mas[(i - 1) % 4] == "flocking" else
                                  {"hold_radius_m": 250, "acceptance_m": 80},
                                  speed=20.0 if af == "skywalker_x8" else 24.0))
    sc["mission_plan"] = {"plan_id": "plan-s5", "tasks": [
        {"task_id": "s5-move", "assignees": ids("uav", 1, 4), "move_to": {"destination": off(4000, 2000, 1300.0)}}]}
    return sc


def s6_load(n: int, ma: str = "waypoint") -> dict:
    sc = base(f"qa-s6-load{n}", f"부하 시험: 2/3-DoF 혼합 {n}대, MA={ma}", rate=1.0)
    cols = 10
    for i in range(1, n + 1):
        r, c = divmod(i - 1, cols)
        sc["entities"].append(uav(f"uav-{i:03d}", r * 400.0 - 1000.0, (c - 4.5) * 400.0,
                                  alt=1000.0 + (i % 5) * 50.0, dyn="dof2" if i % 2 else "dof3", ma=ma,
                                  ma_params={} if ma == "flocking" else {"hold_radius_m": 200, "acceptance_m": 80}))
    return sc


def main() -> None:
    import swarm_scenario

    OUT.mkdir(parents=True, exist_ok=True)
    made = {
        "qa_s1_formation6": s1_formation6(), "qa_s2_swarm20": s2_swarm20(), "qa_s3_link": s3_link(),
        "qa_s4_engage": s4_engage(), "qa_s5_mixed": s5_mixed(), "qa_s6_load50": s6_load(50),
        "qa_s6_load100": s6_load(100), "qa_s6_load100_flock": s6_load(100, "flocking"),
    }
    for stem, doc in made.items():
        issues = swarm_scenario.validate(doc)
        (OUT / f"{stem}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{stem}: 엔티티 {len(doc['entities'])}, 검증 오류 {len(issues)}" + "".join(f"\n  {i}" for i in issues[:5]))


if __name__ == "__main__":
    main()

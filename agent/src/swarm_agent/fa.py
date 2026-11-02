"""기본 FA "default" (IMP-AGT-007, PRP-GNC-001, REQ-GNC-001).

FlightCommand(HSA, Waypoint, Curve/Orbit) → 2/3-DoF용 KinematicCmd.
- 유도: 목표 침로·속도·고도를 만든다. Waypoint는 직행, Orbit은 벡터장(Beard & McLain).
  Racetrack(DEC-034)은 매개변수 racetrack_guidance(dubins 기본 | vector_field)로 고른다 (racetrack.py).
- 제어: 침로 오차 비례 선회율(최대 뱅크로 제한), 고도 오차 비례 상승률.
- KinematicCmd는 heading_rate(2-DoF)와 협조선회 뱅크 bank = atan(V·ψ̇/g)(3-DoF)를 함께 채운다.
  두 모델이 같은 출력으로 같은 궤적을 따른다.
- 고도 alt_m <= 0은 "현재 고도 유지"로 해석한다.
- 명령 전에는 첫 항법 보고의 침로·속도·고도를 유지한다.
- 같은 command_id로 같은 모드 명령이 다시 오면 목표만 바꾸고 상태는 다시 보내지 않는다(편대 추종용).
"""

import math
from collections.abc import Mapping, Sequence
from typing import Any

from swarm.v1 import common_pb2, fa_pb2, vi_pb2
from swarm_api import FlightAutonomy, ParamDef, ParamLayer

from . import racetrack
from .geo import G_MPS2, course_rad, ned_offset, wrap_pi

_A, _C, _G = ParamLayer.AIRFRAME, ParamLayer.CONTROL, ParamLayer.GUIDANCE

# 매개변수 선언 (DEC-035). 기체 한계는 FlightCapability로 Core에 알리므로 실행 중 바꿀 수 없다
PARAMS: tuple[ParamDef, ...] = (
    ParamDef("min_speed_mps", 12.0, _A, "m/s", 1.0, 200.0, "최소 속력", runtime=False),
    ParamDef("max_speed_mps", 35.0, _A, "m/s", 1.0, 500.0, "최대 속력", runtime=False),
    ParamDef("max_climb_mps", 5.0, _A, "m/s", 0.1, 100.0, "최대 상승·하강률", runtime=False),
    ParamDef("max_bank_deg", 35.0, _A, "deg", 1.0, 85.0, "최대 뱅크각", runtime=False),
    ParamDef("max_altitude_m", 6000.0, _A, "m", 0.0, 30000.0, "최대 고도", runtime=False),
    ParamDef("k_heading", 0.8, _C, "1/s", 0.0, 10.0, "침로 오차 → 선회율 이득"),
    ParamDef("k_altitude", 0.3, _C, "1/s", 0.0, 10.0, "고도 오차 → 상승률 이득"),
    ParamDef("k_orbit", 2.0, _G, "", 0.0, 20.0, "Orbit·레이스트랙 원 구간 벡터장 수렴 이득"),
    ParamDef("acceptance_radius_m", 50.0, _G, "m", 0.0, 10000.0, "Waypoint 수락 반경 기본값(명령에 없을 때)"),
    ParamDef("racetrack_guidance", "dubins", _G, "", description="레이스트랙 유도: dubins | vector_field (DEC-034)",
             choices=racetrack.GUIDANCE),
    ParamDef("k_cross_track", 0.02, _G, "1/m", 0.0, 1.0, "dubins 직선 구간 횡방향 오차 이득"),
    ParamDef("cross_track_inf_deg", 60.0, _G, "deg", 1.0, 89.0, "dubins 직선 구간 최대 진입각"),
    ParamDef("k_racetrack_line", 0.3, _G, "", 0.0, 10.0, "vector_field 직선 구간 이득"),
    ParamDef("racetrack_gamma", 0.2, _G, "", 0.0, 5.0, "vector_field 원 구간 접선 이득"),
)
DEFAULTS: dict[str, float] = {d.name: d.default for d in PARAMS if isinstance(d.default, float)}

_S = common_pb2


class DefaultFlightAutonomy(FlightAutonomy):
    PARAMS = PARAMS

    def on_init(self, entity_id: str, params: Mapping[str, Any]) -> vi_pb2.FlightCapability:
        self.entity_id = entity_id
        p = {**DEFAULTS, **{k: v for k, v in params.items() if k in DEFAULTS}}
        self.p = p
        self.race_guidance = str(params.get("racetrack_guidance", "dubins"))
        if self.race_guidance not in racetrack.GUIDANCE:
            raise ValueError(f"racetrack_guidance must be one of {racetrack.GUIDANCE}")
        self.v_min = float(p["min_speed_mps"])
        self.v_max = float(p["max_speed_mps"])
        self.climb_max = float(p["max_climb_mps"])
        self.bank_max = math.radians(float(p["max_bank_deg"]))
        self._cmd_id = ""
        self._kind = ""          # "" | hsa | waypoint | orbit | loiter
        self._executing = False
        self._pending: list[vi_pb2.FlightCommandStatus] = []
        self._hdg: float | None = None
        self._spd: float | None = None
        self._alt: float | None = None
        self._wps: list[vi_pb2.Waypoint] = []
        self._wp_idx = 0
        self._loop = False
        self._orbit: tuple[float, float, float, float] | None = None  # lat, lon, radius, λ
        self._race: tuple[float, float, float, float, float, float] | None = None  # lat, lon, R, L, α, λ
        self._course = 0.0
        return vi_pb2.FlightCapability(
            min_speed_mps=self.v_min, max_speed_mps=self.v_max, max_climb_mps=self.climb_max,
            max_bank_deg=float(p["max_bank_deg"]), max_altitude_m=float(p["max_altitude_m"]),
            supports_hsa=True, supports_waypoint=True, supports_curve=True)

    def on_params(self, values: Mapping[str, Any], changed: Mapping[str, Any]) -> None:
        """실행 중 변경(제어·유도 항목만 들어온다). 잘못된 레이스트랙 유도 이름은 이전 값을 유지한다"""
        for k in changed:
            if k in DEFAULTS:
                self.p[k] = float(values[k])
        g = values.get("racetrack_guidance")
        if "racetrack_guidance" in changed and g in racetrack.GUIDANCE:
            self.race_guidance = g

    # ---- 명령 ----

    def _status(self, cmd_id: str, state: int, reason: str = "") -> vi_pb2.FlightCommandStatus:
        return vi_pb2.FlightCommandStatus(command_id=cmd_id, state=state, reason=reason)

    def on_command(self, cmd: vi_pb2.FlightCommand) -> vi_pb2.FlightCommandStatus:
        mode = cmd.WhichOneof("mode")
        reason = self._validate(cmd, mode)
        if reason:
            return self._status(cmd.command_id, _S.COMMAND_STATE_REJECTED, reason)
        kind = "orbit" if mode == "curve" else mode
        update = cmd.command_id == self._cmd_id and kind == self._kind
        if not update and self._cmd_id and self._kind and self._executing_or_accepted():
            self._pending.append(self._status(self._cmd_id, _S.COMMAND_STATE_CANCELLED, "superseded"))
        if mode == "hsa":
            h = cmd.hsa
            if h.HasField("heading_deg"):
                self._hdg = math.radians(h.heading_deg)
            if h.HasField("speed_mps"):
                self._spd = h.speed_mps
            if h.HasField("altitude_m"):
                self._alt = h.altitude_m
        elif mode == "waypoint":
            self._wps = list(cmd.waypoint.waypoints)
            self._loop = cmd.waypoint.loop
            if not update:
                self._wp_idx = 0
            self._wp_idx = min(self._wp_idx, len(self._wps) - 1)
        elif cmd.curve.WhichOneof("curve") == "racetrack":
            r = cmd.curve.racetrack
            lam = -1.0 if r.direction == vi_pb2.TURN_DIRECTION_CCW else 1.0
            self._race = (r.center.lat_deg, r.center.lon_deg, r.radius_m, r.leg_length_m,
                          math.radians(r.axis_heading_deg), lam)
            if r.HasField("speed_mps"):
                self._spd = r.speed_mps
            if r.center.alt_m > 0:
                self._alt = r.center.alt_m
        else:
            o = cmd.curve.orbit
            lam = -1.0 if o.direction == vi_pb2.TURN_DIRECTION_CCW else 1.0
            self._orbit = (o.center.lat_deg, o.center.lon_deg, o.radius_m, lam)
            self._race = None
            if o.HasField("speed_mps"):
                self._spd = o.speed_mps
            if o.center.alt_m > 0:
                self._alt = o.center.alt_m
        self._kind = kind
        if not update:
            self._cmd_id = cmd.command_id
            self._executing = False
        return self._status(cmd.command_id, _S.COMMAND_STATE_ACCEPTED)

    def _executing_or_accepted(self) -> bool:
        return self._kind in ("hsa", "waypoint", "orbit")

    @staticmethod
    def _validate(cmd: vi_pb2.FlightCommand, mode: str | None) -> str:
        if mode is None:
            return "no mode"
        if mode == "waypoint" and not cmd.waypoint.waypoints:
            return "empty waypoint list"
        if mode == "curve":
            curve = cmd.curve.WhichOneof("curve")
            if curve == "racetrack":
                if cmd.curve.racetrack.radius_m <= 0:
                    return "racetrack radius must be > 0"
                if cmd.curve.racetrack.leg_length_m < 0:
                    return "racetrack leg_length_m must be >= 0"
            elif curve != "orbit":
                return "unsupported curve"
            elif cmd.curve.orbit.radius_m <= 0:
                return "orbit radius must be > 0"
        return ""

    def pending_status(self) -> Sequence[vi_pb2.FlightCommandStatus]:
        out, self._pending = self._pending, []
        return out

    # ---- 유도·제어 ----

    def turn_radius(self, v: float) -> float:
        return v * v / (G_MPS2 * math.tan(self.bank_max))

    def step(self, nav: vi_pb2.NavigationReport, dt_s: float) -> fa_pb2.ControlOutput:
        k = nav.kinematics
        lat, lon, alt = k.position.lat_deg, k.position.lon_deg, k.position.alt_m
        vn, ve, vd = k.velocity_ned_mps.x, k.velocity_ned_mps.y, k.velocity_ned_mps.z
        v = math.hypot(vn, ve)
        if v > 1.0:
            self._course = float(course_rad(vn, ve))
        chi = self._course
        if self._hdg is None:
            self._hdg = chi
        if self._spd is None:
            self._spd = min(max(v, self.v_min), self.v_max)
        if self._alt is None or self._alt <= 0:
            self._alt = alt

        if self._cmd_id and not self._executing and self._kind in ("hsa", "waypoint", "orbit"):
            self._executing = True
            self._pending.append(self._status(self._cmd_id, _S.COMMAND_STATE_EXECUTING))

        chi_d, v_d, h_d = self._hdg, self._spd, self._alt
        if self._kind == "waypoint":
            chi_d, v_d, h_d = self._waypoint(lat, lon, alt, v)
        if self._kind in ("orbit", "loiter"):
            chi_d = self._orbit_course(lat, lon)

        v_ref = max(v, self.v_min)
        rate_max = G_MPS2 * math.tan(self.bank_max) / v_ref
        rate = max(-rate_max, min(rate_max, self.p["k_heading"] * float(wrap_pi(chi_d - chi))))
        climb = max(-self.climb_max, min(self.climb_max, self.p["k_altitude"] * (h_d - alt)))
        out = fa_pb2.ControlOutput()
        kc = out.kinematic
        kc.speed_mps = max(self.v_min, min(self.v_max, v_d))
        kc.heading_rate_rps = rate
        kc.bank_rad = math.atan(v_ref * rate / G_MPS2)
        kc.climb_rate_mps = climb
        return out

    def _waypoint(self, lat: float, lon: float, alt: float, v: float) -> tuple[float, float, float]:
        wp = self._wps[self._wp_idx]
        acc = max(wp.acceptance_radius_m or self.p["acceptance_radius_m"], self.turn_radius(max(v, self.v_min)))
        n, e = ned_offset(lat, lon, wp.position.lat_deg, wp.position.lon_deg)
        if math.hypot(n, e) < acc:
            if self._wp_idx + 1 < len(self._wps):
                self._wp_idx += 1
            elif self._loop:
                self._wp_idx = 0
            else:
                self._finish_waypoints(wp, v)
                return self._hdg, self._spd, self._alt
            wp = self._wps[self._wp_idx]
            n, e = ned_offset(lat, lon, wp.position.lat_deg, wp.position.lon_deg)
        if wp.HasField("speed_mps"):
            self._spd = wp.speed_mps
        if wp.position.alt_m > 0:
            self._alt = wp.position.alt_m
        self._hdg = math.atan2(float(e), float(n))
        return self._hdg, self._spd, self._alt

    def _finish_waypoints(self, wp: vi_pb2.Waypoint, v: float) -> None:
        """마지막 경유점에 닿으면 COMPLETED를 보내고 그 점 둘레를 선회한다"""
        self._pending.append(self._status(self._cmd_id, _S.COMMAND_STATE_COMPLETED))
        radius = max(2.0 * self.turn_radius(max(v, self.v_min)), wp.acceptance_radius_m)
        self._orbit = (wp.position.lat_deg, wp.position.lon_deg, radius, 1.0)
        self._race = None
        if wp.position.alt_m > 0:
            self._alt = wp.position.alt_m
        self._kind = "loiter"

    def _racetrack_course(self, lat: float, lon: float) -> float:
        clat, clon, r, leg, alpha, lam = self._race
        n, e = (float(x) for x in ned_offset(clat, clon, lat, lon))
        if self.race_guidance == "vector_field":
            self._hdg = racetrack.vector_field_course(n, e, r, leg, alpha, lam, self.p["k_racetrack_line"],
                                                      self.p["racetrack_gamma"])
        else:
            self._hdg = racetrack.dubins_course(n, e, r, leg, alpha, lam, self.p["k_orbit"],
                                                self.p["k_cross_track"],
                                                math.radians(self.p["cross_track_inf_deg"]))
        return self._hdg

    def _orbit_course(self, lat: float, lon: float) -> float:
        if self._race is not None:
            return self._racetrack_course(lat, lon)
        clat, clon, r, lam = self._orbit
        n, e = ned_offset(clat, clon, lat, lon)
        d = math.hypot(n, e)
        gamma = math.atan2(float(e), float(n))  # 중심에서 본 기체 방위
        self._hdg = gamma + lam * (math.pi / 2 + math.atan(self.p["k_orbit"] * (d - r) / r))
        return self._hdg

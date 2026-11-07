"""시험용 내부 메시지 표본과 rx 주입 도우미"""
from __future__ import annotations

from google.protobuf.message import Message
from swarm.v1 import c2_pb2, common_pb2, entity_pb2, link_pb2, ms_pb2, options_pb2, p2p_pb2, vi_pb2
from swarm_api import keys
from swarm_api.bus import protobuf_encoding

GCS = "gcs-01"
UAV = "uav-001"

_IFACE = {v: k for k, v in {
    "c2": options_pb2.L1_INTERFACE_C2, "vi": options_pb2.L1_INTERFACE_VI, "ms": options_pb2.L1_INTERFACE_MS,
    "p2p": options_pb2.L1_INTERFACE_P2P}.items()}


def _h(msg: Message, src: str = UAV) -> Message:
    msg.header.source = src
    msg.header.sim_time_us = 1_000_000
    return msg


def nav() -> vi_pb2.NavigationReport:
    m = _h(vi_pb2.NavigationReport())
    m.kinematics.position.lat_deg, m.kinematics.position.lon_deg, m.kinematics.position.alt_m = 37.5, 128.0, 1500
    m.kinematics.velocity_ned_mps.x = 20.0
    m.position_sigma_m = 3.0
    return m


def system_status() -> vi_pb2.SystemStatus:
    m = _h(vi_pb2.SystemStatus(health=vi_pb2.HEALTH_DEGRADED, energy_frac=0.7))
    m.subsystems.add(name="engine", health=vi_pb2.HEALTH_NOMINAL)
    m.subsystems.add(name="cam0", health=vi_pb2.HEALTH_DEGRADED)
    return m


def flight_command_status() -> vi_pb2.FlightCommandStatus:
    return _h(vi_pb2.FlightCommandStatus(command_id="fc-7", state=common_pb2.COMMAND_STATE_REJECTED,
                                         reason="speed above limit"))


def flight_capability() -> vi_pb2.FlightCapability:
    return _h(vi_pb2.FlightCapability(min_speed_mps=15, max_speed_mps=35, supports_hsa=True,
                                      supports_waypoint=True, supports_curve=True))


def task_status() -> c2_pb2.TaskStatus:
    return _h(c2_pb2.TaskStatus(task_id="task-3", state=common_pb2.COMMAND_STATE_EXECUTING, progress=0.4))


def approval_request() -> c2_pb2.ApprovalRequest:
    return _h(c2_pb2.ApprovalRequest(request_id="req-1", task_id="task-9", target_id="tgt-001",
                                     description="strike approval"))


def peer_status() -> p2p_pb2.PeerStatus:
    m = _h(p2p_pb2.PeerStatus(current_task_id="task-3", group_id="grp-a", energy_frac=0.8))
    m.kinematics.position.lat_deg = 37.5
    return m


def leader_update() -> p2p_pb2.LeaderUpdate:
    return _h(p2p_pb2.LeaderUpdate(group_id="grp-a", leader="uav-002", term=4))


def track_share() -> p2p_pb2.TrackShare:
    m = _h(p2p_pb2.TrackShare(track_id="trk-1", target_id="tgt-001", kind=entity_pb2.ENTITY_KIND_GROUND_TARGET))
    m.position.lat_deg, m.position.lon_deg, m.position.alt_m = 37.6, 128.1, 300
    m.velocity_ned_mps.x = 5.0
    return m


def sensor_activity() -> ms_pb2.SensorActivity:
    m = _h(ms_pb2.SensorActivity(payload_id="cam0", active=True, hfov_deg=30, vfov_deg=20, max_range_m=5000))
    m.boresight_ned.x, m.boresight_ned.z = 0.8, 0.6
    return m


def jammer_activity() -> ms_pb2.JammerActivity:
    m = _h(ms_pb2.JammerActivity(payload_id="jam0", active=True))
    m.zone.radius_m = 2000
    return m


def strike_activity() -> ms_pb2.StrikeActivity:
    return _h(ms_pb2.StrikeActivity(payload_id="sta1", weapon_entity="wpn-uav-001-1",
                                    state=ms_pb2.STRIKE_STATE_LAUNCHED))


def store_loadout() -> ms_pb2.StoreLoadout:
    m = _h(ms_pb2.StoreLoadout())
    m.stores.add(id="sta1", type="agm_short", count=2)
    return m


# 1단계에서 내보내는 STD 상태 메시지 → 기대 UCI 메시지명
EXPORT_SAMPLES = {
    "MA_NavigationReport": nav,
    "SystemStatus": system_status,
    "MA_FlightCommandStatus": flight_command_status,
    "MA_FlightCapability": flight_capability,
    "MA_TaskStatus": task_status,
    "MA_ApprovalRequest": approval_request,
    "MA_PackagePartnerStatusReport": peer_status,
    "MA_LeaderUpdateRequest": leader_update,
    "MA_Entity": track_share,
    "PO_Activity": sensor_activity,
    "EA_Activity": jammer_activity,
    "StrikeActivity": strike_activity,
    "StoreLoadoutConfiguration": store_loadout,
}


def iface_of(msg: Message) -> str:
    return _IFACE[msg.DESCRIPTOR.GetOptions().Extensions[options_pb2.l1]]


def envelope(msg: Message, dst: str = GCS) -> link_pb2.LinkEnvelope:
    env = link_pb2.LinkEnvelope(dst=[dst], iface=msg.DESCRIPTOR.GetOptions().Extensions[options_pb2.l1],
                                msg_type=msg.DESCRIPTOR.full_name, payload=msg.SerializeToString(),
                                rx_time_us=1_000_000)
    env.header.source = msg.header.source
    return env


def rx_key(msg: Message, dst: str = GCS) -> str:
    return keys.rx(dst, keys.Iface(iface_of(msg)), msg.DESCRIPTOR.name)


def deliver(bus, msg: Message, dst: str = GCS) -> None:
    """FakeDatalink 대신 rx 키에 LinkEnvelope를 직접 싣는다"""
    env = envelope(msg, dst)
    bus.put(rx_key(msg, dst), env.SerializeToString(), protobuf_encoding(env.DESCRIPTOR.full_name))

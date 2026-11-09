"""MA "example_rendezvous" (IMP-EXP-003): BatchMissionAutonomy 예제.

기체마다 자기 위치를 PeerStatus로 방송하고, 받은 이웃과 자기의 평균 위치로 침로를 잡는다.

- 자기 상태는 NavBatch에서 읽는다.
- 이웃 정보는 자기 포트의 P2P 수신함으로 받은 것만 쓴다. NavBatch의 다른 행을
  이웃 정보로 쓰면 데이터링크 모의를 건너뛰게 된다 (DEC-008).
"""

from collections.abc import Sequence

import numpy as np

from swarm.v1 import p2p_pb2, vi_pb2
from swarm_api import AgentContext, BatchMissionAutonomy, NavBatch, ParamDef, ParamLayer

M_PER_DEG = 111_320.0


class Rendezvous(BatchMissionAutonomy):
    PARAMS = (
        ParamDef("speed_mps", 22.0, ParamLayer.BEHAVIOR, "m/s", 1.0, 200.0, "순항 속도"),
        ParamDef("peer_hz", 2.0, ParamLayer.BEHAVIOR, "Hz", 0.1, 50.0, "PeerStatus 송신 주기"),
    )

    def on_init(self, ctxs: Sequence[AgentContext]) -> None:
        # 이웃 표는 기체별로 따로 둔다
        self.peers: dict[str, dict[str, tuple[float, float]]] = {c.entity_id: {} for c in ctxs}
        self.speed = {c.entity_id: float(c.params.get("speed_mps", 22.0)) for c in ctxs}
        self.peer_hz = {c.entity_id: float(c.params.get("peer_hz", 2.0)) for c in ctxs}

    def on_params(self, ctx: AgentContext, changed: dict) -> None:
        if "speed_mps" in changed:
            self.speed[ctx.entity_id] = float(changed["speed_mps"])
        if "peer_hz" in changed:
            self.peer_hz[ctx.entity_id] = float(changed["peer_hz"])

    def on_step_batch(self, ctxs: Sequence[AgentContext], nav: NavBatch) -> None:
        for i, c in enumerate(ctxs):
            c.ports.c2.inbox()
            c.ports.vi.command_status()
            table = self.peers[c.entity_id]
            for m in c.ports.p2p.inbox():
                if isinstance(m, p2p_pb2.PeerStatus):
                    p = m.kinematics.position
                    table[m.header.source] = (p.lat_deg, p.lon_deg)
            if not nav.valid[i]:
                continue

            own = nav.lat_lon_alt[i]
            points = np.array([own[:2], *table.values()])
            lat_c, lon_c = points.mean(axis=0)
            north = (lat_c - own[0]) * M_PER_DEG
            east = (lon_c - own[1]) * M_PER_DEG * np.cos(np.radians(own[0]))

            cmd = vi_pb2.FlightCommand(command_id=f"{c.entity_id}-rdv")
            cmd.hsa.heading_deg = float(np.degrees(np.arctan2(east, north))) % 360.0
            cmd.hsa.altitude_m = float(own[2])
            cmd.hsa.speed_mps = self.speed[c.entity_id]
            c.ports.vi.command(cmd)

            period = max(1, round(1.0 / (self.peer_hz[c.entity_id] * c.dt_s)))
            if c.frame % period == 0:
                ps = p2p_pb2.PeerStatus()
                ps.kinematics.position.lat_deg = float(own[0])
                ps.kinematics.position.lon_deg = float(own[1])
                ps.kinematics.position.alt_m = float(own[2])
                c.ports.p2p.send(ps)

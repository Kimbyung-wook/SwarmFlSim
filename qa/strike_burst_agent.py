"""TC-QA-055~056용 Agent 실행기. 실제 swarm_agent.cli를 띄우되 flocking_basic을 정해진 프레임에 StrikeCommand를 내는
관찰용 MA로 바꾼다 (QA 전용).

BURST_PLAN 환경 변수: [{"f": 프레임, "e": 기체, "pid": 스테이션, "tgt": 표적}, ...] JSON.
  "aim": [lat, lon, alt]이면 조준점 StrikeCommand, "kind": "sensor"|"jam"과 "en": bool이면 SensorCommand·JammerCommand (13차).
MA 프레임 번호로만 명령을 내므로 lockstep에서 결정적이다.
BURST_OUT 경로에 낸 명령과 MS 포트로 받은 StrikeActivity를 JSON으로 남긴다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from swarm.v1 import ms_pb2
from swarm_algorithms.flocking import Flocking

import swarm_agent.cli as cli
from swarm_agent.plugins import PluginRegistry

OUT = Path(os.environ.get("BURST_OUT", "burst_probe.json"))
PLAN = json.loads(os.environ.get("BURST_PLAN", "[]"))
S: dict = {"cmds": [], "acts": [], "last_frame": 0}


def _dump() -> None:
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(S, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUT)


class BurstFlocking(Flocking):
    def on_step_batch(self, ctxs, nav) -> None:  # noqa: ANN001
        for c in ctxs:
            S["last_frame"] = max(S["last_frame"], c.frame)
            for a in c.ports.ms.activities():
                if isinstance(a, ms_pb2.StrikeActivity):
                    S["acts"].append({"f": c.frame, "e": c.entity_id, "pid": a.payload_id,
                                      "state": ms_pb2.StrikeState.Name(a.state), "reason": a.reason,
                                      "weapon": a.weapon_entity, "hf": a.header.frame})
            for p in PLAN:
                if p["f"] == c.frame and p["e"] == c.entity_id:
                    kind = p.get("kind", "strike")
                    if kind == "sensor":
                        cmd = ms_pb2.SensorCommand(payload_id=p["pid"], enable=p["en"])
                    elif kind == "jam":
                        cmd = ms_pb2.JammerCommand(payload_id=p["pid"], enable=p["en"])
                    else:
                        cmd = ms_pb2.StrikeCommand(payload_id=p["pid"], target_id=p.get("tgt", ""))
                        if "aim" in p:
                            cmd.aim_point.lat_deg, cmd.aim_point.lon_deg, cmd.aim_point.alt_m = p["aim"]
                    cmd.header.correlation_id = f"qa-burst-{p['pid']}-{p.get('tgt', kind)}-{c.frame}"
                    c.ports.ms.command(cmd)
                    S["cmds"].append({**p, "corr": cmd.header.correlation_id})
        super().on_step_batch(ctxs, nav)
        if ctxs and ctxs[0].frame % 250 == 0:
            _dump()


class BurstRegistry(PluginRegistry):
    def __init__(self, *a, **k) -> None:  # noqa: ANN002, ANN003
        k.setdefault("extra_ma", {})["flocking_basic"] = BurstFlocking
        super().__init__(*a, **k)


if __name__ == "__main__":
    cli.PluginRegistry = BurstRegistry
    try:
        rc = cli.main(sys.argv[1:])
    finally:
        _dump()
    sys.exit(rc)

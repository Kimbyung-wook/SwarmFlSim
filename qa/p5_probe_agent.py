"""TC-QA-031~033용 Agent 실행기. 실제 swarm_agent.cli를 띄우되 flocking_basic을 관찰용 MA로 바꾼다.

관찰용 MA(QA 전용)는 flocking 동작을 그대로 하면서
- MS 포트(ctx.ports.ms.detections()/activities())로 받은 Detection·Activity를 집계하고
- 지상 표적을 처음 탐지한 기체가 무장 스테이션을 가졌으면 그 표적에 StrikeCommand를 MS 포트로 낸다.
명령 재시도는 프레임 번호로만 정해 lockstep 결정성을 해치지 않는다.

P5_PROBE_OUT 환경 변수의 경로에 JSON으로 집계를 남긴다.
P5_PROBE_IO가 있으면 그 경로에 프레임·기체별 MA 입력(항법 보고 프레임·신선도·위치 비트, P2P·C2 수신함의
송신자·seq·sim_time 순서)을 한 줄씩 남긴다 (QA-019 원인 조사용).
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from swarm.v1 import ms_pb2
from swarm_algorithms.flocking import Flocking

import swarm_agent.cli as cli
from swarm_agent.plugins import PluginRegistry

OUT = Path(os.environ.get("P5_PROBE_OUT", "p5_probe.json"))
STRIKERS = {"uav-001": "sta1", "uav-003": "fpv1", "uav-004": "sta1"}
RETRY_FRAMES = 50

S = {
    "det": defaultdict(lambda: {"n": 0, "first": None, "last": None, "min_range": None}),
    "det_frames": defaultdict(list),  # 기체별 탐지가 있던 프레임 구간 [start, end]
    "acts": [],
    "cmds": [],
    "assign": {},
    "last_frame": 0,
}
_last_try: dict[tuple[str, str], int] = {}
_IO_PATH = os.environ.get("P5_PROBE_IO")
_IO = open(_IO_PATH, "w", encoding="utf-8", buffering=1 << 16) if _IO_PATH else None


def _msgs(port) -> str:  # noqa: ANN001
    buf = getattr(port, "buffer", None)
    if buf is None:
        return "?"
    return ",".join(f"{m.header.source}:{m.header.seq}:{m.header.sim_time_us}" for m in buf.peek())


def _io_record(ctxs, nav) -> None:  # noqa: ANN001
    """MA가 이번 프레임에 받는 입력을 그대로 적는다. 위치·속도는 float.hex로 비트까지 비교한다"""
    for i, c in enumerate(ctxs):
        n = c.ports.vi.nav()
        nf = n.header.frame if n is not None else -1
        lla = ",".join(float(x).hex() for x in (*nav.lat_lon_alt[i], *nav.velocity_ned[i]))
        _IO.write(f"{c.frame} {c.entity_id} nav={nf} fresh={int(bool(nav.valid[i]))} x={lla} "
                  f"p2p=[{_msgs(c.ports.p2p)}] c2=[{_msgs(c.ports.c2)}]\n")
    if ctxs and ctxs[0].frame % 50 == 0:
        _IO.flush()
_launched: set[str] = set()


def _dump() -> None:
    d = {
        "det": {k: v for k, v in S["det"].items()},
        "det_frames": S["det_frames"],
        "acts": S["acts"], "cmds": S["cmds"], "assign": S["assign"], "last_frame": S["last_frame"],
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUT)


class ProbeFlocking(Flocking):
    def on_step_batch(self, ctxs, nav) -> None:  # noqa: ANN001
        if _IO is not None:
            _io_record(ctxs, nav)
        for c in ctxs:
            S["last_frame"] = max(S["last_frame"], c.frame)
            dets = c.ports.ms.detections()
            if dets:
                runs = S["det_frames"][c.entity_id]
                if runs and runs[-1][1] >= c.frame - 1:
                    runs[-1][1] = c.frame
                else:
                    runs.append([c.frame, c.frame])
            for d in dets:
                k = f"{c.entity_id}>{d.target_id}"
                r = S["det"][k]
                r["n"] += 1
                r["first"] = c.frame if r["first"] is None else r["first"]
                r["last"] = c.frame
                r["min_range"] = d.range_m if r["min_range"] is None else min(r["min_range"], d.range_m)
                if d.target_id.startswith("tgt-") and d.target_id not in S["assign"] and c.entity_id in STRIKERS \
                        and c.entity_id not in S["assign"].values():
                    S["assign"][d.target_id] = c.entity_id
            for a in c.ports.ms.activities():
                if isinstance(a, ms_pb2.StrikeActivity):
                    S["acts"].append({"f": c.frame, "e": c.entity_id, "pid": a.payload_id,
                                      "state": ms_pb2.StrikeState.Name(a.state), "reason": a.reason,
                                      "weapon": a.weapon_entity})
                    if a.state == ms_pb2.STRIKE_STATE_LAUNCHED:
                        _launched.add(c.entity_id)
            for tgt, shooter in S["assign"].items():
                if shooter != c.entity_id or shooter in _launched:
                    continue
                last = _last_try.get((shooter, tgt))
                if last is not None and c.frame - last < RETRY_FRAMES:
                    continue
                _last_try[(shooter, tgt)] = c.frame
                cmd = ms_pb2.StrikeCommand(payload_id=STRIKERS[shooter], target_id=tgt)
                cmd.header.correlation_id = f"qa-{shooter}-{tgt}-{c.frame}"
                c.ports.ms.command(cmd)
                S["cmds"].append({"f": c.frame, "e": shooter, "tgt": tgt})
        super().on_step_batch(ctxs, nav)
        if ctxs and ctxs[0].frame % 250 == 0:
            _dump()


class ProbeRegistry(PluginRegistry):
    def __init__(self, *a, **k) -> None:  # noqa: ANN002, ANN003
        k.setdefault("extra_ma", {})["flocking_basic"] = ProbeFlocking
        super().__init__(*a, **k)


if __name__ == "__main__":
    cli.PluginRegistry = ProbeRegistry
    try:
        rc = cli.main(sys.argv[1:])
    finally:
        _dump()
        if _IO is not None:
            _IO.close()
    sys.exit(rc)

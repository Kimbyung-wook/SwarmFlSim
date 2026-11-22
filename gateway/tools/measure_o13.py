"""QA O-13 측정: 재기동한 Gateway의 준비 전 외부 PUB 손실 구간 (QA 계획 §35.5).

    uv run python tools/measure_o13.py [--runs 5] [--interval 0.5] [--port 18765]

- CAL Server를 별도 프로세스로 띄우고(설정은 config/lacal_server.yaml, 포트만 바꿈) 외부 C2(`external_c2`)가
  `MA_TaskCommand`를 `--interval` 간격으로 계속 PUB한다(작업 ID에 일련번호).
- Gateway는 매 회 새 프로세스로 띄우고(가져오기·XSD 적재 포함 실제 재기동) 준비 뒤 `--hold` s 지나 끝낸다(자기 PID).
  다음 회 Gateway는 앞 Gateway가 끝난 직후 띄운다.
- Gateway 프로세스는 프로세스 안 버스를 쓴다. Core의 `sim/ctrl/scenario` 재발행은 구독 즉시 전달로 흉내 낸다.
  tx로 나간 작업 ID와 단계 시각(벽시계)을 표준 출력 JSON 줄로 알린다.
- 회마다: 앞 Gateway 종료 → 새 프로세스 시작 → LA-CAL 접속 → SUB 완료 → ready 시각과,
  그 사이 보낸 PUB 중 잃은 것과 처음 받은 것을 적는다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
CHILD_T0 = time.time()


# ---------------------------------------------------------------- Gateway 프로세스
def child(url: str, hold: float) -> None:
    import logging

    from swarm_api import keys
    from swarm_api.bus import InMemoryBus, protobuf_encoding
    from swarm.v1 import c2_pb2, entity_pb2, link_pb2, sim_pb2

    from swarm_gateway.gateway import GatewayConfig
    from swarm_gateway.runner import start_gateway

    def emit(ev: str, **kw) -> None:
        print(json.dumps({"ev": ev, "t": time.time(), **kw}), flush=True)

    emit("spawn", t=CHILD_T0)
    sc = sim_pb2.Scenario(name="o13")
    for u in ("uav-001", "uav-002"):
        sc.entities.add(id=u, kind=entity_pb2.ENTITY_KIND_UAV, controlling_gcs="gcs-01")

    class Bus(InMemoryBus):
        def subscribe(self, keyexpr, callback, **kw):
            sub = super().subscribe(keyexpr, callback, **kw)
            if keyexpr == keys.SIM_CTRL_SCENARIO:   # Core 재발행 흉내
                self.put(keyexpr, sc.SerializeToString(), protobuf_encoding("swarm.v1.Scenario"))
            return sub

    class Events(logging.Handler):
        def emit(self, record):
            m = record.getMessage()
            for tag, ev in (("LA-CAL connected", "connected"), ("XSD loaded", "xsd"),
                            ("SUB MA_TaskCommand", "sub_c2"), ("gateway: ready", "ready")):
                if tag in m:
                    emit(ev)
            if "rejected" in m and "MA_TaskCommand" in m:
                emit("rejected", reason=m[-200:])

    log = logging.getLogger("swarm_gateway")
    log.setLevel(logging.INFO)
    log.addHandler(Events())
    bus = Bus()

    def on_tx(s):
        env = link_pb2.LinkEnvelope.FromString(s.payload)
        emit("tx", task=c2_pb2.TaskCommand.FromString(env.payload).task_id)

    bus.subscribe("swarm/gcs-01/tx/c2/TaskCommand", on_tx)

    async def run():
        running = await start_gateway(bus, GatewayConfig("gcs-01"), url, admin_url=None)
        await asyncio.sleep(hold)
        emit("stop")
        await running.stop()

    asyncio.run(run())


# ---------------------------------------------------------------- 측정 프로세스
async def measure(args) -> list[dict]:
    from swarm.v1 import c2_pb2
    from swarm_api.bus import InMemoryBus

    from swarm_gateway.gateway import Gateway, GatewayConfig
    from swarm_gateway.lacal import LaCalClient

    import yaml
    cfg = yaml.safe_load((HERE / "config" / "lacal_server.yaml").read_text(encoding="utf-8"))
    cfg["listen"]["port"], cfg["admin"]["port"] = args.port, args.port + 1
    tmp = Path(tempfile.mkdtemp(prefix="o13-")) / "lacal.yaml"
    tmp.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "swarm_gateway.lacal_server", "--config", str(tmp),
                               "--log", "WARNING"], cwd=HERE)
    url = f"ws://127.0.0.1:{args.port}"
    maker = Gateway(InMemoryBus(), GatewayConfig("gcs-01"))       # 외부 메시지 만들기용 (변환기·봉투)

    def command(n: int) -> dict:
        tc = c2_pb2.TaskCommand(task_id=f"o13-{n}", assignees=["uav-001"])
        tc.hold.SetInParent()
        return maker.envelope("MA_TaskCommand", maker.converters["swarm.v1.TaskCommand"].to_uci(tc, maker.ctx))

    ext = LaCalClient(url, "external_c2")
    for _ in range(100):
        try:
            await ext.connect()
            break
        except OSError:
            await asyncio.sleep(0.1)
    sent: dict[int, float] = {}
    events: list[dict] = []
    stop = asyncio.Event()

    async def publisher():
        n = 0
        nxt = time.monotonic()
        while not stop.is_set():
            sent[n] = time.time()
            await ext.publish("swarm.c2", command(n))
            n += 1
            nxt += args.interval
            await asyncio.sleep(max(0.0, nxt - time.monotonic()))

    async def run_child(run: int):
        proc = await asyncio.create_subprocess_exec(
            sys.executable, __file__, "--child", url, "--hold", str(args.hold), cwd=HERE,
            stdout=asyncio.subprocess.PIPE, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        ev = {"run": run, "pid": proc.pid, "tx": [], "rejected": []}
        async for line in proc.stdout:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e["ev"] == "tx":
                ev["tx"].append((int(e["task"].split("-")[1]), e["t"]))
            elif e["ev"] == "rejected":
                ev["rejected"].append(e)
            else:
                ev[e["ev"]] = e["t"]
        await proc.wait()
        ev["exit"] = time.time()
        return ev

    pub = asyncio.create_task(publisher())
    try:
        for run in range(args.runs + 1):              # 0회차는 첫 기동(측정 앞 정상 상태 만들기)
            events.append(await run_child(run))
    finally:
        stop.set()
        await pub
        await ext.close()
        server.terminate()
        server.wait()

    results = []
    for prev, cur in zip(events, events[1:]):
        got = {n for n, _ in cur["tx"]}
        window = [n for n, t in sent.items() if prev["exit"] <= t <= cur["ready"] + 1.0]
        lost = [n for n in window if n not in got]
        first = min((n for n in window if n in got), default=None)
        lost_after_conn = [n for n in lost if sent[n] >= cur["connected"]]
        lost_after_sub = [n for n in lost if sent[n] >= cur["sub_c2"]]
        results.append({
            "run": cur["run"],
            "down_to_spawn_s": round(cur["spawn"] - prev["exit"], 3),
            "spawn_to_connected_s": round(cur["connected"] - cur["spawn"], 3),
            "connected_to_sub_s": round(cur["sub_c2"] - cur["connected"], 3),
            "sub_to_ready_s": round(cur["ready"] - cur["sub_c2"], 3),
            "exit_to_ready_s": round(cur["ready"] - prev["exit"], 3),
            "lost": len(lost), "lost_after_connected": len(lost_after_conn), "lost_after_sub": len(lost_after_sub),
            "loss_span_s": round(sent[max(lost)] - sent[min(lost)], 3) if lost else 0.0,
            "first_received_after_exit_s": round(sent[first] - prev["exit"], 3) if first is not None else None,
            "rejected": len(cur["rejected"]),
        })
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--hold", type=float, default=4.0, help="Gateway 준비 뒤 유지 시간 s")
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--child", metavar="URL")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.child:
        child(args.child, args.hold)
        return
    results = asyncio.run(measure(args))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return
    cols = list(results[0])
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in results:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")


if __name__ == "__main__":
    main()

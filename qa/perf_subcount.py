"""상대 세션의 구독 수·모양에 따른 put 비용 (QA 35차, DEC-100 원인 계측, TC-QA-192).

Agent 구독 모양을 흉내 낸 구독 세션(자식 프로세스) 하나와 발행 세션 하나를 tcp로 잇고, 발행 세션의 put 한 번 비용을 잰다.
Core·Datalink·Logger(C++)와 같은 Zenoh 코어(Rust)의 경로 계산을 보지만, 발행은 Python이라 절대값에는 Python 호출 비용이 들어 있다.
모드 사이의 차이만 본다.

uv run python qa/perf_subcount.py --out qa/out/perf_g/subcount
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api" / "python" / "src"))

from swarm_api.bus import BusConfig, ZenohBus  # noqa: E402

N_VEH = 100
INBOUND = ("Detection", "JammerActivity", "SensorActivity", "StoreLoadout", "StrikeActivity", "SystemStatus")
VEH = [f"uav-{i:03d}" for i in range(1, N_VEH + 1)]


def sub_keys(mode: str) -> list[str]:
    """모드별 구독 키 표현식. wild = IMP-AGT-043(와일드카드 7개), exact = IMP-AGT-052(기체별 700개)"""
    base = ["onboard_batch/NavigationBatch", "sim/clock/tick", "sim/ctrl/cmd", "sim/ctrl/scenario", "sim/clock/done/datalink-0"]
    wild = [f"onboard/*/{n}" for n in INBOUND] + ["swarm/*/rx/**"]
    exact = [f"onboard/{v}/{n}" for v in VEH for n in INBOUND] + [f"swarm/{v}/rx/**" for v in VEH]
    return {"none": [], "wild": base + wild, "exact": base + exact,
            "wild_all": base + wild + ["**"], "exact_all": base + exact + ["**"]}[mode]


FAMILIES = {
    # 구독과 맞는 키 (Datalink 수신 전달, Core onboard 발행)
    "rx_match": [f"swarm/{v}/rx/c2/TaskCommand" for v in VEH],
    "onboard_match": [f"onboard/{v}/SystemStatus" for v in VEH],
    # 어느 Agent 구독과도 맞지 않는 키 (Datalink link/state, Core truth, Agent 자기 발행)
    "link_nomatch": [f"link/{v}/uav-001/state" for v in VEH],
    "truth_nomatch": [f"truth/{v}/State" for v in VEH],
    "ctrl_nomatch": [f"onboard/{v}/ControlOutput" for v in VEH],
}


def child(port: int, mode: str) -> None:
    bus = ZenohBus(BusConfig(listen=[f"tcp/127.0.0.1:{port}"], multicast_scouting=False))
    n = [0]

    def cb(_s) -> None:  # noqa: ANN001
        n[0] += 1

    subs = [bus.subscribe(k, cb) for k in sub_keys(mode)]
    print(json.dumps({"ready": len(subs)}), flush=True)
    sys.stdin.readline()
    print(json.dumps({"received": n[0]}), flush=True)
    bus.close()


def measure(port: int, mode: str, puts: int, rounds: int) -> dict:
    p = subprocess.Popen([sys.executable, __file__, "--child", mode, "--port", str(port)], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, text=True)
    try:
        ready = json.loads(p.stdout.readline())
        bus = ZenohBus(BusConfig(connect=[f"tcp/127.0.0.1:{port}"], multicast_scouting=False))
        time.sleep(3.0)                          # 구독 선언이 발행 세션에 퍼질 시간
        payload = b"x" * 200
        res: dict = {"mode": mode, "subs": ready["ready"], "families": {}}
        for _ in range(rounds):
            for fam, ks in FAMILIES.items():
                t0 = time.perf_counter()
                for i in range(puts):
                    bus.put(ks[i % len(ks)], payload, "")
                dt = time.perf_counter() - t0
                res["families"].setdefault(fam, []).append(round(1e6 * dt / puts, 3))
                time.sleep(0.3)
        time.sleep(1.0)
        bus.close()
        p.stdin.write("\n")
        p.stdin.flush()
        res["received"] = json.loads(p.stdout.readline())["received"]
        res["median_us"] = {f: st.median(v) for f, v in res["families"].items()}
        return res
    finally:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()                             # 자기가 띄운 자식 PID만 종료한다


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="qa/out/perf_g/subcount")
    ap.add_argument("--puts", type=int, default=20000)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--port", type=int, default=47500)
    ap.add_argument("--child", default="")
    a = ap.parse_args()
    if a.child:
        child(a.port, a.child)
        return 0
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for k, mode in enumerate(("none", "wild", "exact", "wild_all", "exact_all", "none", "exact", "wild")):
        r = measure(a.port + k, mode, a.puts, a.rounds)
        results.append(r)
        print(json.dumps({"mode": mode, "subs": r["subs"], "median_us": r["median_us"], "received": r["received"]}), flush=True)
    (out / "result.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

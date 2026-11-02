"""QA-008 판별: 재생 측이 truth/state를 모두 발행하는지, 관찰자가 몇 개를 받는지 비교한다.

uv run --with mcap python qa/qa008_replay.py <rec.mcap> [--build-dir build/msvc-release]
기록의 truth/state 개수(N)와, 배속별로 (a) 재생기 보고 "replayed M messages", (b) 관찰자 수신 수를 출력한다.
관찰자는 callback 안에서 개수만 센다(무거운 처리 없음)와 harness Observer(전체 처리)를 둘 다 쓴다.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mcap")
    ap.add_argument("--build-dir", default="build/msvc-release")
    ap.add_argument("--rates", default="1,4,20,100")
    a = ap.parse_args()
    h.BUILD = Path(a.build_dir)
    from mcap.reader import make_reader
    n_truth = 0
    with open(a.mcap, "rb") as f:
        for _, ch, _m in make_reader(f).iter_messages():
            if ch.topic.endswith("truth/state"):
                n_truth += 1
    print(f"기록 truth/state {n_truth}")
    out = Path(__file__).parent / "out" / "qa008"
    out.mkdir(parents=True, exist_ok=True)
    from swarm_api import BusConfig, open_bus
    port = 17970
    for rate in [float(x) for x in a.rates.split(",")]:
        port += 1
        mesh_ep = f"tcp/127.0.0.1:{port}"
        cnt = {"light": 0}
        lk = threading.Lock()

        def on(_s):
            with lk:
                cnt["light"] += 1
        rp = subprocess.Popen([h.p0.exe(h.BUILD, "logger", "swarm_logger"), "replay", a.mcap, "--rate", str(rate),
                               "--no-multicast", "--listen", mesh_ep], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True)
        time.sleep(0.3)
        bus = open_bus(BusConfig(connect=[mesh_ep], multicast_scouting=False))
        sub = bus.subscribe("truth/state", on)
        ob = h.Observer([mesh_ep])
        t0 = time.monotonic()
        rp.wait(timeout=300)
        wall = time.monotonic() - t0
        time.sleep(1.0)
        rep = (rp.stdout.read() or "").strip().splitlines()
        with ob.lock:
            heavy = ob.frames
            first, last, gaps = ob.first_frame, ob.last_frame, ob.gap_frames
        print(f"rate {rate}: 벽시계 {wall:.1f}s, 재생기 '{rep[-1] if rep else ''}', "
              f"가벼운 수신기 {cnt['light']}, Observer 처리 {heavy}, 첫 프레임 {first}, 마지막 {last}, 중간 누락 {gaps}")
        try:
            sub.close()
        except Exception:
            pass
        bus.close()
        ob.close()


if __name__ == "__main__":
    main()

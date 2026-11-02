"""라이브 스택의 link/outcome을 독립적으로 집계해 Traffic Monitor 통계와 대조한다 (TC-QA-026).

uv run python qa/link_count.py --connect tcp/127.0.0.1:18101 --seconds 40
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", default="tcp/127.0.0.1:18101")
    ap.add_argument("--seconds", type=float, default=40.0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    from swarm_api import BusConfig, open_bus
    sim, truth, link, *_ = h.pb()
    bus = open_bus(BusConfig(connect=[a.connect], multicast_scouting=False))
    lock = threading.Lock()
    out = defaultdict(lambda: {"n": 0, "kinds": Counter(), "reasons": Counter(), "lat_ms": []})
    types = Counter()

    def on(s):
        o = link.LinkOutcome.FromString(s.payload)
        with lock:
            d = out[o.src]
            d["n"] += 1
            d["kinds"][link.LinkOutcomeKind.Name(o.outcome).removeprefix("LINK_OUTCOME_KIND_")] += 1
            types[o.msg_type] += 1
            if o.outcome == link.LINK_OUTCOME_KIND_DROPPED:
                d["reasons"][link.DropReason.Name(o.reason).removeprefix("DROP_REASON_")] += 1
            elif o.rx_time_us >= o.tx_time_us:
                d["lat_ms"].append((o.rx_time_us - o.tx_time_us) / 1000.0)

    sub = bus.subscribe("link/outcome/**", on)
    t0 = time.monotonic()
    time.sleep(a.seconds)
    with lock:
        res = {}
        for src, d in sorted(out.items()):
            lat = sorted(d["lat_ms"])
            res[src] = {
                "n": d["n"], "kinds": dict(d["kinds"]), "reasons": dict(d["reasons"]),
                "loss": round(d["kinds"].get("DROPPED", 0) / d["n"], 4) if d["n"] else None,
                "lat_mean_ms": round(statistics.fmean(lat), 1) if lat else None,
                "lat_p95_ms": round(lat[int(len(lat) * 0.95)], 1) if lat else None,
            }
    print(f"window {time.monotonic() - t0:.1f}s msg_types {dict(types)}")
    for src, r in res.items():
        print(src, json.dumps(r, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        sub.close()
    except Exception:
        pass
    bus.close()


if __name__ == "__main__":
    main()

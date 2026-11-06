"""TC-QA-043: 기체 → GCS 임무장비 상태 보고(*Activity) 빈도·대역 (QA O-4, DEC-051, DEC-056).

--trace-io로 남긴 link_io.pkl.gz(LinkOutcome 전체)에서 msg_type이 *Activity이고 dst가 GCS인 송신을 센다.
송신 기준(Agent가 Datalink에 넘긴 것)이므로 BURST_LOSS와 무관하다. 크기는 LinkOutcome size_bytes(envelope 본문).
같은 키 연속 송신 간격의 최솟값으로 (기체, 메시지)별 최대 빈도를 본다.

사용: uv run python qa/act_rate.py qa/out/p5/r9_base_1 [qa/out/p5/a40_base_1 ...] [--skip-s 5] [--json 파일]
"""
from __future__ import annotations

import argparse
import gzip
import json
import pickle
from collections import defaultdict
from pathlib import Path

FR_US = 20000


def rate(d: Path, gcs: str, skip_s: float) -> dict:
    rows = pickle.load(gzip.open(d / "link_io.pkl.gz"))
    # (tx 프레임, src, dst, seq, iface, msg_type, size, kind, reason, tx_us, rx_us)
    act = [r for r in rows if r[5].endswith("Activity") and r[2] == gcs and r[9] >= skip_s * 1e6]
    if not act:
        return {"n": 0}
    t0 = min(r[9] for r in act)
    t1 = max(r[9] for r in act)
    span = (t1 - t0) / 1e6 or 1.0
    per = defaultdict(list)
    for r in act:
        per[(r[1], r[5].rsplit(".", 1)[-1])].append(r)
    out = {"span_s": round(span, 1), "total_msgs_per_s": round(len(act) / span, 1),
           "total_bytes_per_s": round(sum(r[6] for r in act) / span), "by": {}}
    for (src, msg), rs in sorted(per.items()):
        ts = sorted(r[9] for r in rs)
        gaps = [(b - a) / 1e6 for a, b in zip(ts, ts[1:])]
        out["by"][f"{src}:{msg}"] = {"n": len(rs), "msgs_per_s": round(len(rs) / span, 2),
                                     "bytes_per_s": round(sum(r[6] for r in rs) / span),
                                     "size_b": sorted({r[6] for r in rs})[:4],
                                     "min_gap_s": round(min(gaps), 3) if gaps else None,
                                     "max_gap_s": round(max(gaps), 3) if gaps else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--gcs", default="gcs-01")
    ap.add_argument("--skip-s", type=float, default=5.0, help="이 모의 초 이전 송신은 뺀다(시작 과도)")
    ap.add_argument("--json")
    a = ap.parse_args()
    res = {Path(r).name: rate(Path(r), a.gcs, a.skip_s) for r in a.runs}
    txt = json.dumps(res, ensure_ascii=False, indent=1)
    print(txt)
    if a.json:
        Path(a.json).write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()

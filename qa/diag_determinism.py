"""s3 불완전 링크 결정성 불일치의 원인 진단 (QA-016 근거).

엔티티별 첫 불일치 프레임과 최대 차이를 출력한다.
uv run python qa/diag_determinism.py [--frames 1000] [--seed 7] [--scenario qa_s3_link]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402

SC = Path(__file__).parent / "scenarios"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scenario", default="qa_s3_link")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    out = Path(__file__).parent / "out" / "diag_det"
    out.mkdir(parents=True, exist_ok=True)
    d = json.loads((SC / f"{a.scenario}.json").read_text(encoding="utf-8"))
    d["run"]["seed"] = a.seed
    sj = out / "s.json"
    sj.write_text(json.dumps(d), encoding="utf-8")
    traces = []
    for run in range(a.runs):
        st = h.Stack(out / f"run{run}", sj, lockstep=True, rate=0.0, base_port=48060, record=False)
        st.up()
        t0 = time.monotonic()
        ob = h.Observer([st.endpoint()])
        ob.keep_traj = True
        ob.wait(lambda: (ob.last_frame or 0) >= a.frames, 240)
        time.sleep(0.5)
        with ob.lock:
            traces.append({k: {f: (la, lo, al) for f, la, lo, al in v} for k, v in ob.traj.items()})
        wall = time.monotonic() - t0
        print(f"run{run}: frame {ob.last_frame} gaps {ob.gap_frames} 벽시계 {wall:.1f}s {ob.last_frame / wall:.1f} 프레임/s", flush=True)
        ob.close()
        st.down()
        time.sleep(1)
    ta, tb = traces[0], traces[1]
    bad, firsts, worst_all = 0, [], 0.0
    for k in sorted(ta):
        common = sorted(set(ta[k]) & set(tb.get(k, {})))
        first, worst, n = None, 0.0, 0
        for f in common:
            dd = h.dist_m(ta[k][f][:2], tb[k][f][:2]) + abs(ta[k][f][2] - tb[k][f][2])
            if dd > 1e-6:
                n += 1
                worst = max(worst, dd)
                if first is None:
                    first = f
        if a.verbose:
            print(f"{k}: 공통 {len(common)} 불일치 {n} 첫 프레임 {first} 최대 {worst:.4f} m")
        if n:
            bad += 1
            firsts.append(first)
            worst_all = max(worst_all, worst)
    print(f"요약 {a.scenario} seed {a.seed}: 엔티티 {len(ta)} 중 불일치 {bad}, 첫 발산 프레임 {min(firsts) if firsts else None}, 최대 차 {worst_all:.4f} m")


if __name__ == "__main__":
    main()

"""P1 두 경우 번갈아 비교 (QA 37차, OPN-077, TC-QA-200~).

(가) 현재 작업 트리의 Agent, (나) --b-src 의 agent/src(측정용 임시 worktree에 패치를 적용한 것)를 PYTHONPATH로 앞에 둔 Agent.
C++ 빌드·proto·나머지 Python은 같다. 한 묶음 안에서 가·나를 회차마다 번갈아(가1 나1 가2 나2 …) perf_p1_batch.py run을
--repeat 1로 부른다. 회차마다 유휴 게이트(다른 시뮬레이터 없음 + 시스템 CPU 조건 30 s)를 지난다.

uv run --with psutil python qa/perf_p1_ab.py run --out qa/out/perf_h --batch b1 --n 6 --b-src <임시 worktree>
uv run --with psutil python qa/perf_p1_ab.py run --out qa/out/perf_h --batch p1 --n 6 --b-src <임시 worktree> --cfgs d3_w_log_P,d3_w_P
uv run --with psutil python qa/perf_p1_ab.py summary --out qa/out/perf_h --batches b1,b2
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ("A", "B")
# DEC-087 기준 (QA 26차 §34, 35차 요약 도구로 다시 읽은 값). cfg: 배속
DEC087 = {"d3_w_log": 12.43, "d3_w": 13.52, "d3_w_log_P": 12.27, "d3_w_P": 13.00}


def check_b(src: Path) -> str:
    """(나) Agent가 정말 패치된 소스를 가져오는지 본다"""
    env = {**os.environ, "PYTHONPATH": str(src)}
    r = subprocess.run([sys.executable, "-c", "import swarm_agent, swarm_agent.messages as m; "
                        "print(swarm_agent.__file__, len(m.rx_inbound()))"], env=env, capture_output=True, text=True)
    return r.stdout.strip() or r.stderr.strip()[-300:]


def run(a: argparse.Namespace) -> int:
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    src = Path(a.b_src).resolve() / "agent" / "src"
    chk = check_b(src)
    with (out / "progress.txt").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {a.batch} B 소스 확인: {chk}\n")
    if str(src) not in chk:
        print("B 소스를 가져오지 못함:", chk)
        return 2
    rc_all = 0
    for k in range(1, a.n + 1):
        for c in CASES:
            env = dict(os.environ)
            if c == "B":
                env["PYTHONPATH"] = str(src) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            else:
                env.pop("PYTHONPATH", None)
            cmd = [sys.executable, str(ROOT / "qa" / "perf_p1_batch.py"), "run", "--out", a.out,
                   "--label", f"{a.batch}_{c}{k}", "--repeat", "1", "--base-port", str(a.base_port),
                   "--max-sys", str(a.max_sys)] + (["--only", a.cfgs] if a.cfgs else [])
            rc = subprocess.run(cmd, cwd=ROOT, env=env).returncode
            rc_all = rc_all or rc
    return rc_all


def summary(a: argparse.Namespace) -> int:
    out = ROOT / a.out
    bs = [b for b in a.batches.split(",") if b]
    res: dict = {}
    for c in CASES:
        labels = sorted(p.name for p in out.iterdir() if p.is_dir() and any(p.name.startswith(f"{b}_{c}") for b in bs))
        name = f"summary_{c}.json"
        subprocess.run([sys.executable, str(ROOT / "qa" / "perf_p1_batch.py"), "summary", "--out", a.out,
                        "--labels", ",".join(labels), "--name", name], cwd=ROOT, check=True)
        s = json.loads((out / name).read_text(encoding="utf-8"))
        res[c] = {"labels": labels, "all": s["all"], "pairs": {k: {kk: v[kk] for kk in ("median_noE_ms", "n_noE")}
                                                            for k, v in s["pairs"].items()},
                  "per_batch": {}}
        for b in bs:
            for cfg in DEC087:
                xs = [r["x"] for lab, bb in s["batches"].items() if lab.startswith(f"{b}_") for r in bb[cfg]["runs"] if r["x"]]
                res[c]["per_batch"].setdefault(b, {})[cfg] = st.median(xs) if xs else None
    rows = []
    for cfg, x0 in DEC087.items():
        ms0 = 20.0 / x0
        r = {"cfg": cfg, "dec087_x": x0, "dec087_ms": round(ms0, 3)}
        for c in CASES:
            v = res[c]["all"][cfg]
            r[c] = {"n": v["n"], "x": v["median_x"], "ms": v["median_ms"], "x_noE": v["median_x_noE"], "E": v["E"],
                    "below10": v["below10"], "d_ms": round(v["median_ms"] - ms0, 3) if v["median_ms"] else None}
        if r["A"]["ms"] and r["B"]["ms"]:
            r["B_minus_A_ms"] = round(r["B"]["ms"] - r["A"]["ms"], 3)
        rows.append(r)
    res["table"] = rows
    (out / "ab_summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    for c in CASES:
        print(c, "Logger 비용", res[c]["pairs"], {b: v for b, v in res[c]["per_batch"].items()})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", default="qa/out/perf_h")
    r.add_argument("--batch", required=True)
    r.add_argument("--n", type=int, default=6)
    r.add_argument("--b-src", required=True, help="(나) 패치를 적용한 worktree 경로")
    r.add_argument("--base-port", type=int, default=44000)
    r.add_argument("--max-sys", type=float, default=10.0)
    r.add_argument("--cfgs", default="", help="perf_p1_batch --only (예: d3_w_log_P,d3_w_P)")
    s = sub.add_parser("summary")
    s.add_argument("--out", default="qa/out/perf_h")
    s.add_argument("--batches", required=True)
    a = ap.parse_args()
    return run(a) if a.cmd == "run" else summary(a)


if __name__ == "__main__":
    sys.exit(main())

"""P1 성능 판정 묶음 실행과 요약 (DEC-086(2), QA 35차 TC-QA-190~).

묶음 하나: 다른 시뮬레이터 프로세스가 30 s 없음을 확인 → perf_p1.py 긴 창(7,500 프레임) 실행 → 겹침 기록.
uv run --with psutil python qa/perf_p1_batch.py run --out qa/out/perf_g --label a --repeat 6
uv run --with psutil python qa/perf_p1_batch.py summary --out qa/out/perf_g

판정 구성은 d3_w_log(Logger 켬, 기본 스케줄링)이고, 같은 회차 r의 d3_w(Logger 끔)이 짝 값이다.
P 고정(d3_w_log_P·d3_w_P)은 교차 확인이다. E 코어 회차: 시스템 CPU의 40% 넘게가 논리 코어 16~31에 있던 회차(O-42).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
CFGS = ("d3_w_log", "d3_w", "d3_w_log_P", "d3_w_P")
SIM_WORDS = ("swarm_agent", "perf_agent", "run_p0_demo", "swarm_gateway", "swarm_api", "harness_run", "perf_p1")


def _is_sim(p: psutil.Process) -> bool:
    try:
        name = p.name().lower()
        if name.startswith("swarm_"):
            return True
        if name.startswith("python"):
            return any(any(w in a for w in SIM_WORDS) for a in p.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    return False


def foreign(own: set[int]) -> list[str]:
    """이 측정이 띄우지 않은 시뮬레이터 프로세스"""
    out = []
    for p in psutil.process_iter():
        if p.pid in own or not _is_sim(p):
            continue
        try:
            out.append(f"{p.pid} {p.name()} {' '.join(p.cmdline())[:160]}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def _own_tree(root_pid: int) -> set[int]:
    me = psutil.Process()
    s = {me.pid, *(q.pid for q in me.parents())}
    try:
        r = psutil.Process(root_pid)
        s |= {r.pid, *(c.pid for c in r.children(recursive=True))}
    except psutil.NoSuchProcess:
        pass
    return s


def log(out: Path, msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with (out / "progress.txt").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def top_load(own: set[int], interval: float = 2.0, n: int = 4) -> tuple[float, list[str]]:
    """시스템 CPU %와, 이 측정 밖에서 CPU를 쓰는 상위 프로세스(논리 코어 1개 = 100%)"""
    ps = []
    for p in psutil.process_iter():
        if p.pid in own or p.pid == 0:
            continue
        try:
            p.cpu_percent(None)
            ps.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    sysp = psutil.cpu_percent(interval=interval)
    rows = []
    for p in ps:
        try:
            rows.append((p.cpu_percent(None), p.name(), p.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    rows.sort(reverse=True)
    return sysp, [f"{nm}({pid}) {c:.0f}%" for c, nm, pid in rows[:n] if c >= 5]


def quiet(out: Path, need_s: float = 30.0, max_s: float = 3600.0, max_sys: float = 5.0) -> bool:
    """다른 시뮬레이터 프로세스가 없고 시스템 CPU가 max_sys % 이하인 상태가 need_s 이어지면 시작한다.
    시스템 CPU 조건은 35차 묶음 b 재실행(색인·백신 부하로 무효) 뒤 더했다"""
    own = _own_tree(os.getpid())
    t0 = time.monotonic()
    clear_since = time.monotonic()
    while time.monotonic() - t0 < max_s:
        f = foreign(own)
        sysp, top = top_load(own)
        if f or sysp > max_sys:
            clear_since = time.monotonic()
            with (out / "foreign.txt").open("a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now():%H:%M:%S} wait sys {sysp:.1f}% {' '.join(top)} " + " | ".join(f) + "\n")
        elif time.monotonic() - clear_since >= need_s:
            log(out, f"quiet {need_s:.0f}s (sys {sysp:.1f}%)")
            return True
    log(out, "quiet 시간 초과")
    return False


def run(a: argparse.Namespace) -> int:
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    if not quiet(out, max_sys=a.max_sys):
        return 2
    cmd = [sys.executable, str(ROOT / "qa" / "perf_p1.py"), "--out", f"{a.out}/{a.label}", "--only", a.only or ",".join(CFGS),
           "--repeat", str(a.repeat), "--meas", "7500", "--base-port", str(a.base_port)]
    log(out, f"start {a.label}")
    with (out / f"{a.label}.log").open("w", encoding="utf-8") as lf:
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT)
        stop = threading.Event()
        hits: list[str] = []

        loadf = (out / f"{a.label}_load.txt").open("w", encoding="utf-8")

        def watch() -> None:
            k = 0
            while not stop.is_set():
                own = _own_tree(p.pid)
                for x in foreign(own):
                    hits.append(f"{datetime.now():%H:%M:%S} {a.label} {x}")
                if k % 5 == 0:                    # 측정 밖 CPU 부하 (프로세스별, 5 s마다)
                    _, top = top_load(own, interval=0.5)
                    loadf.write(f"{datetime.now():%H:%M:%S} {' '.join(top)}\n")
                    loadf.flush()
                k += 1
                stop.wait(1.0)

        th = threading.Thread(target=watch, daemon=True)
        th.start()
        rc = p.wait()
        stop.set()
        th.join()
        loadf.close()
    with (out / "foreign.txt").open("a", encoding="utf-8") as fh:
        fh.write("".join(h + "\n" for h in hits))
    log(out, f"end {a.label} rc={rc} 겹침 {len(hits)}건")
    return rc


def ecore(res: dict) -> bool:
    pc = res.get("cpu", {}).get("_system", {}).get("per_core", [])
    if len(pc) < 32 or sum(pc) <= 0:
        return False
    return sum(pc[16:32]) / sum(pc) > 0.4


def load(out: Path, labels: list[str] | None = None) -> dict:
    """{label: {cfg: {r: result}}}"""
    data: dict = {}
    for lab in labels or sorted(p.name for p in out.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for cfg in CFGS:
            for rd in sorted((out / lab / cfg).glob("r*")):
                fp = rd / "result.json"
                if fp.exists():
                    data.setdefault(lab, {}).setdefault(cfg, {})[int(rd.name[1:])] = json.loads(fp.read_text(encoding="utf-8"))
    return data


def summary(a: argparse.Namespace) -> int:
    out = ROOT / a.out
    data = load(out, [x for x in a.labels.split(",") if x])
    s: dict = {"batches": {}, "all": {}, "pairs": {}}
    allv: dict = {c: [] for c in CFGS}
    pairs: dict = {"기본": [], "P 고정": []}
    for lab, cs in data.items():
        b = {}
        for cfg in CFGS:
            runs = cs.get(cfg, {})
            vals = [{"r": r, "x": v.get("speed_x"), "ms": v.get("frame_ms"), "E": ecore(v), "dead": v.get("dead"),
                     "timeout": v.get("timeout"),
                     "cpu": {n: d.get("cpu_pct") for n, d in v.get("cpu", {}).items() if n != "_system"},
                     "sys": v.get("cpu", {}).get("_system", {}).get("busy_pct_avg")} for r, v in sorted(runs.items())]
            xs = [x["x"] for x in vals if x["x"]]
            b[cfg] = {"runs": vals, "median_x": st.median(xs) if xs else None,
                      "median_ms": st.median([x["ms"] for x in vals if x["ms"]]) if xs else None,
                      "below10": sum(1 for x in xs if x < 10), "below10_E": sum(1 for x in vals if x["x"] and x["x"] < 10 and x["E"])}
            allv[cfg] += vals
        for on, off, k in (("d3_w_log", "d3_w", "기본"), ("d3_w_log_P", "d3_w_P", "P 고정")):
            for r, v in cs.get(on, {}).items():
                w = cs.get(off, {}).get(r)
                if w and v.get("frame_ms") and w.get("frame_ms"):
                    pairs[k].append({"batch": lab, "r": r, "d_ms": round(v["frame_ms"] - w["frame_ms"], 3),
                                     "E": ecore(v) or ecore(w)})
        s["batches"][lab] = b
    for cfg, vals in allv.items():
        xs = [x["x"] for x in vals if x["x"]]
        ne = [x["x"] for x in vals if x["x"] and not x["E"]]
        s["all"][cfg] = {"n": len(xs), "median_x": st.median(xs) if xs else None,
                         "median_ms": st.median([x["ms"] for x in vals if x["ms"]]) if xs else None,
                         "median_x_noE": st.median(ne) if ne else None, "below10": sum(1 for x in xs if x < 10),
                         "E": sum(1 for x in vals if x["E"]),
                         "cpu_median": {n: st.median([x["cpu"][n] for x in vals if x["cpu"].get(n) is not None])
                                        for n in (vals[0]["cpu"] if vals else {})}}
    for k, ps in pairs.items():
        ne = [p["d_ms"] for p in ps if not p["E"]]
        s["pairs"][k] = {"pairs": ps, "median_noE_ms": st.median(ne) if ne else None, "n_noE": len(ne)}
    (out / (a.name or "summary.json")).write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    for lab, b in s["batches"].items():
        for cfg, v in b.items():
            print(lab, cfg, [f"{x['x']}{'E' if x['E'] else ''}" for x in v["runs"]], "med", v["median_x"], v["median_ms"])
    for cfg, v in s["all"].items():
        print("ALL", cfg, {k: v[k] for k in ("n", "median_x", "median_ms", "median_x_noE", "below10", "E")}, v["cpu_median"])
    for k, v in s["pairs"].items():
        print("Logger 비용", k, v["median_noE_ms"], v["n_noE"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", default="qa/out/perf_g")
    r.add_argument("--label", required=True)
    r.add_argument("--repeat", type=int, default=6)
    r.add_argument("--base-port", type=int, default=44000)   # 49152~ 임시 포트 범위를 피한다
    r.add_argument("--max-sys", type=float, default=5.0, help="시작 조건: 시스템 CPU %% 이하가 30 s")
    r.add_argument("--only", default="", help="CFGS 가운데 일부만 (QA 37차: P 고정 둘만)")
    sm = sub.add_parser("summary")
    sm.add_argument("--out", default="qa/out/perf_g")
    sm.add_argument("--labels", default="", help="쉼표로 구분한 묶음 폴더. 비우면 모두")
    sm.add_argument("--name", default="", help="요약 파일 이름 (기본 summary.json)")
    a = ap.parse_args()
    return run(a) if a.cmd == "run" else summary(a)


if __name__ == "__main__":
    sys.exit(main())

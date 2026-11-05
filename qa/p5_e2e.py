"""P5 임무장비 종단 시험 (TC-QA-031~036, DEC-046, DEC-047, DEC-009, DEC-012, DEC-018).

Logger·Datalink·Agent(관찰용 MA, qa/p5_probe_agent.py)·Bridge·Core를 실제 프로세스로 띄우고
버스 관측으로 탐지·SENSOR 고장·엔티티 수명 주기·재밍 구역을 확인한다.

uv run python qa/p5_e2e.py --mode lockstep --out qa/out/p5/l1 --fault
uv run python qa/p5_e2e.py --mode lockstep --out qa/out/p5/d1 --frames 80000   (결정성용, 고장 주입 없음)
uv run python qa/p5_e2e.py --mode realtime --scenario qa/scenarios/qa_p5_near.json --out qa/out/p5/rt --fault --ui
uv run python qa/p5_e2e.py --compare qa/out/p5/d1 qa/out/p5/d2
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import pickle
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "scenario/examples/p5_payload_demo_5.json"


class P5Stack(h.Stack):
    def __init__(self, *a, probe_out: Path, **k) -> None:  # noqa: ANN002, ANN003
        super().__init__(*a, **k)
        self.probe_out = probe_out

    def _cmd(self, name: str) -> list[str]:
        c = super()._cmd(name)
        if name == "agent":
            os.environ["P5_PROBE_OUT"] = str(self.probe_out)
            c = [sys.executable, str(Path(__file__).parent / "p5_probe_agent.py"), *c[3:]]
        return c


class P5Observer(h.Observer):
    def __init__(self, endpoints: list[str]) -> None:
        super().__init__(endpoints, jump_m=2000.0)
        from swarm.v1 import ms_pb2
        self.ms = ms_pb2
        self.keep_traj = True
        self.det: list[tuple[int, str, str, float]] = []
        self.sact: list[tuple[int, str, str, bool]] = []
        self.stk: list[tuple[int, str, str, str, str]] = []
        self.lo: list[tuple[int, str, str, str, str]] = []  # (frame, src, dst, kind, reason)
        self.subs += [
            self.bus.subscribe("onboard/*/Detection", self._det),
            self.bus.subscribe("onboard/*/SensorActivity", self._sact),
            self.bus.subscribe("onboard/*/StrikeActivity", self._stk),
        ]

    def _det(self, s) -> None:  # noqa: ANN001
        d = self.ms.Detection.FromString(s.payload)
        with self.lock:
            self.det.append((d.header.frame, s.key.split("/")[1], d.target_id, d.range_m))

    def _sact(self, s) -> None:  # noqa: ANN001
        a = self.ms.SensorActivity.FromString(s.payload)
        with self.lock:
            self.sact.append((a.header.frame, s.key.split("/")[1], a.payload_id, a.active))

    def _stk(self, s) -> None:  # noqa: ANN001
        a = self.ms.StrikeActivity.FromString(s.payload)
        with self.lock:
            self.stk.append((a.header.frame, s.key.split("/")[1], a.payload_id,
                             self.ms.StrikeState.Name(a.state), a.reason))

    def _outcome(self, s) -> None:  # noqa: ANN001
        super()._outcome(s)
        sim, truth, link, *_ = self.m
        o = link.LinkOutcome.FromString(s.payload)
        kind = link.LinkOutcomeKind.Name(o.outcome).removeprefix("LINK_OUTCOME_KIND_")
        reason = link.DropReason.Name(o.reason).removeprefix("DROP_REASON_") if kind == "DROPPED" else ""
        with self.lock:
            self.lo.append((o.tx_time_us // 20000, o.src, o.dst, kind, reason))

    def parsed_events(self) -> list[tuple[str, object, bytes]]:
        sim, truth, *_ = self.m
        with self.lock:
            evs = list(self.events)
        return [(k, truth.TruthEvent.FromString(p), p) for k, p in evs]

    def close(self) -> None:
        for s in self.subs:
            try:
                s.close()
            except Exception:  # noqa: BLE001
                pass
        self.bus.close()


def inside(zone: dict, lat: float, lon: float) -> bool:
    return h.dist_m((lat, lon), (zone["lat"], zone["lon"])) <= zone["r"]


def analyse(ob: P5Observer, probe: dict, fault: dict | None, dt_us: int) -> dict:
    sim, truth, link, *_ = ob.m
    evs = ob.parsed_events()
    r: dict = {"snapshot": ob.snapshot()}
    kinds = Counter(e.WhichOneof("event") for _, e, _ in evs)
    r["event_kinds"] = dict(kinds)
    r["events"] = []
    for k, e, _ in evs:
        w = e.WhichOneof("event")
        x = getattr(e, w)
        row = {"f": e.header.frame, "key": k, "kind": w}
        if w == "launch":
            row |= {"shooter": x.shooter, "weapon": x.weapon_entity, "target": x.target_id}
        elif w == "impact":
            row |= {"weapon": x.weapon_entity, "lethal_r": x.lethal_radius_m, "killed": list(x.killed),
                    "alt": round(x.position.alt_m, 1)}
        elif w == "kill":
            row |= {"entity": x.entity_id, "cause": x.cause}
        elif w == "spawn":
            row |= {"entity": x.entity.id, "kind_e": x.entity.kind}
        elif w == "jam_zone":
            c = x.area.circle if x.HasField("area") else x.zone
            row |= {"owner": x.owner, "active": x.active, "lat": c.center.lat_deg, "lon": c.center.lon_deg,
                    "r": c.radius_m, "alt": [x.area.min_alt_m, x.area.max_alt_m]}
        r["events"].append(row)
    # 1. 탐지: 버스(Core 발행) 대 MS 포트(관찰용 MA) ------------------------------
    bus_det = Counter((e, t) for _, e, t, _ in ob.det)
    r["det_bus"] = {f"{e}>{t}": n for (e, t), n in sorted(bus_det.items())}
    r["det_ms"] = {k: v["n"] for k, v in sorted(probe.get("det", {}).items())}
    r["det_min_range"] = {k: round(v["min_range"], 1) for k, v in sorted(probe.get("det", {}).items())}
    # 2. SENSOR 고장 ----------------------------------------------------------
    if fault:
        e = fault["entity"]
        inactive = sorted(f for f, ent, _, act in ob.sact if ent == e and not act)
        r["fault"] = dict(fault)
        if inactive:
            a0, a1 = inactive[0], inactive[-1]
            during = [f for f, ent, *_ in ob.det if ent == e and a0 <= f <= a1]
            after = [f for f, ent, *_ in ob.det if ent == e and f > a1]
            before = [f for f, ent, *_ in ob.det if ent == e and f < a0]
            r["fault"] |= {"inactive_first": a0, "inactive_last": a1, "inactive_msgs": len(inactive),
                           "det_before": len(before), "det_during": len(during), "det_after": len(after),
                           "first_det_after": after[0] if after else None,
                           "ms_runs": probe.get("det_frames", {}).get(e, [])}
        else:
            r["fault"]["inactive_msgs"] = 0
    r["sensor_activity_rate"] = dict(Counter(ent for _, ent, _, _ in ob.sact))
    # 3. 수명 주기 ------------------------------------------------------------
    life = {}
    for w in {row["weapon"] for row in r["events"] if row["kind"] == "launch"}:
        tr = ob.traj.get(w, [])
        L = {"frames_in_truth": len(tr)}
        if tr:
            L["first_frame"], L["last_frame"] = tr[0][0], tr[-1][0]
            L["path_m"] = round(sum(h.dist_m(a[1:3], b[1:3]) for a, b in zip(tr, tr[1:])), 1)
            L["alt_start_end"] = (round(tr[0][3], 1), round(tr[-1][3], 1))
        life[w] = L
    r["weapons"] = life
    r["alive_final"] = {k: v for k, v in sorted(ob.alive.items())}
    r["strike_activity"] = ob.stk
    r["probe_cmds"] = probe.get("cmds", [])[:40]
    r["probe_cmd_n"] = len(probe.get("cmds", []))
    r["probe_acts"] = probe.get("acts", [])
    r["assign"] = probe.get("assign", {})
    # 4. 재밍 ----------------------------------------------------------------
    zones = [row for row in r["events"] if row["kind"] == "jam_zone" and row["active"]]
    if zones:
        z = zones[0]
        pos_at: dict[str, dict[int, tuple[float, float]]] = {k: {f: (la, lo) for f, la, lo, _ in v}
                                                            for k, v in ob.traj.items()}
        cnt = Counter()
        for f, src, dst, kind, reason in ob.lo:
            p = pos_at.get(dst, {}).get(f)
            ps = pos_at.get(src, {}).get(f)
            if p is None:
                cnt["no_pos"] += 1
                continue
            dst_in = inside(z, *p)
            src_in = ps is not None and inside(z, *ps)
            tag = "dst_in" if dst_in else ("src_in_only" if src_in else "out")
            cnt[f"{tag}:{kind}:{reason}"] += 1
        r["jam"] = {"zone": z, "outcomes": dict(sorted(cnt.items()))}
        frames_in = Counter()
        for k, v in pos_at.items():
            if k.startswith("uav"):
                frames_in[k] = sum(1 for la, lo in v.values() if inside(z, la, lo))
        r["jam"]["uav_frames_in_zone"] = dict(frames_in)
    return r


def run(a: argparse.Namespace) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sc = Path(a.scenario)
    probe_out = out / "probe.json"
    st = P5Stack(out / "stack", sc, base_port=a.base_port, lockstep=(a.mode == "lockstep"), rate=a.rate,
                 record=a.record, bridge=a.bridge, probe_out=probe_out)
    web = []
    t0 = time.monotonic()
    fault = None
    try:
        # JamZone은 첫 프레임에 한 번만 나오므로 Core보다 먼저 관측자를 붙인다
        if st.record:
            st.start_one("logger")
        st.start_one("datalink")
        st.start_one("agent")
        if st.bridge:
            st.start_one("bridge")
        ob = P5Observer([st.endpoint()])
        if a.ui:
            for name, port in (("ui", 45173),):
                web.append(subprocess.Popen(["npm.cmd", "run", "dev", "--", "--port", str(port), "--strictPort"],
                                            cwd=str(ROOT / name), stdout=open(out / f"{name}.log", "w"),
                                            stderr=subprocess.STDOUT))
            # 브라우저가 브리지에 붙을 때까지 Core 시작을 미룬다 (out/go 파일)
            go = out / "go"
            go.unlink(missing_ok=True)
            print("waiting for go file", go, flush=True)
            end = time.monotonic() + 600
            while not go.exists() and time.monotonic() < end:
                time.sleep(0.5)
        time.sleep(st.settle + 1.0)
        st.start_one("core")
        t0 = time.monotonic()
        print(f"ready endpoint {st.endpoint()} bridge {st.bridge_port if a.bridge else '-'}", flush=True)
        last_print = 0.0
        launch_seen_at = None
        while True:
            time.sleep(0.5)
            with ob.lock:
                lf = ob.last_frame or 0
                ndet = Counter(e for _, e, _, _ in ob.det[-2000:])
                nlaunch = sum(1 for k, _ in ob.events if k.endswith("launch"))
                nimpact = sum(1 for k, _ in ob.events if k.endswith("impact"))
            sim_s = lf * 0.02
            # SENSOR 고장: 탐지가 이어지는 기체 하나에 고장을 주고 a.fault_s(시뮬레이션 초) 뒤 해제한다
            if a.fault and fault is None:
                cand = [e for e in ("uav-004", "uav-002", "uav-005", "uav-001", "uav-003") if ndet.get(e, 0) >= 50]
                if cand:
                    fault = {"entity": cand[0], "inject_frame_obs": lf, "wall": round(time.monotonic() - t0, 1)}
                    ob.fault(cand[0], "SENSOR")
                    print(f"fault SENSOR {cand[0]} at obs frame {lf}", flush=True)
            elif fault and "clear_frame_obs" not in fault and lf - fault["inject_frame_obs"] >= a.fault_s * 50:
                ob.fault(fault["entity"], "SENSOR", clear=True)
                fault["clear_frame_obs"] = lf
                print(f"clear SENSOR {fault['entity']} at obs frame {lf}", flush=True)
            if nlaunch and launch_seen_at is None:
                launch_seen_at = sim_s
            if time.monotonic() - last_print > 15:
                last_print = time.monotonic()
                print(f"{time.monotonic() - t0:6.0f}s frame {lf} sim {sim_s:.0f}s det {dict(ndet)} "
                      f"launch {nlaunch} impact {nimpact} dead {st.dead()}", flush=True)
            if a.frames and lf >= a.frames:
                break
            if not a.frames and nlaunch and nimpact >= nlaunch and sim_s - (launch_seen_at or 0) > 20 \
                    and (not a.fault or (fault and "clear_frame_obs" in fault and lf - fault["clear_frame_obs"] > 250)):
                if a.hold_s <= 0:
                    break
                print(f"done; holding {a.hold_s}s for UI", flush=True)
                time.sleep(a.hold_s)
                break
            if sim_s >= a.until_s or time.monotonic() - t0 > a.wall_s or st.dead():
                print(f"stop: sim {sim_s:.0f} wall {time.monotonic() - t0:.0f} dead {st.dead()}", flush=True)
                break
        time.sleep(1.0)
        probe = json.loads(probe_out.read_text(encoding="utf-8")) if probe_out.exists() else {}
        res = analyse(ob, probe, fault, 20000)
        res["mode"], res["scenario"], res["wall_s"] = a.mode, str(sc), round(time.monotonic() - t0, 1)
        res["log_issues"] = h.scan_logs(st)
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        with gzip.open(out / "trace.pkl.gz", "wb") as f:
            with ob.lock:
                pickle.dump({"traj": dict(ob.traj), "events": [(k, p) for k, p in ob.events]}, f)
        print(json.dumps({k: res[k] for k in ("event_kinds", "det_bus", "det_ms", "weapons", "assign")},
                         ensure_ascii=False, default=str), flush=True)
        ob.close()
    finally:
        for w in web:
            subprocess.run(["taskkill", "/PID", str(w.pid), "/T", "/F"], capture_output=True)
        st.down()


def compare(a_dir: Path, b_dir: Path, upto: int) -> None:
    sys.path.insert(0, str(ROOT / "api/python/src"))
    from swarm.v1 import truth_pb2
    A = pickle.load(gzip.open(a_dir / "trace.pkl.gz"))
    B = pickle.load(gzip.open(b_dir / "trace.pkl.gz"))
    bad, worst, first = 0, 0.0, None
    ids = sorted(set(A["traj"]) | set(B["traj"]))
    only = [k for k in ids if k not in A["traj"] or k not in B["traj"]]
    for k in ids:
        ta = {f: p for f, *p in A["traj"].get(k, []) if f <= upto}
        tb = {f: p for f, *p in B["traj"].get(k, []) if f <= upto}
        if set(ta) != set(tb):
            print(f"{k}: 프레임 집합 다름 {len(ta)} vs {len(tb)}")
        for f in sorted(set(ta) & set(tb)):
            d = h.dist_m(ta[f][:2], tb[f][:2]) + abs(ta[f][2] - tb[f][2])
            if d > 1e-9:
                bad += 1
                worst = max(worst, d)
                first = f if first is None else min(first, f)

    def ev(X):
        return [(k, p) for k, p in X["events"] if truth_pb2.TruthEvent.FromString(p).header.frame <= upto]
    ea, eb = ev(A), ev(B)
    same = ea == eb
    print(json.dumps({"entities": len(ids), "only_one_side": only, "pos_mismatch": bad, "worst_m": worst,
                      "first_frame": first, "events": [len(ea), len(eb)], "events_identical": same,
                      "event_kinds": dict(Counter(k for k, _ in ea))}, ensure_ascii=False))
    if not same:
        for i, (x, y) in enumerate(zip(ea, eb)):
            if x != y:
                print("첫 이벤트 차이", i, x[0], y[0], truth_pb2.TruthEvent.FromString(x[1]),
                      truth_pb2.TruthEvent.FromString(y[1]))
                break


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="lockstep", choices=["lockstep", "realtime"])
    ap.add_argument("--scenario", default=str(EXAMPLE))
    ap.add_argument("--out", default=str(ROOT / "qa/out/p5/run"))
    ap.add_argument("--base-port", type=int, default=48300)
    ap.add_argument("--rate", type=float, default=0.0)
    ap.add_argument("--frames", type=int, default=0, help="이 프레임까지 관측하고 끝낸다(결정성용)")
    ap.add_argument("--until-s", type=float, default=2000.0)
    ap.add_argument("--wall-s", type=float, default=1500.0)
    ap.add_argument("--fault", action="store_true")
    ap.add_argument("--fault-s", type=float, default=10.0)
    ap.add_argument("--bridge", action="store_true")
    ap.add_argument("--ui", action="store_true")
    ap.add_argument("--hold-s", type=float, default=0.0)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--compare", nargs=2)
    ap.add_argument("--upto", type=int, default=10**9)
    a = ap.parse_args()
    if a.compare:
        compare(Path(a.compare[0]), Path(a.compare[1]), a.upto)
    else:
        run(a)


if __name__ == "__main__":
    main()

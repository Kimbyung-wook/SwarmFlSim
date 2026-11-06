"""TC-QA-055~056: StrikeActivity 변화 보고 10 Hz 상한 (DEC-051, DEC-056, TC-QA-047 보완).

정지 사수(uav-001, sta1 agm_short 6발, sta2 agm_short 2발)가 평지(0 m)의 정지 지상 표적에 프레임 단위로 붙인
StrikeCommand를 낸다. (StrikeActivity, payload_id) 키가 0.1 s 안에 여러 번 바뀌게 한다.
- 묶음 A: sta1에 20 ms 간격 4연속 (발사·발사·거부 unknown_target·거부 out_of_range)
- 묶음 B: sta1의 1·2번 무장이 20 ms 간격으로 명중할 때 같은 프레임에 sta1 3번 발사, sta2는 명중 40 ms 뒤 발사
  (명중 프레임은 1차 실행에서 잰다: --impact-from 결과 파일)
- 대조: sta2 단발 발사(키 하나에 변화 한 번)

Core가 낸 onboard/<id>/StrikeActivity(진실)와 GCS가 받은 swarm/gcs-01/rx/ms/StrikeActivity를 견준다.
Agent `--activity-max-hz 10`(기본)과 `0`을 비교한다. 링크 손실은 0으로 둔다.

uv run python qa/strike_burst.py --out qa/out/burst/p1 --hz 0                       (1차: 명중 프레임 측정)
uv run python qa/strike_burst.py --out qa/out/burst/h10 --hz 10 --impact-from qa/out/burst/p1
uv run python qa/strike_burst.py --out qa/out/burst/h0 --hz 0 --impact-from qa/out/burst/p1
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
from p5_e2e import P5Observer  # noqa: E402

SCN = Path(__file__).resolve().parent / "scenarios"
M_LAT = 111_320.0
SH = (37.5, 128.0, 500.0)


def at(dn: float, de: float) -> dict:
    return {"lat_deg": round(SH[0] + dn / M_LAT, 7),
            "lon_deg": round(SH[1] + de / (M_LAT * math.cos(math.radians(SH[0]))), 7), "alt_m": 0.0}


def scenario() -> dict:
    tg = {"tgt-a": (1000, 0), "tgt-b": (1000, 60), "tgt-c": (1200, -200), "tgt-d": (1500, 300),
          "tgt-e": (1500, -300), "tgt-far": (7000, 0)}
    ents = [{"id": "gcs-01", "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {**at(-2000, 0), "alt_m": 30.0}}, "link_profile": "gcs_default"},
            {"id": "uav-001", "kind": "uav", "side": "blue", "dynamics": "static",
             "initial": {"position": {**at(0, 0), "alt_m": SH[2]}},
             "payloads": [{"id": "sta1", "type": "agm_short", "profile": "agm_generic", "count": 6},
                          {"id": "sta2", "type": "agm_short", "profile": "agm_generic", "count": 2}],
             "autonomy": {"ma_plugin": "flocking_basic", "ma_params": {"group": "alpha"}},
             "link_profile": "uav_default", "controlling_gcs": "gcs-01"}]
    for tid, (dn, de) in tg.items():
        ents.append({"id": tid, "kind": "ground_target", "side": "red", "dynamics": "static",
                     "initial": {"position": at(dn, de)}})
    noloss = {"p_gb": 0.0, "p_bg": 1.0, "loss_good": 0.0, "loss_bad": 0.0}
    return {"schema_version": "0.1", "name": "qa-burst", "description": "TC-QA-055~056 StrikeActivity 10 Hz 상한",
            "map": {"origin": at(0, 0), "extent": {"south_deg": 37.4, "north_deg": 37.6, "west_deg": 127.9,
                                                   "east_deg": 128.1}},
            "run": {"mode": "lockstep", "frame_hz": 50, "seed": 20261106, "rate": 20.0, "duration_s": 600.0},
            "link_profiles": [{"name": "uav_default", "ge": noloss}, {"name": "gcs_default", "ge": noloss}],
            "entities": ents, "mission_plan": {"plan_id": "plan-burst", "tasks": []}}


F0 = 100  # 묶음 A 시작 MA 프레임


def plan(impact: dict | None) -> list[dict]:
    p = [{"f": F0, "e": "uav-001", "pid": "sta1", "tgt": "tgt-a"},
         {"f": F0 + 1, "e": "uav-001", "pid": "sta1", "tgt": "tgt-b"},
         {"f": F0 + 2, "e": "uav-001", "pid": "sta1", "tgt": "tgt-none"},
         {"f": F0 + 3, "e": "uav-001", "pid": "sta1", "tgt": "tgt-far"},
         {"f": F0 + 50, "e": "uav-001", "pid": "sta2", "tgt": "tgt-c"}]
    if impact:
        lat = impact["cmd_latency_frames"]
        p.append({"f": impact["w01"] - lat, "e": "uav-001", "pid": "sta1", "tgt": "tgt-d"})
        p.append({"f": impact["sta2_w"] - lat + 2, "e": "uav-001", "pid": "sta2", "tgt": "tgt-e"})
    return p


class BurstStack(h.Stack):
    def _cmd(self, name: str) -> list[str]:
        c = super()._cmd(name)
        if name == "agent":
            c = [sys.executable, str(Path(__file__).parent / "strike_burst_agent.py"), *c[3:]]
        return c


class BurstObserver(P5Observer):
    def __init__(self, endpoints: list[str]) -> None:
        super().__init__(endpoints)
        self.core: list[dict] = []
        self.rx: list[dict] = []

    def _stk(self, s) -> None:  # noqa: ANN001
        a = self.ms.StrikeActivity.FromString(s.payload)
        with self.lock:
            self.core.append({"f": a.header.frame, "t_us": a.header.sim_time_us, "e": s.key.split("/")[1],
                              "pid": a.payload_id, "state": self.ms.StrikeState.Name(a.state)[13:],
                              "reason": a.reason, "weapon": a.weapon_entity})

    def _gact(self, s) -> None:  # noqa: ANN001
        sim, truth, link, *_ = self.m
        if not s.key.endswith("/StrikeActivity"):
            return
        env = link.LinkEnvelope.FromString(s.payload)
        a = self.ms.StrikeActivity.FromString(env.payload)
        with self.lock:
            self.rx.append({"obs_f": self.last_frame or 0, "src": env.header.source, "seq": env.header.seq,
                            "env_f": env.header.frame, "rx_us": env.rx_time_us, "f": a.header.frame,
                            "t_us": a.header.sim_time_us, "pid": a.payload_id,
                            "state": self.ms.StrikeState.Name(a.state)[13:], "reason": a.reason,
                            "weapon": a.weapon_entity})


def sig(r: dict) -> tuple:
    return (r["pid"], r["state"], r["reason"], r["weapon"])


def analyse(core: list[dict], rx: list[dict], probe: dict) -> dict:
    """Core 변화(키별 상태 열)와 GCS 수신 열을 견준다"""
    out: dict = {}
    by_pid_core, by_pid_rx = defaultdict(list), defaultdict(list)
    for r in core:
        by_pid_core[r["pid"]].append(r)
    for r in sorted(rx, key=lambda r: (r["rx_us"], r["seq"])):
        by_pid_rx[r["pid"]].append(r)
    for pid in sorted(by_pid_core):
        cs = by_pid_core[pid]
        rs = by_pid_rx.get(pid, [])
        # GCS가 받은 서로 다른 변화(같은 본문이 이어지면 주기 재전송)
        rx_changes = []
        for r in rs:
            if not rx_changes or sig(rx_changes[-1]) != sig(r):
                rx_changes.append(r)
        rows = []
        for c in cs:
            first = next((r for r in rs if sig(r) == sig(c) and r["t_us"] == c["t_us"]), None)
            same_body = next((r for r in rs if sig(r) == sig(c) and r["rx_us"] >= c["t_us"]), None)
            rows.append({"core_f": c["f"], "t_s": c["t_us"] / 1e6, "state": c["state"], "reason": c["reason"],
                         "weapon": c["weapon"],
                         "gcs_first_rx_s": round(first["rx_us"] / 1e6, 3) if first else None,
                         "gcs_same_body_rx_s": round(same_body["rx_us"] / 1e6, 3) if same_body else None,
                         "delay_ms": round((first["rx_us"] - c["t_us"]) / 1e3, 1) if first else None})
        last_core, last_rx = cs[-1], (rs[-1] if rs else None)
        out[pid] = {"core_changes": len(cs), "rx_msgs": len(rs), "rx_distinct_changes": len(rx_changes),
                    "lost": [f"{r['core_f']}:{r['state']}:{r['reason'] or r['weapon']}" for r in rows
                             if r["gcs_same_body_rx_s"] is None],
                    "last_core": sig(last_core), "last_rx": sig(last_rx) if last_rx else None,
                    "last_delivered": bool(last_rx and sig(last_rx) == sig(last_core)), "rows": rows,
                    "rx_seq": [(round(r["rx_us"] / 1e6, 3), r["state"], r["reason"] or r["weapon"]) for r in rs]}
    # 같은 Core 프레임에 같은 키 변화가 둘 이상인 경우
    per_frame = defaultdict(list)
    for r in core:
        per_frame[(r["e"], r["pid"], r["f"])].append(f"{r['state']}:{r['reason'] or r['weapon']}")
    out["same_frame_multi"] = {f"{k[1]}@{k[2]}": v for k, v in per_frame.items() if len(v) > 1}
    # Agent MS 포트가 받은 것 (MA 쪽은 상한과 무관해야 한다)
    out["ma_port_n"] = len(probe.get("acts", []))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--impact-from")
    ap.add_argument("--frames", type=int, default=2500)
    ap.add_argument("--base-port", type=int, default=48400)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    impact = None
    if a.impact_from:
        impact = json.loads((Path(a.impact_from) / "result.json").read_text(encoding="utf-8"))["impact"]
    pl = plan(impact)
    sp = SCN / "qa_burst.json"
    sp.write_text(json.dumps(scenario(), ensure_ascii=False, indent=1), encoding="utf-8")
    probe_out = out / "probe.json"
    os.environ["BURST_OUT"] = str(probe_out)
    os.environ["BURST_PLAN"] = json.dumps(pl)
    st = BurstStack(out / "stack", sp, base_port=a.base_port, lockstep=True, rate=20.0, record=False,
                    core_extra=["--terrain-flat", "0", "--frames", str(a.frames)])
    res: dict = {"hz": a.hz, "plan": pl}
    try:
        st.start_one("datalink")
        st.start_one("agent", ["--activity-max-hz", str(a.hz)])
        time.sleep(st.settle)
        ob = BurstObserver([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 600:
            time.sleep(1.0)
            if (ob.last_frame or 0) >= a.frames - 1 or "core" in "".join(st.dead()):
                break
        time.sleep(1.5)
        with ob.lock:
            core, rx = list(ob.core), list(ob.rx)
            act_lo = list(ob.act_lo)
        probe = json.loads(probe_out.read_text(encoding="utf-8")) if probe_out.exists() else {}
        res["last_frame"] = ob.last_frame
        res["core"] = core
        res["rx_n"] = len(rx)
        res["drops"] = [x for x in act_lo if x[4] != "DELIVERED"]
        res["probe_cmds"] = probe.get("cmds")
        res["analysis"] = analyse(core, rx, probe)
        # 명중 프레임과 명령 지연 (2차 실행 일정용)
        launch = {r["weapon"]: r["f"] for r in core if r["state"] == "LAUNCHED"}
        imp = {r["weapon"]: r["f"] for r in core if r["state"] in ("IMPACT", "MISSED")}
        w1 = "wpn-uav-001-01"
        lat = launch.get(w1, 0) - F0 if w1 in launch else None
        sta2_w = next((r["weapon"] for r in core if r["pid"] == "sta2" and r["state"] == "LAUNCHED"), None)
        res["impact"] = {"cmd_latency_frames": lat, "w01": imp.get(w1), "launch": launch, "end": imp,
                         "sta2_w": imp.get(sta2_w) if sta2_w else None}
        res["log_issues"] = h.scan_logs(st)
        with open(out / "rx.json", "w", encoding="utf-8") as f:
            json.dump(rx, f, ensure_ascii=False)
        ob.close()
    finally:
        st.down()
    txt = json.dumps(res, ensure_ascii=False, indent=1, default=str)
    (out / "result.json").write_text(txt, encoding="utf-8")
    an = res["analysis"]
    print(json.dumps({"hz": a.hz, "impact": res["impact"], "drops": len(res["drops"]),
                      **{k: {kk: v[kk] for kk in ("core_changes", "rx_distinct_changes", "lost", "last_delivered")}
                         for k, v in an.items() if k.startswith("sta")},
                      "same_frame_multi": an["same_frame_multi"]}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()

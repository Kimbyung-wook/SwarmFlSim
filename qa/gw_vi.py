"""QA 16차 VI·위치 분석 (TC-QA-078~083, DEC-071~073). `qa/gw_integ.py`가 부른다.

입력
- extj: 외부 클라이언트 기록(qa/gw_ext_client.py). rx 행 = [epoch, name, topic, xsd_ok, sysid, mode, extra]
- vi_rx: 관찰자가 GCS rx에서 푼 VI·PeerStatus (epoch, sim_s, msg, src, hdr_us, ...)
- traj: truth 궤적 {entity: [(frame, lat, lon, alt)]}. QA 비교용으로만 쓴다
"""
from __future__ import annotations

import datetime as dt
import math
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

M_LAT = 111_320.0
VI_NAMES = ("MA_NavigationReport", "SystemStatus", "MA_FlightCommandStatus", "MA_FlightCapability")
UAVS = ("uav-001", "uav-002", "uav-003", "uav-004", "uav-005")


def sim_at(clock: list, epoch: float) -> float:
    """epoch → 모의 s (표본 사이 선형 보간)"""
    prev = None
    for e, s in clock:
        if e >= epoch:
            if prev is None or e == prev[0]:
                return s
            return prev[1] + (s - prev[1]) * (epoch - prev[0]) / (e - prev[0])
        prev = (e, s)
    return clock[-1][1] if clock else 0.0


def stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    s = sorted(xs)
    return {"n": len(s), "mean": round(st.fmean(s), 2), "p50": round(s[len(s) // 2], 2),
            "p95": round(s[min(len(s) - 1, int(0.95 * len(s)))], 2), "max": round(s[-1], 2)}


def iso_epoch(ts: str) -> float | None:
    try:
        return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


def ready_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "gateway: ready at" in ln or "not ready yet" in ln or "XSD loaded" in ln:
            out.append(re.sub(r"\s+", " ", ln)[:220])
    return out


def analyse(res: dict, extj: dict, vi_rx: list, traj: dict, clock: list, gw_logs: dict) -> dict:  # noqa: C901, PLR0912, PLR0915
    m = res["marks"]
    S: dict = {}
    rx = extj["rx"]
    kill_e = m.get("gw_kill", 1e20)
    up_e = m.get("gw2_ready_log", m.get("gw2_connected", m.get("gw_up", 1e20)))
    alive = lambda e: e < kill_e or e >= up_e  # noqa: E731
    t_last = clock[-1][1] if clock else 0.0

    # 1. 종류별 개수, XSD -----------------------------------------------------
    cnt, ok = Counter(), Counter()
    per_who = defaultdict(Counter)
    for r in rx:
        if r[1] in VI_NAMES or r[1] == "MA_PositionReport":
            k = r[1] if r[1] != "MA_PositionReport" else f"MA_PositionReport@{r[2]}"
            cnt[k] += 1
            ok[k] += bool(r[3])
            per_who[k][r[6].get("who", "")] += 1
    S["ext_counts"] = {k: {"n": cnt[k], "xsd_ok": ok[k], "by_vehicle": dict(sorted(per_who[k].items()))}
                       for k in sorted(cnt)}
    gin = defaultdict(Counter)
    for x in vi_rx:
        gin[x[2]][x[3]] += 1
    S["gcs_rx_counts"] = {k: dict(sorted(v.items())) for k, v in gin.items()}
    gin_up = defaultdict(Counter)
    for x in vi_rx:
        if alive(x[0]):
            gin_up[x[2]][x[3]] += 1
    S["gcs_rx_counts_gw_up"] = {k: sum(v.values()) for k, v in gin_up.items()}
    # NavigationReport 기대값: 기체 × 1 Hz × (모의 시간 − 그 기체의 GCS 차단 시간)
    cut = {e: 15.0 for e in UAVS}           # LINK_CUT gcs-01 15 s
    for e in ("uav-003", "uav-004"):
        cut[e] += 15.0                       # GCS_LINK_CUT 15 s
    exp_rx = {e: round(t_last - cut[e]) for e in UAVS}
    down_s = sim_at(clock, up_e) - sim_at(clock, kill_e) if kill_e < 1e19 else 0.0
    S["nav_expected"] = {"sim_s": round(t_last, 1), "gcs_rx_expected_by_vehicle": exp_rx,
                         "gcs_rx_expected_total": sum(exp_rx.values()),
                         "gw_down_sim_s": round(down_s, 1),
                         "ext_expected_total": round(sum(exp_rx.values()) - len(UAVS) * down_s)}
    # 2. 위치 비교 ----------------------------------------------------------
    tr = {e: {fr: (la, lo, al) for fr, la, lo, al in v} for e, v in traj.items()}
    internal = defaultdict(list)          # (src, kind) → [(lat, lon, alt, hdr_us, epoch)]
    for x in vi_rx:
        if x[2] in ("NavigationReport", "PeerStatus"):
            internal[(x[3], x[2])].append((x[5], x[6], x[7], x[4], x[0]))
    pos = {}
    for topic, kind in (("swarm.vi", "NavigationReport"), ("swarm.p2p", "PeerStatus")):
        rows = [r for r in rx if r[1] == "MA_PositionReport" and r[2] == topic]
        match = 0
        eh, ev, lag, conv, age, stale = [], [], [], [], [], []
        for r in rows:
            ex = r[6]
            cand = internal.get((ex.get("who", ""), kind), [])
            same = [c for c in cand if abs(c[0] - ex["lat"]) < 1e-9 and abs(c[1] - ex["lon"]) < 1e-9]
            if not same:
                continue
            # 정지 기체는 같은 좌표가 반복되므로 Timestamp에 가장 가까운 표본과 짝짓는다
            te = iso_epoch(ex.get("ts", "")) or r[0]
            hit = min(same, key=lambda c: abs(c[4] - te))
            match += 1
            conv.append(max(abs(hit[0] - ex["lat"]), abs(hit[1] - ex["lon"])) * M_LAT)
            fr = round(hit[3] / 20_000)
            t = tr.get(ex["who"], {}).get(fr)
            if t is not None:
                dn = (ex["lat"] - t[0]) * M_LAT
                de = (ex["lon"] - t[1]) * M_LAT * math.cos(math.radians(t[0]))
                eh.append(math.hypot(dn, de))
                ev.append(abs((ex["alt"] or 0.0) - t[2]))
            lag.append((te - hit[4]) * 1e3)
            s_rx = sim_at(clock, r[0])
            age.append(s_rx - hit[3] * 1e-6)
            t2 = tr.get(ex["who"], {}).get(round(s_rx * 50))
            if t2 is not None and ex["who"] != "uav-005":   # 이동 기체만: 외부 수신 시점의 truth와 견준 오차
                stale.append(math.hypot((ex["lat"] - t2[0]) * M_LAT,
                                        (ex["lon"] - t2[1]) * M_LAT * math.cos(math.radians(t2[0]))))
        pos[topic] = {"ext_n": len(rows), "matched_internal": match,
                      "conv_err_m_max": round(max(conv), 6) if conv else None,
                      "vs_truth_horiz_m": stats(eh), "vs_truth_vert_m": stats(ev),
                      "ts_minus_gcs_rx_ms": stats(lag), "age_at_ext_rx_s": stats(age),
                      "moving_vs_truth_at_ext_rx_horiz_m": stats(stale),
                      "has_velocity": sum(1 for r in rows if r[6].get("vel")),
                      "has_orientation": sum(1 for r in rows if r[6].get("ori"))}
    S["position"] = pos
    # 3. SystemStatus 변화 (고장 주입 uav-004) ---------------------------------
    f_on, f_off = (sim_at(clock, m[k]) if k in m else None for k in ("fault_on", "fault_off"))
    S["fault_sim_s"] = [round(f_on, 2) if f_on else None, round(f_off, 2) if f_off else None]
    seq, prev = [], None
    for x in vi_rx:
        if x[2] == "SystemStatus" and x[3] == "uav-004":
            key = (x[5], tuple(x[7]))
            if key != prev:
                seq.append({"sim_s": round(x[4] * 1e-6, 2), "health": x[5],
                            "subsystems": [f"{a}:{b}" for a, b in x[7] if b != "NOMINAL"]})
                prev = key
    S["sysstatus_gcs_uav004_changes"] = seq[:10]
    S["sysstatus_gcs_per_vehicle"] = dict(sorted(gin["SystemStatus"].items()))
    e_seq, prev = [], None
    for r in rx:
        if r[1] == "SystemStatus" and r[6].get("who") == "uav-004":
            stt = r[6].get("state")
            if stt != prev:
                e_seq.append({"sim_s": round(sim_at(clock, r[0]), 2), "SystemState": stt})
                prev = stt
    S["sysstatus_ext_uav004_changes"] = e_seq[:10]
    # 4. FlightCommandStatus -----------------------------------------------
    fcs = defaultdict(list)
    for x in vi_rx:
        if x[2] == "FlightCommandStatus":
            fcs[x[3]].append((round(x[4] * 1e-6, 2), x[5], x[6], x[7]))
    S["fcs_gcs"] = {e: {"n": len(v), "first": v[:4], "distinct": sorted({f"{c}:{s}" for _, c, s, _ in v})[:8]}
                    for e, v in sorted(fcs.items())}
    efcs = defaultdict(list)
    for r in rx:
        if r[1] == "MA_FlightCommandStatus":
            efcs[r[6].get("cmd", "")].append((round(sim_at(clock, r[0]), 2), r[6].get("state")))
    S["fcs_ext"] = {c: {"n": len(v), "first": v[:4]} for c, v in sorted(efcs.items())}
    S["ext_cmd_sim_s"] = {k: round(sim_at(clock, m[k]), 2) for k in ("ext1", "ext2", "cancel") if k in m}
    # 5. 구간별 VI 외부 발행률 -------------------------------------------------
    wins = {"base_40_55": (40, 55), "cut1_72_85": (72, 85), "mid_87_95": (87, 95), "cut2_97_110": (97, 110),
            "rec_112_120": (112, 120)}
    if kill_e < 1e19:
        wins["gw_down"] = (sim_at(clock, kill_e) + 0.5, sim_at(clock, up_e))
        wins["after_up"] = (sim_at(clock, up_e) + 2.0, t_last - 3.0)
    rx_sim = [(sim_at(clock, r[0]), r) for r in rx if r[1] in VI_NAMES or r[1] == "MA_PositionReport"]
    out = {}
    for w, (a0, a1) in wins.items():
        d = max(a1 - a0, 1e-6)
        sel = [r for s, r in rx_sim if a0 <= s < a1]
        c = Counter(r[1] if r[1] != "MA_PositionReport" else f"Pos@{r[2][6:]}" for r in sel)
        who = Counter(r[6].get("who", "") for r in sel if r[1] == "MA_NavigationReport")
        out[w] = {"sim_s": [round(a0, 1), round(a1, 1)], "per_s": {k: round(v / d, 2) for k, v in sorted(c.items())},
                  "nav_vehicles": sorted(who)}
    S["vi_windows"] = out
    # 6. 준비 로그와 그 뒤 명령 -------------------------------------------------
    S["ready_log"] = {g: ready_lines(p) for g, p in gw_logs.items()}
    if "gw2_ready_log" in m and "ext2" in m:
        S["ext2_after_ready_s"] = round(m["ext2"] - m["gw2_ready_log"], 3)
    S["gw2_ready_after_start_wall_s"] = round(m["gw2_ready_log"] - m["gw_up"], 2) \
        if "gw2_ready_log" in m and "gw_up" in m else None
    return S


if __name__ == "__main__":  # 저장된 원자료로 다시 분석: uv run python qa/gw_vi.py qa/out/gw16/r2
    import gzip
    import json
    import pickle
    import sys
    d = Path(sys.argv[1])
    with gzip.open(d / "raw.pkl.gz", "rb") as f:
        raw = pickle.load(f)
    ext = json.loads((d / "ext" / "ext.json").read_text(encoding="utf-8"))
    out = analyse(raw["res"], ext, raw["vi_rx"], raw["traj"], raw["clock"],
                  {g: d / "stack" / f"gateway.{g}.log" for g in (1, 2)})
    print(json.dumps(out["position"], ensure_ascii=False, indent=1))

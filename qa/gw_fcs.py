"""QA 17차 FlightCommandStatus 상태 흐름 분석 (TC-QA-085~088, D-28, IMP-AGT-033).

`qa/gw_integ.py`가 남긴 원자료(raw.pkl.gz, ext/ext.json)를 읽어 command_id별 상태 열을 요약한다.
  - 역행: ACCEPTED(1) < EXECUTING(2) < 종료(3) 순서가 뒤로 가는 경우
  - 반복: 같은 상태가 연달아 오는 경우
  - 마지막 상태

uv run python qa/gw_fcs.py qa/out/gw17/flock qa/out/gw17/wp
"""
from __future__ import annotations

import gzip
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gw_vi as V  # noqa: E402

RANK = {"ACCEPTED": 1, "EXECUTING": 2, "COMPLETED": 3, "CANCELLED": 3, "FAILED": 3, "REJECTED": 3}


def flow(rows: list[str]) -> dict:
    regress = sum(1 for a, b in zip(rows, rows[1:]) if RANK.get(b, 0) < RANK.get(a, 0))
    repeat = sum(1 for a, b in zip(rows, rows[1:]) if a == b)
    return {"seq": rows, "n": len(rows), "regress": regress, "repeat": repeat, "last": rows[-1] if rows else None}


def analyse(d: Path) -> dict:
    with gzip.open(d / "raw.pkl.gz", "rb") as f:
        raw = pickle.load(f)
    ext = json.loads((d / "ext" / "ext.json").read_text(encoding="utf-8"))
    res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    S, clock = res["summary"], raw["clock"]
    by_recv, by_hdr, times = defaultdict(list), defaultdict(list), defaultdict(list)
    for x in raw["vi_rx"]:                      # 수신 순서대로 쌓여 있다
        if x[2] == "FlightCommandStatus":
            by_recv[(x[3], x[5])].append(x[6])
            by_hdr[(x[3], x[5])].append((x[4], x[6]))
            times[(x[3], x[5])].append(round(x[4] * 1e-6, 2))
    cmds = {}
    for k, rows in sorted(by_recv.items()):
        hdr = [s for _, s in sorted(by_hdr[k], key=lambda r: r[0])]
        cmds[f"{k[0]}/{k[1]}"] = {**flow(rows), "t": times[k], "hdr_order_regress": flow(hdr)["regress"]}
    ext_cmds = defaultdict(list)
    for r in ext["rx"]:
        if r[1] == "MA_FlightCommandStatus":
            ext_cmds[r[6]["cmd"]].append((round(V.sim_at(clock, r[0]), 2), r[6]["state"]))
    drops = Counter((x[1], x[4], x[5]) for x in raw["lo"] if x[3] == "FlightCommandStatus" and x[4] != "DELIVERED")
    vi = S["vi"]
    return {
        "frames": S["frames"], "dead": S["dead_at_end"], "log_issues": S["log_issues"][:5],
        "ext_total": S["ext_rx_total"], "ext_xsd_ok": S["ext_xsd_ok"], "xsd_fail": S["ext_xsd_fail"][:3],
        "ext_by_uci": {k: v[0] for k, v in S["ext_rx_by_uci"].items() if v[0]},
        "gw": {g: {k: c.get(k, 0) for k in ("exported", "sent", "invalid", "send_failed", "internal_error")}
               for g, c in S["gw_counters"].items()},
        "rejections": S["gw_rejections"],
        "gcs_rx_counts_gw_up": vi["gcs_rx_counts_gw_up"],
        "nav_gcs": vi["gcs_rx_counts"]["NavigationReport"],
        "windows_nav": {w: v["per_s"].get("MA_NavigationReport", 0) for w, v in vi["vi_windows"].items()},
        "ss_ext_uav004": vi["sysstatus_ext_uav004_changes"],
        "position": {t: {k: p[k] for k in ("ext_n", "matched_internal", "conv_err_m_max", "vs_truth_horiz_m")}
                     for t, p in vi["position"].items()},
        "ext_cmd_sim_s": vi["ext_cmd_sim_s"], "ext2_after_ready_s": vi.get("ext2_after_ready_s"),
        "tc_outcomes": [(o["dst"], o["outcome"]) for o in S["taskcommand_outcomes"]],
        "taskstatus_ext": S["taskstatus_ext"], "behaviour_keys": {
            e: {k: b.get(k) for k in ("east_30_90_m", "home_dist_90_m")} for e, b in S["behaviour"].items()},
        "fcs_gcs": cmds,
        "fcs_totals": {"commands": len(cmds), "msgs": sum(c["n"] for c in cmds.values()),
                       "regress": sum(c["regress"] for c in cmds.values()),
                       "repeat": sum(c["repeat"] for c in cmds.values()),
                       "hdr_order_regress": sum(c["hdr_order_regress"] for c in cmds.values()),
                       "last": dict(Counter(c["last"] for c in cmds.values()))},
        "fcs_drops": {str(k): v for k, v in drops.items()},
        "fcs_ext": {k: v for k, v in sorted(ext_cmds.items())},
    }


if __name__ == "__main__":
    out = {}
    for a in sys.argv[1:]:
        d = Path(a)
        out[d.name] = analyse(d)
        (d / "fcs.json").write_text(json.dumps(out[d.name], ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, default=str))

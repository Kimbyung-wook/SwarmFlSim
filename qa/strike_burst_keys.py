"""TC-QA-056 재시험·TC-QA-057: StrikeActivity 무장별 보고 키 (DEC-063, IMP-AGT-031) 분석.

`qa/strike_burst.py` 결과 폴더(result.json의 core, rx.json)를 읽어 다음을 낸다.
- 키 (payload_id, weapon_entity)별 Core 변화와 GCS 첫 수신(지연), 빠진 변화
- 1 s 주기 보고(송신 틱 frame % 50 == 0)에 나온 키와 그 틱에 Agent가 아는 비행 중 무장(발사 프레임 < f ≤ 종료 프레임)의 비교,
  종료 상태를 보낸 뒤 다시 나온 키
- 변화 보고 간격: 같은 키 안 최소 간격, 서로 다른 키 사이 최소 간격(상한이 키별인지)

uv run python qa/strike_burst_keys.py qa/out/burst2/h10 [qa/out/burst2/h0 ...]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

FRAME_US = 20_000
PERIOD_FRAMES = 50
TERMINAL = {"IMPACT", "MISSED", "REJECTED"}


def key(r: dict) -> tuple[str, str]:
    return (r["pid"], r["weapon"])


def sig(r: dict) -> tuple:
    return (r["pid"], r["state"], r["reason"], r["weapon"])


def analyse(d: Path) -> dict:
    res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    rx = sorted(json.loads((d / "rx.json").read_text(encoding="utf-8")), key=lambda r: (r["rx_us"], r["seq"]))
    core = res["core"]
    out: dict = {"hz": res["hz"], "core_n": len(core), "rx_n": len(rx), "drops": res.get("drops")}
    # 1) 변화별 첫 수신
    rows, lost = [], []
    for c in core:
        first = next((r for r in rx if sig(r) == sig(c) and r["t_us"] == c["t_us"]), None)
        row = {"core_f": c["f"], "t_s": c["t_us"] / 1e6, "pid": c["pid"], "state": c["state"],
               "reason": c["reason"], "weapon": c["weapon"],
               "rx_s": round(first["rx_us"] / 1e6, 3) if first else None,
               "send_f": first["env_f"] if first else None,
               "delay_ms": round((first["rx_us"] - c["t_us"]) / 1e3, 1) if first else None}
        rows.append(row)
        if first is None:
            lost.append(f"{c['f']}:{c['pid']}:{c['state']}:{c['reason'] or c['weapon']}")
    out["rows"], out["lost"] = rows, lost
    # 키별 마지막 상태 전달
    last_core: dict = {}
    for c in core:
        last_core[key(c)] = sig(c)
    last_rx: dict = {}
    for r in rx:
        last_rx[key(r)] = sig(r)
    out["last_by_key"] = {f"{k[0]}/{k[1] or '-'}": {"core": v[1:3], "rx": last_rx.get(k, (None,) * 4)[1:3],
                                                     "ok": last_rx.get(k) == v} for k, v in last_core.items()}
    # 2) 1 s 주기 보고
    # Core 프레임 F의 변화는 Agent 틱 F+1에 도착하므로 송신 틱 f에서 알려진 것은 Core 프레임 < f 인 변화다
    launch = {c["weapon"]: c["f"] for c in core if c["state"] == "LAUNCHED"}
    end = {c["weapon"]: c["f"] for c in core if c["state"] in TERMINAL and c["weapon"]}
    by_send = defaultdict(list)
    for r in rx:
        by_send[r["env_f"]].append(r)
    periods, bad = [], []
    for f in sorted(by_send):
        if f % PERIOD_FRAMES:
            continue
        t = f * FRAME_US
        keys_sent = sorted({f"{r['pid']}/{r['weapon'] or '-'}:{r['state']}" for r in by_send[f]})
        flying = sorted(w for w, lf in launch.items() if lf < f <= end.get(w, 1 << 62))
        sent_w = sorted({r["weapon"] for r in by_send[f] if r["weapon"]})
        # 주기 틱에 같은 틱의 변화 보고가 섞일 수 있으므로 종료 상태는 그 틱 직전 20 ms 안의 변화만 허용
        stale = [r for r in by_send[f] if r["state"] in TERMINAL and not (t - FRAME_US <= r["t_us"] <= t)]
        periods.append({"f": f, "t_s": t / 1e6, "sent": keys_sent, "flying": flying})
        if sent_w != flying:
            bad.append({"f": f, "why": "비행 중 무장과 다름", "sent": sent_w, "flying": flying})
        if stale:
            bad.append({"f": f, "why": "종료 키 재보고", "sent": keys_sent})
    out["periods"], out["period_bad"] = periods, bad
    # 종료 상태를 보낸 키가 그 뒤에 다시 나오는가 (주기·변화 모두)
    term_sent: dict = {}
    reappear = []
    for r in rx:
        k = key(r)
        if k in term_sent and sig(r) == term_sent[k][0]:
            reappear.append({"key": f"{k[0]}/{k[1] or '-'}", "rx_s": r["rx_us"] / 1e6, "state": r["state"],
                             "reason": r["reason"]})
        if r["state"] in TERMINAL:
            term_sent[k] = (sig(r), r["rx_us"])
    out["terminal_reappear"] = reappear
    # 3) 변화 보고 간격 (주기 틱 제외)
    sends = sorted({(r["env_f"], r["pid"], r["weapon"]) for r in rx if r["env_f"] % PERIOD_FRAMES})
    same, cross = defaultdict(list), []
    prev_by_key: dict = {}
    prev_by_pid: dict = {}
    for f, pid, w in sends:
        k = (pid, w)
        if k in prev_by_key:
            same[f"{pid}/{w or '-'}"].append((f - prev_by_key[k]) * FRAME_US / 1e3)
        if pid in prev_by_pid and prev_by_pid[pid][1] != w:
            cross.append({"pid": pid, "f": f, "gap_ms": (f - prev_by_pid[pid][0]) * FRAME_US / 1e3,
                          "keys": [prev_by_pid[pid][1] or "-", w or "-"]})
        prev_by_key[k] = f
        prev_by_pid[pid] = (f, w)
    out["same_key_min_gap_ms"] = {k: min(v) for k, v in same.items()}
    out["cross_key_gaps_lt_100ms"] = [c for c in cross if c["gap_ms"] < 100]
    return out


def main() -> None:
    for a in sys.argv[1:]:
        d = Path(a)
        o = analyse(d)
        (d / "keys.json").write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"== {d} hz={o['hz']} core={o['core_n']} rx={o['rx_n']} drops={o['drops']}")
        for r in o["rows"]:
            print(f"  f{r['core_f']:>4} {r['t_s']:7.3f} {r['pid']} {r['state']:<9} {r['reason'] or r['weapon']:<16}"
                  f" rx={r['rx_s']} send_f={r['send_f']} delay={r['delay_ms']}")
        print("  lost:", o["lost"])
        print("  last_by_key:", o["last_by_key"])
        print("  period_bad:", o["period_bad"], " terminal_reappear:", o["terminal_reappear"])
        for p in o["periods"][:20]:
            print("   period", p["t_s"], p["sent"], "flying", p["flying"])
        print("  same_key_min_gap_ms:", o["same_key_min_gap_ms"])
        print("  cross_key_gaps_lt_100ms:", o["cross_key_gaps_lt_100ms"])


if __name__ == "__main__":
    main()

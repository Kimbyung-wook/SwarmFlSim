"""QA 37차 O-43·O-44 (TC-QA-20x): Agent --profile 결과를 §34.5 표 모양으로 다시 읽는다.

단계: done_to_done, tick_total, fa, ma, report_activity, inputs_total, SystemStatus 수신, GCS 하트비트 수신, Agent 밖
(= done_to_done − tick_total − inputs_total). 묶음: all, phase0, phase4, other. 실행별 값과 중앙값을 낸다.
timeline 구성(result.json의 timeline)에서는 긴 프레임 위상 상위와 구간 평균을 같이 낸다.

uv run python qa/o43_phase.py qa/out/qa37/tlP
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

KEYS = ("done_to_done", "tick_total", "fa", "ma", "report_activity", "inputs_total", "in:onboard:SystemStatus",
        "in:rx:c2:GcsHeartbeat")


def row(s: dict) -> dict:
    m = s["ms_per_frame"]
    r = {k: round(m.get(k, 0.0), 3) for k in KEYS}
    r["outside_agent"] = round(m.get("done_to_done", 0) - m.get("tick_total", 0) - m.get("inputs_total", 0), 3)
    r["n_hb"] = s.get("n_per_frame", {}).get("in:rx:c2:GcsHeartbeat")
    r["n_ss"] = s.get("n_per_frame", {}).get("in:onboard:SystemStatus")
    return r


def find_tl(o) -> dict | None:  # noqa: ANN001
    if isinstance(o, dict):
        if "big_phase_top" in o:
            return o
        for v in o.values():
            x = find_tl(v)
            if x:
                return x
    elif isinstance(o, list):
        for v in o:
            x = find_tl(v)
            if x:
                return x
    return None


def main() -> None:
    base = Path(sys.argv[1])
    out: dict = {"profile": {}, "timeline": {}}
    for f in sorted(base.glob("*/r*/agent-0_profile.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out["profile"][f"{f.parent.parent.name}/{f.parent.name}"] = {g: row(d["summary"][g]) for g in d["summary"]}
    for f in sorted(base.glob("*/r*/result.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        tl = find_tl(r)
        if tl:
            out["timeline"][f"{f.parent.parent.name}/{f.parent.name}"] = {
                "speed_x": r.get("speed_x"), **{k: tl.get(k) for k in ("big_phase_top", "big_segments", "rest_lt5ms",
                                                                        "frames_ge_5ms", "frame_total")}}
    med = {}
    runs = list(out["profile"].values())
    if runs:
        for g in runs[0]:
            med[g] = {k: round(st.median(x[g][k] for x in runs if x[g].get(k) is not None), 3)
                      for k in runs[0][g] if all(x[g].get(k) is not None for x in runs)}
    out["profile_median"] = med
    (base / "o43_phase.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

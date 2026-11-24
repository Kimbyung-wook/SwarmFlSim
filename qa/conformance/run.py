"""표준 적합성 점검 도구 진입점 (DEC-092, REQ-STD-001, docs/44_standards_conformance.md §5).

uv run python qa/conformance/run.py --out qa/out/conformance/<날짜>

1. 정적 수집: proto 옵션·Gateway 변환기 등록(gateway/.venv에서 gw_dump.py), 공개 XSD, 등록부 §5, gateway/TRACE.md, MA import,
   open_bus 소스 점검
2. 점검 실행(harness_run.py): lockstep 고정 시드. --repeat N이면 같은 커밋으로 N번 돌려 판정이 같은지 비교한다
3. 판정(judges.py) → <out>/result.json, <out>/c1_table.json, docs/45_standards_report.md (--no-doc이면 <out>/report.md만)
4. 이력(history.py, DEC-095) → qa/conformance/history.jsonl에 한 줄 덧붙이고 docs/47_conformance_history.md를 다시 만든다

옵션: --reuse <폴더>  점검 실행 없이 이전 실행 폴더(run1 등)를 다시 판정한다
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import analyze as A  # noqa: E402
import findings as F  # noqa: E402
import history as H  # noqa: E402
import judges as J  # noqa: E402
import report  # noqa: E402
import static  # noqa: E402
from confcommon import CONFORMANCE_DOC, REPORT_DOC, ROOT, versions, write_json  # noqa: E402

DET_TEXT = ("docs/21_qa_report.md §28(20차, TC-QA-106~113): 같은 시드 lockstep 반복에서 truth 궤적·LinkOutcome·GCS 수신이 "
            "같았다(손실 없음·있음, 고장 주입, 임무장비, 50기, Gateway 포함 외부 입력 없는 구성). §31(23차 회귀)에서 다시 같았다")


def judge_run(rd: Path, st: dict) -> tuple[dict, dict]:
    r = A.Run(rd)
    gwd = st["gwd"]
    rx, sent, negs = A.c2_inputs(r)
    c2 = J.judge_c2(rx, sent, negs)
    pairs, ts, ids, states, routes, unp = A.c3_inputs(r)
    c3 = J.judge_c3(pairs, ts, ids, states, routes, unp, A.c3_epoch(r))
    c4 = J.judge_c4(**A.c4_inputs(r, gwd["proto"]))
    seqs, approvals, commands = A.c5_inputs(r)
    c5 = J.judge_c5(seqs, approvals, commands)
    d, fl, tap, ext_rx, inbound = A.c6_inputs(r)
    c6 = J.judge_c6(d, fl, tap, ext_rx, inbound, negative_flows=A.c6_negative_flows(r))
    observed = {x[1] for x in r.ext.get("rx", [])} | {k for k, n in inbound.items() if n > 0}
    extra = {"observed": observed, "c5_commands": commands, "run": r}
    return {"C2": c2, "C3": c3, "C4": c4, "C5": c5, "C6": c6}, extra


def gw_scenario(rd: Path) -> str:
    """39차(DEC-109): Gateway가 시나리오를 어느 경로로 받았는지 (gw1.json 카운터)"""
    import json
    try:
        c = json.loads((rd / "gw1.json").read_text(encoding="utf-8")).get("counters", {})
    except (OSError, ValueError):
        return "gw1.json 없음"
    keys = ("scenario_query", "scenario_by_query", "scenario_by_subscription", "scenario_duplicate", "scenario_query_none",
            "scenario_query_error")
    return f"{rd.name}: " + " ".join(f"{k.removeprefix('scenario_')}={c.get(k, 0)}" for k in keys)


def key_numbers(res: dict) -> dict:
    s1 = res["C1"]["summary"]
    c2, c3, c4, c5, c6 = (res[k] for k in ("C2", "C3", "C4", "C5", "C6"))
    return {
        "C1": f"XSD {s1['xsd_top']}(MA_ {s1['xsd_ma']}), 대응 UCI {s1['mapped_uci']}, 송신 {s1['send']}·수신 {s1['recv']}, "
              f"실패 {len(res['C1']['fail'])}",
        "C2": f"수신 {sum(x['n'] for x in c2['rx'].values())}건·실패 {sum(x['fail'] for x in c2['rx'].values())}, "
              f"부정 입력 {len(c2['negatives'])}종 중 버스로 나감 {sum(1 for x in c2['negatives'] if x['on_bus'])}",
        "C3": f"위치 {c3['n_pos']}쌍 최대 차 {max(c3['worst']['lat'], c3['worst']['lon']):.3g} rad, "
              f"Timestamp 변동 {c3['ts'].get('spread', 0):.2f} s",
        "C4": f"구독 {len(c4['subs'])}·발행 {len(c4['puts'])}키, 허용 밖 {sum(1 for x in c4['subs'] + c4['puts'] if not x['ok'])}, "
              f"SIM 포트 메시지 {sum(1 for x in c4['ports'] if not x['ok'])}",
        "C5": f"전이 위반 {len(c5['fail'])}건, 승인 필요 {sum(1 for a in c5['approvals'] if a['need'])}건 중 위반 "
              f"{sum(1 for a in c5['approvals'] if a['need'] and not a.get('ok', True))}",
        "C6": f"선언 불일치 {sum(1 for x in c6['declared'] if x['state'] not in ('일치', '선언 밖(부정 입력)'))}, /tap 불일치 "
              f"{sum(1 for x in c6['tap'] if not x['ok'])}",
        "C7": f"버스 직접 열기 {len(res['C7']['direct_open'])}, 진입점 open_bus "
              f"{sum(res['C7']['entries'].values())}/{len(res['C7']['entries'])}, 적용성 해당·부분 "
              f"{len(res['C7']['applicability']['rows'])}행 중 근거 없음 "
              f"{sum(1 for x in res['C7']['applicability']['rows'] if x['missing'])}",
    }


def main() -> int:  # noqa: PLR0915
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeat", type=int, default=1, help="같은 커밋으로 점검 실행을 몇 번 할지 (판정 재현 비교)")
    ap.add_argument("--reuse", default="", help="점검 실행 없이 판정할 이전 실행 폴더")
    ap.add_argument("--base-port", type=int, default=48900)
    ap.add_argument("--no-doc", action="store_true", help="docs/45를 쓰지 않고 <out>/report.md만 쓴다")
    ap.add_argument("--envelope", choices=("on", "off"), default="on", help="39차: 봉투(DEC-111). off면 lacal_server_raw.yaml")
    ap.add_argument("--late-gw", action="store_true", help="39차: Gateway를 Core가 돈 뒤에 띄운다(시나리오 조회 경로)")
    a = ap.parse_args()
    t0 = time.time()
    out = Path(a.out)
    out = (ROOT / out) if not out.is_absolute() else out
    out.mkdir(parents=True, exist_ok=True)
    print(f"[conf] 정적 수집 → {out}", flush=True)
    st = A.static_inputs(out)
    gwd = st["gwd"]
    runs: list[Path] = []
    if a.reuse:
        runs = [Path(a.reuse).resolve()]
    else:
        import harness as h
        import harness_run
        try:
            for i in range(a.repeat):
                rd = out / f"run{i + 1}"
                print(f"[conf] 점검 실행 {i + 1}/{a.repeat} → {rd}", flush=True)
                harness_run.run(rd, a.base_port, envelope=a.envelope == "on", late_gw=a.late_gw)
                runs.append(rd)
        finally:
            h.Stack.down_all()
    all_res = []
    for rd in runs:
        res, extra = judge_run(rd, st)
        all_res.append((res, extra))
    res, extra = all_res[0]
    std_shorts = [p["short"] for p in gwd["proto"] if p["mapping"] == "STD"]
    scope = static.contract_scope(static.CONTRACT_DOC.read_text(encoding="utf-8"), std_shorts, static.proto_fields())
    res["C1"] = J.judge_c1(gwd["proto"], st["xsd"], gwd["converters"], gwd["also_converters"], st["registry"],
                           st["trace"], gwd["effective_import"], extra["observed"], scope)
    direct, entries = static.bus_open_scan()
    loadout = [f"{x['uci']} ({x['internal']}, {x['dir']}, {x['status']})" for x in res["C1"]["rows"]
               if x["l1"] == "MS" and x["uci"] in ("StoreLoadoutConfiguration", "StrikeActivity")]
    app = static.amsgra_applicability(static.AMSGRA_DOC.read_text(encoding="utf-8"))
    decs = static.registry_decs((ROOT / "docs" / "02_registry.md").read_text(encoding="utf-8"))
    appc = J.check_applicability(app, static.repo_files(), decs)
    appc["summary_head"], appc["summary"] = app["head"], app["summary"]
    res["C7"] = J.judge_c7(direct, entries, A.ms_services(gwd["proto"]), loadout, {"text": DET_TEXT}, appc)
    res["C7"]["determinism"]["tool_repeat"] = None
    repeat = None
    if len(all_res) > 1:
        rows, same_all, exact_all = [], True, True
        for k in ("C2", "C3", "C4", "C5", "C6"):
            vs = [r[k]["verdict"] for r, _ in all_res]
            fs = [sorted(r[k]["fail"]) for r, _ in all_res]
            ns = [sorted(J.strip_numbers(t) for t in f) for f in fs]
            same = len(set(vs)) == 1 and all(f == ns[0] for f in ns)
            exact = all(f == fs[0] for f in fs)
            same_all &= same
            exact_all &= exact
            rows.append([k, *[f"{v} ({len(f)})" for v, f in zip(vs, fs)], "예" if same else "아니오",
                         "예" if exact else "아니오"])
        if same_all:
            summ = "판정과 실패 문구(수치 제외)가 모두 같다" + ("" if exact_all else ". 수치(건수·시간 차)는 일부 다르다(표 참고)")
        else:
            summ = "판정 또는 실패 문구(수치 제외)가 다른 항목이 있다(표 참고)"
        repeat = {"runs": len(all_res), "rows": rows, "summary": summ}
        res["C7"]["determinism"]["text"] += f". 이 도구의 같은 커밋 {len(all_res)}회 실행: {repeat['summary']}"
    # C3는 반복 실행 가운데 하나라도 실패하면 실패로 센다(38차, docs/44 C3 시각 기준). 다른 항목은 run1 판정 그대로다
    for i, (ri, _) in enumerate(all_res[1:], 2):
        if ri["C3"]["verdict"] == "실패":
            res["C3"]["fail"] += [f"run{i}: {t}" for t in ri["C3"]["fail"]]
            res["C3"]["verdict"] = "실패"
    r: A.Run = extra["run"]
    m = r.marks
    fnd, loose = F.attach(res)
    sim_end = max((e["sim_s"] for e in m.get("events", [])), default=0)
    R = {
        "versions": versions(),
        "meta": {"date": dt.date.today().isoformat(), "out": out.relative_to(ROOT).as_posix(),
                 "elapsed_s": round(time.time() - t0)},
        "results": {k: res[k] for k in ("C1", "C2", "C3", "C4", "C5", "C6", "C7")},
        "key": key_numbers(res),
        "limits": static.conformance_limits(CONFORMANCE_DOC.read_text(encoding="utf-8")),
        "findings": fnd, "loose": loose, "c5_commands": extra["c5_commands"], "repeat": repeat,
        "run": {"scenario": (r.d / "scenario.json").relative_to(ROOT).as_posix(), "seed": r.scenario["run"]["seed"],
                "n_vehicles": len(r.vehicles()), "cal": "28765/28766", "zenoh": f"{a.base_port}~{a.base_port + 30}",
                "sim_s": round(sim_end, 1), "wall_s": round(m.get("t1_epoch", 0) - m.get("t0_epoch", 0)),
                "pids": m.get("pids"), "dead": m.get("dead_at_end"), "log_issues": m.get("log_issues", []),
                "envelope": m.get("envelope", True), "late_gw": m.get("late_gw", False),
                "gw_scenario": [gw_scenario(rr.d) for _, x in all_res for rr in [x["run"]]],
                "events": m.get("events", [])},
    }
    R["meta"]["elapsed_s"] = round(time.time() - t0)
    write_json(out / "result.json", {k: v for k, v in R.items()})
    write_json(out / "c1_table.json", res["C1"]["rows"])
    md = report.build(R)
    (out / "report.md").write_text(md, encoding="utf-8", newline="\n")
    if not a.no_doc:
        REPORT_DOC.write_text(md, encoding="utf-8", newline="\n")
        print(f"[conf] 보고서 → {REPORT_DOC.relative_to(ROOT)}", flush=True)
        # DEC-095: 실행마다 이력 한 줄을 덧붙이고 docs/47을 다시 만든다 (--no-doc 실행은 남기지 않는다)
        ent = H.make_entry(R, repeat=len(all_res), mode="reuse" if a.reuse else "run")
        if not a.reuse:     # 39차: 외부 교환 방식·Gateway 기동 순서를 남긴다
            ent["notes"] = [f"봉투 {a.envelope}" + (", Gateway 늦게 붙음(late_gw)" if a.late_gw else "")
                            + ". " + "; ".join(R["run"]["gw_scenario"])]
        H.append(ent)
        H.write_doc()
        print(f"[conf] 이력 → {H.HISTORY.relative_to(ROOT)}, {H.HISTORY_DOC.relative_to(ROOT)}", flush=True)
    for k, _ in report.ITEMS:
        print(f"[conf] {k} {res[k]['verdict']}  {R['key'][k]}", flush=True)
    print(f"[conf] 미분류 실패 {len(loose)}, 걸린 시간 {R['meta']['elapsed_s']} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

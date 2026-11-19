"""DEC-094 C1 범위 구분과 DEC-095 점검 이력의 도구 시험 (TC-QA-173~177).

uv run python -m pytest qa/conformance/tests -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import confcommon  # noqa: E402
import findings as F  # noqa: E402
import history as H  # noqa: E402
import judges as J  # noqa: E402
import static  # noqa: E402
from confcommon import FAIL, PASS  # noqa: E402

# ------------------------------------------------------------------------------------------- TC-QA-173 C1 범위 구분

CONTRACT = """# 계약
### 3.2 키 목록

| 키 | 메시지 | 발행 | 구독 |
|---|---|---|---|
| `sim/ctrl/scenario` | `Scenario` | Core | Agent 런타임 |
| `swarm/<src>/tx/<iface>/<msg>` | `LinkEnvelope` | 송신 엔티티 런타임 | Datalink만 |
| `onboard/<id>/<msg>` | `SystemStatus`, `*Activity`, `*Command` | Core ⇄ 해당 기체 런타임 | 해당 기체 런타임, Core |

### 3.3 규칙

- `<iface>`: `c2`, `vi`. `<msg>`: proto 메시지의 짧은 이름(예: `FlightCommand`).
- 임무장비 상태 보고
  - 런타임은 `onboard/<id>/{SensorActivity}`를 받아 GCS에 `swarm/<id>/tx/ms/<Msg>`로 보낸다.
- 기체 VI 상태 보고
  - `swarm/<id>/tx/vi/<Msg>`로 보낸다.
  - `SystemStatus`는 값이 바뀔 때 보낸다.

### 3.4 다음
"""
FIELDS = {"Scenario": {"MissionPlan", "EngagementCriteria"}, "MissionPlan": {"Task"}, "EngagementCriteria": set()}
SHORTS = ["SensorCommand", "SensorActivity", "SystemStatus", "FlightCommand", "EngagementCriteria", "MissionPlan",
          "TaskStatus", "Task"]


def test_c1_scope_derived_from_contract_key_table():
    sc = static.contract_scope(CONTRACT, SHORTS, FIELDS)
    inside = {k for k, v in sc.items() if v["inside"]}
    # *Command 끝 맞춤, Scenario 필드(중첩 포함)는 swarm 밖 키. swarm 덩어리에 이름이 나오면 경계. 키 표에 없으면 경계
    assert inside == {"SensorCommand", "FlightCommand", "EngagementCriteria", "MissionPlan", "Task"}
    assert sc["SensorActivity"]["swarm_ctx"] == ["임무장비 상태 보고"]
    assert sc["SystemStatus"]["swarm_ctx"] == ["기체 VI 상태 보고"]       # 하위 줄도 덩어리에 든다
    assert sc["TaskStatus"] == {"named_keys": [], "swarm_ctx": [], "inside": False}
    assert sc["FlightCommand"]["named_keys"] == ["onboard/<id>/<msg>"]   # swarm 없는 덩어리의 예시는 근거가 아니다
    # 계약이 바뀌면 결과도 바뀐다(목록을 손으로 두지 않음)
    sc2 = static.contract_scope(CONTRACT.replace("`*Command`", "`SensorCommand`"), SHORTS, FIELDS)
    assert not sc2["FlightCommand"]["inside"] and sc2["SensorCommand"]["inside"]


def _p(short, uci, l1="MS"):  # noqa: ANN001, ANN202
    return {"full_name": f"swarm.v1.{short}", "short": short, "file": "x.proto", "uci_name": uci, "uci_also": [],
            "mapping": "STD", "l1": l1}


XSD = {"MA_A", "MA_B", "MA_C", "MA_D"}


def _c1(scope):  # noqa: ANN001, ANN202
    proto = [_p("SensorCommand", "MA_A"), _p("SensorActivity", "MA_B"), _p("MissionPlan", "MA_C", "MP"),
             _p("TaskStatus", "MA_D", "C2")]
    conv = [{"proto": "swarm.v1.SensorActivity", "cls": "X", "module": "m", "export": True, "import": False},
            {"proto": "swarm.v1.MissionPlan", "cls": "Y", "module": "m", "export": False, "import": True}]
    return J.judge_c1(proto, XSD, conv, [], [], {}, ["MA_C"], set(), scope)


def test_c1_inside_std_without_converter_is_not_failure():
    sc = static.contract_scope(CONTRACT, ["SensorCommand", "SensorActivity", "MissionPlan", "TaskStatus"],
                               {"Scenario": {"MissionPlan"}})
    r = _c1(sc)
    # TaskStatus는 경계인데 변환기가 없다 → 실패 하나만 남는다
    assert r["verdict"] == FAIL and r["fail"] == ["TaskStatus (MA_D): STD인데 변환기가 없다"]
    st = {x["internal"]: (x["status"], x["scope"]) for x in r["rows"]}
    assert st["SensorCommand"] == (J.INSIDE, "기체 내부")
    assert st["SensorActivity"][1] == "GCS 경계" and st["MissionPlan"][1] == "GCS 경계"
    assert r["summary"]["inside"] == ["SensorCommand"]
    # 계약상 기체 내부인데 변환기가 있으면 경계로 보고 정보로 적는다
    assert any(t.startswith("MissionPlan: 계약 키 표로는 swarm 밖 키") for t in r["info"])


def test_c1_without_scope_keeps_old_rule():
    r = _c1(None)
    assert any("SensorCommand (MA_A): STD인데 변환기가 없다" in t for t in r["fail"])


def test_c1_inside_std_still_needs_xsd_name():
    sc = {"SensorCommand": {"named_keys": ["onboard/<id>/<msg>"], "swarm_ctx": [], "inside": True}}
    proto = [_p("SensorCommand", "MA_NOPE")]
    r = J.judge_c1(proto, XSD, [], [], [], {}, [], set(), sc)
    assert r["fail"] == ["SensorCommand: uci_name MA_NOPE이 XSD 최상위 요소에 없다"]


def test_c1_real_contract_inside_set_and_d38_gone():
    """실제 계약·proto: 기체 내부는 계약에서 나온다. 29차 D-38의 5종이 기체 내부이고 D-38 판정 문구가 없어진다"""
    shorts = ["EngagementCriteria", "SensorCommand", "JammerCommand", "StrikeCommand", "FlightCommand", "SensorActivity",
              "SystemStatus", "TaskCommand", "TaskStatus", "NavigationReport", "StoreLoadout"]
    sc = static.contract_scope(static.CONTRACT_DOC.read_text(encoding="utf-8"), shorts, static.proto_fields())
    inside = {k for k, v in sc.items() if v["inside"]}
    assert {"EngagementCriteria", "SensorCommand", "JammerCommand", "StrikeCommand", "FlightCommand"} <= inside
    assert not inside & {"SensorActivity", "SystemStatus", "TaskStatus", "NavigationReport", "StoreLoadout"}
    fnd, _ = F.attach({"C1": {"fail": [], "info": []}})
    assert not next(f for f in fnd if f["id"] == "D-38")["hits"]


def test_proto_fields_parser():
    f = static.proto_fields()
    assert "EngagementCriteria" in f["Scenario"] and "MissionPlan" in f["Scenario"]
    assert "string" not in f["Scenario"]


# ------------------------------------------------------------------------------------------- TC-QA-174 실행 기록

def _R(verdicts, hits, commit="abc1234", dirty=False, date="2026-11-18", out="qa/out/conformance/x"):  # noqa: ANN001, ANN202
    return {"versions": {"commit": commit, "dirty": dirty, "contract": "0.19.0", "agra_lacal": "45274ce"},
            "meta": {"date": date, "out": out},
            "results": {k: {"verdict": v, "fail": ["x"] * (v == FAIL)} for k, v in zip(H.ITEMS, verdicts)},
            "key": {k: f"{k} 수치" for k in H.ITEMS}, "run": {"seed": 7},
            "findings": [{"id": i, "hits": ["t"] if i in hits else []} for i in ("D-1", "D-2", "O-3")]}


V_A = [FAIL, FAIL, FAIL, PASS, FAIL, FAIL, "정보"]


def test_history_entry_fields():
    e = H.make_entry(_R(V_A, {"D-1", "O-3"}, dirty=True), repeat=2)
    assert {"date", "out", "commit", "dirty", "contract", "agra_lacal", "criteria_commit", "tool_commit", "seed", "repeat",
            "items", "findings"} <= set(e)
    assert e["dirty"] is True and e["seed"] == 7 and e["repeat"] == 2 and e["findings"] == ["D-1", "O-3"]
    assert e["items"]["C1"] == {"verdict": FAIL, "n_fail": 1, "key": "C1 수치"}
    assert e["criteria_commit"] != H.UNKNOWN and e["tool_commit"] != H.UNKNOWN   # 이 저장소 git에서 얻는다


def test_history_missing_fields_are_unknown():
    e = H.make_entry({"versions": {}, "meta": {}, "results": {}}, repeat=H.UNKNOWN, rev="HEAD")
    assert e["commit"] == e["date"] == e["seed"] == e["findings"] == H.UNKNOWN
    assert e["items"]["C3"] == {"verdict": H.UNKNOWN, "n_fail": H.UNKNOWN, "key": H.UNKNOWN}


def test_history_append_only(tmp_path):
    p = tmp_path / "h.jsonl"
    H.append({"n": 1}, p)
    first = p.read_bytes()
    H.append({"n": 2}, p)
    assert p.read_bytes().startswith(first)                    # 앞 줄은 그대로
    assert [e["n"] for e in H.load(p)] == [1, 2]
    assert b"\r\n" not in p.read_bytes()


# ------------------------------------------------------------------------------------------- TC-QA-175 docs/47 표

def _entries():  # noqa: ANN202
    e1 = H.make_entry(_R(V_A, {"D-1", "D-2"}, commit="c1"), repeat=2)
    e2 = H.make_entry(_R([PASS, *V_A[1:]], {"D-2"}, commit="c2"), repeat=2)
    e3 = H.make_entry(_R([PASS, *V_A[1:]], {"D-2", "O-3"}, commit="c3", dirty=True), repeat=1)
    return [e1, e2, e3]


def _between(a, b):  # noqa: ANN001, ANN202
    return {("c1", "c2"): ["`k1` 기준"]}.get((a, b), [])


def test_run_rows_mark_changed_verdicts():
    rows = H.run_rows(_entries())
    c1 = 8                                        # #, 날짜, 폴더, 대상, 기준, 도구, 시드, 반복 다음
    assert rows[0][c1] == FAIL
    assert rows[1][c1] == f"**{PASS}** (← {FAIL})"
    assert rows[2][c1] == PASS                     # 바뀌지 않으면 표시 없음
    assert rows[2][3] == "`c3` (dirty)"
    assert rows[1][-1] == "D-2"


def test_finding_rows_track_first_last_gone():
    rows = {r[0]: r for r in H.finding_rows(_entries(), ["D-1", "D-2", "O-3", "O-9"], _between)}
    assert rows["D-1"][1:] == ["1 (`c1`)", "1 (`c1`)", "2 (`c2`)", "해소", "`k1` 기준", "제품 변경"]
    assert rows["D-2"][1:] == ["1 (`c1`)", "3 (`c3`)", "—", "재현", "—", "—"]
    assert rows["O-3"][1:] == ["3 (`c3`)", "3 (`c3`)", "—", "재현", "—", "—"]
    assert "O-9" not in rows                      # 한 번도 재현되지 않은 목록 항목은 싣지 않는다


def test_finding_rows_skip_unknown_runs():
    es = _entries()
    es.insert(1, {**es[1], "findings": H.UNKNOWN, "commit": "cx"})   # 발견을 모르는 실행은 사라진 실행으로 치지 않는다
    rows = {r[0]: r for r in H.finding_rows(es, between=_between)}
    assert rows["D-1"][3] == "3 (`c2`)"


def test_build_md_has_three_tables():
    md = H.build_md(_entries(), [{"commit": "k1", "date": "2026-11-18", "subject": "DEC-094 기준", "what": ["기준(docs/44)"],
                                  "decs": ["DEC-094"]}], ["D-1", "O-9"], _between)
    assert "## 1. 실행 이력" in md and "## 2. 점검 조건 변경 이력" in md and "## 3. 발견 추적" in md
    assert "| `k1` | 2026-11-18 | 기준(docs/44) | DEC-094 기준 | DEC-094 |" in md
    assert md.count("\n| 3 |") >= 1
    assert "나온 적 없는 발견: O-9" in md


# ------------------------------------------------------------------------------------------- TC-QA-176 소급 기록

def test_backfill_from_result_json(tmp_path):
    R = _R(V_A, {"D-1"}, commit="HEAD")
    R["repeat"] = {"runs": 2}
    confcommon.write_json(tmp_path / "result.json", R)
    e = H.backfill(tmp_path)
    assert e["mode"] == "backfill" and e["repeat"] == 2 and e["findings"] == ["D-1"]
    assert e["derived"] == ["criteria_commit", "tool_commit"]
    R.pop("repeat")
    R.pop("findings")
    confcommon.write_json(tmp_path / "result.json", R)
    e = H.backfill(tmp_path)
    assert e["repeat"] == 1 and e["findings"] == H.UNKNOWN and "repeat" in e["derived"]


def test_history_file_first_line_is_run29():
    es = H.load()
    assert es, "history.jsonl이 비어 있다"
    e = es[0]
    assert (e["commit"], e["date"], e["out"], e["mode"]) == ("b80a848", "2026-11-17", "qa/out/conformance/2026-11-17",
                                                              "backfill")
    assert e["dirty"] is False and e["repeat"] == 2 and e["seed"] == 20261117
    assert "D-38" in e["findings"] and e["items"]["C4"]["verdict"] == PASS
    for ln in H.HISTORY.read_text(encoding="utf-8").splitlines():
        json.loads(ln)


# ------------------------------------------------------------------------------------------- TC-QA-177 조건 변경 이력

def test_condition_changes_from_git():
    ch = {c["commit"]: c for c in H.condition_changes()}
    assert ch["14538c4"]["what"] == ["기준(docs/44)"] and ch["14538c4"]["decs"] == ["DEC-092"]
    assert "도구(qa/conformance)" in ch["a904a3b"]["what"] and ch["a904a3b"]["decs"] == ["DEC-092", "DEC-093"]
    assert "6e0dd5c" not in ch                     # 병합 커밋은 뺀다
    assert all(c["what"] for c in ch.values())     # 이력 파일만 바꾼 커밋은 나오지 않는다


# ------------------------------------------------------------------------------------------- TC-QA-182 해소 원인 구분

def test_finding_gone_by_product_change_marked():
    es = _entries()
    rows = {r[0]: r for r in H.finding_rows(es, between=lambda a, b: [])}
    assert rows["D-1"][5] == "없음(제품 변경)"
    rows = {r[0]: r for r in H.finding_rows(es, between=lambda a, b: H.UNKNOWN)}
    assert rows["D-1"][5] == H.UNKNOWN


def test_changes_between_from_git():
    """31차(2ee7ebb)와 32차 준비 병합(b763a74) 사이: 기준 da9287c(DEC-097), 도구 fd1b8e1. 병합 커밋은 없다"""
    ch = H.changes_between("2ee7ebb", "b763a74")
    assert "`fd1b8e1` 도구" in ch
    assert not any(c.startswith(("`095abb3`", "`ee7aad2`", "`5e8cee7`")) for c in ch)
    assert H.changes_between(H.UNKNOWN, "b763a74") == H.UNKNOWN
    assert "`da9287c` 기준(DEC-097)" in ch


def test_gone_cause_criteria_vs_product():
    ch = ["`t1` 도구", "`k1` 기준(DEC-097)"]
    assert H.gone_cause(ch, "DEC-097: 첫 보고 CANCELLED 허용") == "기준 변경(DEC-097 `k1`)"
    assert H.gone_cause(ch, "") == "제품 변경"                       # 조치 DEC가 없으면 제품 변경
    assert H.gone_cause(["`t1` 도구", "`k2` 기준(DEC-094)"], "DEC-097") == "제품 변경"
    assert H.gone_cause(H.UNKNOWN, "DEC-097") == H.UNKNOWN
    rows = {r[0]: r for r in H.finding_rows(_entries(), between=lambda a, b: ch, resolutions={"D-1": "DEC-097"})}
    assert rows["D-1"][6] == "기준 변경(DEC-097 `k1`)"

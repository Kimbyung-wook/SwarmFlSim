"""DEC-097 명령 상태 전이의 도구 시험 (TC-QA-179~181).

uv run python -m pytest qa/conformance/tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import findings as F  # noqa: E402
import judges as J  # noqa: E402
from confcommon import FAIL, PASS  # noqa: E402

EXT = "MA_FlightCommandStatus(외부)"
FCS = "FlightCommandStatus(내부)"


def _c5(name, states):  # noqa: ANN001, ANN202
    return J.judge_c5({name: {"c": states}}, [], [{"entity": "u", "task": "t", "src": "외부", "status_seen": True}])


# ------------------------------------------------------------------------------------------- TC-QA-179 외부 명령 상태

def test_ext_cmd_table_matches_dec097():
    assert J.TERMINAL_EXT_CMD == {"ACCEPTED", "REJECTED", "CANCELED"}
    assert J.TRANS_EXT_CMD[None] == {"RECEIVED", "ACCEPTED", "REJECTED", "CANCELED"}
    assert J.TRANS_EXT_CMD["RECEIVED"] == {"ACCEPTED", "REJECTED", "CANCELED"}
    assert set(J.TRANS_EXT_CMD) == {None, "RECEIVED"}          # 끝 상태에서 나가는 전이는 없다


def test_ext_cmd_allowed_sequences_pass():
    for st in (["RECEIVED"], ["ACCEPTED"], ["REJECTED"], ["CANCELED"], ["RECEIVED", "ACCEPTED"],
               ["RECEIVED", "REJECTED"], ["RECEIVED", "CANCELED"], ["RECEIVED", "RECEIVED", "ACCEPTED"]):
        assert _c5(EXT, st)["verdict"] == PASS, st


def test_ext_cmd_report_after_terminal_fails():
    for st, msg in ((["ACCEPTED", "CANCELED"], "ACCEPTED→CANCELED(끝 상태 뒤)"),
                    (["ACCEPTED", "REJECTED"], "ACCEPTED→REJECTED(끝 상태 뒤)"),
                    (["REJECTED", "ACCEPTED"], "REJECTED→ACCEPTED(끝 상태 뒤)"),
                    (["CANCELED", "RECEIVED"], "CANCELED→RECEIVED(끝 상태 뒤)")):
        r = _c5(EXT, st)
        assert r["verdict"] == FAIL and msg in r["fail"][0], (st, r["fail"])


# ------------------------------------------------------------------------------------------- TC-QA-180 끝 상태 뒤 반복

def test_ext_cmd_repeat_after_terminal_fails():
    """DEC-097 '끝 상태 뒤 보고가 있으면 실패': 외부 명령 상태는 같은 상태 반복도 끝 상태 뒤면 실패"""
    r = _c5(EXT, ["RECEIVED", "ACCEPTED", "ACCEPTED"])
    assert r["verdict"] == FAIL and "ACCEPTED→ACCEPTED(끝 상태 뒤 반복)" in r["fail"][0]
    assert J.check_sequence(["ACCEPTED", "ACCEPTED", "ACCEPTED"], J.TRANS_EXT_CMD, J.TERMINAL_EXT_CMD, True) == [
        "ACCEPTED→ACCEPTED(끝 상태 뒤 반복)", "ACCEPTED→ACCEPTED(끝 상태 뒤 반복)"]


def test_internal_tables_keep_repeat_rule():
    """내부 표와 외부 MA_TaskStatus는 변화 보고 재송신 반복을 계속 허용한다"""
    assert _c5(FCS, ["ACCEPTED", "COMPLETED", "COMPLETED"])["verdict"] == PASS
    assert _c5("MA_TaskStatus(외부)", ["EXECUTING", "COMPLETED", "COMPLETED"])["verdict"] == PASS
    assert {k: v[2] for k, v in J.TABLES.items()} == {"TaskStatus(내부)": False, FCS: False,
                                                       "MA_TaskStatus(외부)": False, EXT: True}
    assert _c5(EXT, ["RECEIVED", "RECEIVED"])["verdict"] == PASS   # 끝 상태가 아닌 반복은 허용


# ------------------------------------------------------------------------------------------- TC-QA-181 내부 첫 CANCELLED, O-47

def test_internal_fcs_first_cancelled_allowed():
    assert "CANCELLED" in J.TRANS_FCS[None]
    assert _c5(FCS, ["CANCELLED"])["verdict"] == PASS
    assert _c5(FCS, ["CANCELLED", "EXECUTING"])["verdict"] == FAIL        # 끝 상태 뒤는 여전히 실패
    assert _c5("TaskStatus(내부)", ["CANCELLED"])["verdict"] == FAIL      # 내부 TaskStatus는 바뀌지 않음


def test_o47_lines_no_longer_produced():
    """31차 O-47의 두 순서가 이제 통과하고, O-47에 붙을 실패 문구가 없다"""
    r = J.judge_c5({FCS: {"uav-006-fmn-lead": ["CANCELLED"]}, EXT: {"uav-006-fmn-lead": ["CANCELED"]}}, [],
                   [{"entity": "u", "task": "t", "src": "외부", "status_seen": True}])
    assert r["verdict"] == PASS, r["fail"]
    fnd, _ = F.attach({"C5": r})
    o47 = next(f for f in fnd if f["id"] == "O-47")
    assert not o47["hits"] and "DEC-097" in o47["resolution"]
    assert r["tables"][EXT]["strict_terminal"] is True


def test_d40_classifies_ext_reports_after_accepted():
    """31차 원자료의 새 실패(ACCEPTED 뒤 CANCELED·ACCEPTED 반복)는 D-40으로 분류된다. D-37(REJECTED 뒤)과 겹치지 않는다"""
    lines = ["MA_FlightCommandStatus(외부) uav-009-task-1: 허용 전이 밖 ACCEPTED→CANCELED(끝 상태 뒤) (순서 ACCEPTED → CANCELED)",
             "MA_FlightCommandStatus(외부) uav-010-task-2: 허용 전이 밖 ACCEPTED→ACCEPTED(끝 상태 뒤 반복) (순서 ACCEPTED → ACCEPTED)",
             "MA_FlightCommandStatus(외부) uav-007-fmn-beta: 허용 전이 밖 REJECTED→ACCEPTED(끝 상태 뒤) (순서 REJECTED → ACCEPTED)"]
    fnd, loose = F.attach({"C5": {"fail": lines, "info": []}})
    hits = {f["id"]: len(f["hits"]) for f in fnd}
    assert hits["D-40"] == 2 and hits["D-37"] == 1 and not loose

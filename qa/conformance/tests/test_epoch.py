"""DEC-098 C3 시각 기준 확인의 도구 시험 (TC-QA-184~185).

uv run python -m pytest qa/conformance/tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import analyze as A  # noqa: E402
import judges as J  # noqa: E402
import report  # noqa: E402

EP = 1_790_000_000_000_000          # µs


def _ep(vals=(EP,), gw=None, log=()):  # noqa: ANN001, ANN202
    return {"scenario": [{"epoch_utc_us": v, "wall": 0.0, "n": 3} for v in vals],
            "gw": {"epoch_set": 1, "epoch_changed": 0} if gw is None else gw, "log": list(log)}


# ------------------------------------------------------------------------------------------- TC-QA-184 (a) epoch 일치

def test_epoch_offsets_match_scenario():
    r = J.judge_epoch(_ep(), [EP * 1e-6 + 0.0, EP * 1e-6 + 0.0004])
    assert r["checked"] and not r["fail"] and r["epoch_utc_us"] == EP
    assert abs(r["dev_s"]["abs_max"] - 0.0004) < 1e-5


def test_epoch_offset_mismatch_fails():
    r = J.judge_epoch(_ep(), [EP * 1e-6 + 36.4])
    assert any("시나리오 epoch_utc_us와 다름" in t for t in r["fail"])


def test_epoch_missing_or_zero_fails():
    assert any("관측 0건" in t for t in J.judge_epoch(_ep(vals=()), [1.0])["fail"])
    assert any("0이다" in t for t in J.judge_epoch(_ep(vals=(0,)), [1.0])["fail"])


def test_epoch_multiple_values_use_last_and_info():
    r = J.judge_epoch(_ep(vals=(EP, EP + 5_000_000)), [(EP + 5_000_000) * 1e-6])
    assert not r["fail"] and r["info"] and r["epoch_utc_us"] == EP + 5_000_000


def test_old_raw_data_skips_with_info():
    r = J.judge_epoch(None, [1.0])
    assert not r["checked"] and not r["fail"] and "33차 이전" in r["info"][0]
    run = A.Run(Path(__file__).resolve().parents[3] / "qa" / "out" / "conformance" / "_none_")
    assert A.c3_epoch(run) is None                     # obs.json에 scenario_epochs가 없으면 None


# ------------------------------------------------------------------------------------------- TC-QA-185 (b) epoch_changed

def test_epoch_changed_counter():
    assert not J.judge_epoch(_ep(), [EP * 1e-6])["fail"]
    r = J.judge_epoch(_ep(gw={"epoch_set": 1, "epoch_changed": 1}), [EP * 1e-6])
    assert r["fail"] == ["Gateway epoch_changed 1: 실행 중 UCI 시각 기준이 바뀌었다(DEC-098)"]
    assert any("카운터 기록 없음" in t for t in J.judge_epoch({**_ep(), "gw": None}, [EP * 1e-6])["fail"])


def test_c3_carries_epoch_result_and_report_rows():
    c3 = J.judge_c3([], [EP * 1e-6], {}, [], [], {}, _ep(gw={"epoch_set": 1, "epoch_changed": 2}))
    assert any("epoch_changed 2" in t for t in c3["fail"]) and c3["epoch"]["gw"]["epoch_changed"] == 2
    rows = report._epoch_rows(c3["epoch"], J.TOL)
    assert rows[0][3] == "통과" and rows[1][3] == "실패"
    assert [r[3] for r in report._epoch_rows(J.judge_epoch(None, []), J.TOL)] == ["확인 안 함"] * 3


# ------------------------------------------------------------------- TC-QA-213 (c) 시각 기준 = 시나리오 (38차 O-53, DEC-109)

FIRST = ("2026-11-24 11:48:05,654 WARNING swarm_gateway: gateway: no scenario epoch yet; UCI time = "
         "2026-11-24T02:48:05.654477Z + sim time (wall clock at sim 0.000 s)")


def test_base_scenario_passes():
    r = J.judge_epoch(_ep(), [EP * 1e-6])
    assert not r["fail"] and r["base"] == "scenario"


def test_base_first_message_then_changed_fails():
    """38차 실행 7 run1: 첫 메시지 기준 → 시나리오로 바뀜 (epoch_set 0, epoch_changed 1)"""
    r = J.judge_epoch(_ep(gw={"epoch_changed": 1}, log=(FIRST,)), [EP * 1e-6 + 0.515])
    assert r["base"] == "first_message"
    assert any("시각 기준이 시나리오 값이 아님" in t and "첫 메시지" in t for t in r["fail"])


def test_base_first_message_never_changed_fails():
    """38차 실행 8 run2: 시나리오를 끝까지 못 받음. (a)는 0.5 s 안이라 통과, (b)는 0이라 통과해도 (c)로 실패"""
    r = J.judge_epoch(_ep(gw={}, log=(FIRST,)), [EP * 1e-6 + 0.31])
    assert [t for t in r["fail"] if "epoch_changed" in t or "epoch_utc_us와 다름" in t] == []
    assert len(r["fail"]) == 1 and "첫 메시지 기준" in r["fail"][0]


def test_base_without_epoch_set_fails():
    r = J.judge_epoch(_ep(gw={"epoch_set": 0, "epoch_changed": 0}), [EP * 1e-6])
    assert r["base"] == "없음" and any("epoch_set 0" in t for t in r["fail"])


def test_base_report_row_and_finding():
    import findings as F
    c3 = J.judge_c3([], [EP * 1e-6], {}, [], [], {}, _ep(gw={}, log=(FIRST,)))
    rows = report._epoch_rows(c3["epoch"], J.TOL)
    assert rows[2][:3] == ["Gateway 시각 기준", "scenario", "first_message"] and rows[2][3] == "실패"
    assert report._epoch_rows(J.judge_epoch(_ep(), [EP * 1e-6]), J.TOL)[2][3] == "통과"
    fnd, _ = F.attach({"C3": c3})
    assert [f["id"] for f in fnd if f["hits"]] == ["O-53"]


def test_changed_and_mismatch_texts_attach_to_o53():
    import findings as F
    c3 = J.judge_c3([], [EP * 1e-6 + 0.515], {}, [], [], {}, _ep(gw={"epoch_changed": 1}, log=(FIRST,)))
    fnd, loose = F.attach({"C3": c3})
    o53 = next(f for f in fnd if f["id"] == "O-53")
    assert len(o53["hits"]) == 3 and not [t for _, t in loose if "epoch" in t or "시각 기준" in t]

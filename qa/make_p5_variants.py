"""QA-019 범위 좁히기용 P5 변형 시나리오 생성기. 원본 p5_payload_demo_5.json에서 한 요소씩 끈다.

- qa_p5_nosensor.json : 모든 UAV의 camera 페이로드 제거 (무장·재머는 유지)
- qa_p5_nopayload.json: 모든 엔티티의 payloads 제거 (camera·무장·재머 모두 없음)
- qa_p5_noloss.json   : uav_default·gcs_default 링크 프로파일의 Gilbert-Elliott 손실을 0으로 재정의 (DEC-029)
- qa_p5_range.json    : gcs_default 최대 거리를 12 km로 재정의, 기체가 GCS에서 멀어지면 GCS 링크가 끊긴다 (TC-QA-039)
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "scenario/examples/p5_payload_demo_5.json"
OUT = ROOT / "qa/scenarios"
NO_GE = {"p_gb": 0.0, "p_bg": 1.0, "loss_good": 0.0, "loss_bad": 0.0}


def main() -> None:
    base = json.loads(SRC.read_text(encoding="utf-8"))
    v = {}
    d = copy.deepcopy(base)
    for e in d["entities"]:
        if "payloads" in e:
            e["payloads"] = [p for p in e["payloads"] if p.get("type") != "camera"]
    v["qa_p5_nosensor"] = d
    d = copy.deepcopy(base)
    for e in d["entities"]:
        e.pop("payloads", None)
    v["qa_p5_nopayload"] = d
    d = copy.deepcopy(base)
    d["link_profiles"] = [{"name": n, "ge": NO_GE} for n in ("uav_default", "gcs_default")]
    v["qa_p5_noloss"] = d
    d = copy.deepcopy(base)
    d["link_profiles"] = [{"name": "gcs_default", "max_range_m": 12000.0}]
    for e in d["entities"]:  # 거리 초과 링크 두절이 시험 목적이므로 링크 상실 행동은 끈다 (DEC-078, 21_qa_report §30.8)
        if e.get("kind") == "uav":
            e["autonomy"].setdefault("ma_params", {})["lost_link_policy"] = "continue"
    v["qa_p5_range"] = d
    for name, doc in v.items():
        doc["name"] = name
        doc["description"] = f"QA-019 변형: {name} (원본 {SRC.name})"
        (OUT / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name)


if __name__ == "__main__":
    main()

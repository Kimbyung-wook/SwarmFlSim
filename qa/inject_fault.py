"""라이브 스택에 고장을 주입한다 (UI 고장 표시 점검용).

uv run python qa/inject_fault.py --connect tcp/127.0.0.1:48281 --entity uav-001 --kind ENGINE_OUT [--clear]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--connect", default="tcp/127.0.0.1:48281")
ap.add_argument("--entity", required=True)
ap.add_argument("--kind", required=True)
ap.add_argument("--duration", type=float, default=0.0)
ap.add_argument("--clear", action="store_true")
a = ap.parse_args()
ob = h.Observer([a.connect])
time.sleep(1.5)
ob.fault(a.entity, a.kind, a.duration, a.clear)
time.sleep(1.5)
ob.close()
print("sent", a.entity, a.kind, "clear" if a.clear else "")

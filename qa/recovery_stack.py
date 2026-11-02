"""임무 중 Core·Datalink 재시작 후 UI 복구 시험용 스택 (TC-QA-027).

Logger·Datalink·Agent·Bridge·Core(realtime)와 UI·Monitor dev 서버를 띄우고,
qa/out/recov/cmd.txt에 한 줄씩 적힌 명령(kill|start <이름>, quit)을 처리한다.

uv run --with psutil python qa/recovery_stack.py [--scenario qa/scenarios/qa_s3_link.json]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=str(ROOT / "qa/scenarios/qa_s3_link.json"))
    ap.add_argument("--base-port", type=int, default=18200)
    a = ap.parse_args()
    out = ROOT / "qa/out/recov"
    out.mkdir(parents=True, exist_ok=True)
    cmdf = out / "cmd.txt"
    cmdf.write_text("", encoding="utf-8")
    st = h.Stack(out / "stack", Path(a.scenario), base_port=a.base_port, record=True, bridge=True)
    st.bridge_port = 8765
    web = []
    try:
        st.up()
        for name, port in (("ui", 5173), ("ui/monitor", 5174)):
            web.append(subprocess.Popen(["npm.cmd", "run", "dev", "--", "--port", str(port), "--strictPort"],
                                        cwd=str(ROOT / name), stdout=open(out / f"{name.split('/')[-1]}.log", "w"),
                                        stderr=subprocess.STDOUT))
        print("ready: endpoint", st.endpoint(), flush=True)
        done = 0
        while True:
            lines = cmdf.read_text(encoding="utf-8").splitlines()
            for ln in lines[done:]:
                done += 1
                parts = ln.split()
                if not parts:
                    continue
                if parts[0] == "quit":
                    return
                try:
                    if parts[0] == "kill":
                        st.kill(parts[1])
                    elif parts[0] == "start":
                        st.start_one(parts[1])
                    print(f"{time.strftime('%H:%M:%S')} {ln} ok", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"{ln} FAIL {e}", flush=True)
            time.sleep(0.5)
    finally:
        for w in web:
            subprocess.run(["taskkill", "/PID", str(w.pid), "/T", "/F"], capture_output=True)
        st.down()


if __name__ == "__main__":
    main()

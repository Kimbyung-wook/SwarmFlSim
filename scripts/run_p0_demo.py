"""P0 데모 실행기 (IMP-INT-001, IMP-INT-002). 실행 방법은 docs/20_p0_demo.md.

uv run python scripts/run_p0_demo.py live   [--scenario <json>] [--no-record] [--no-ui] [--monitor]
uv run python scripts/run_p0_demo.py replay <file.mcap> [--rate 1] [--no-ui] [--monitor]
uv run python scripts/run_p0_demo.py probe  [--targets uav-001,uav-002] [--timeout 180]

- live: Logger(record) → Datalink → Agent → 브리지 → Core(realtime 자동 시작) → UI(vite) 순으로 띄운다.
- replay: 브리지 → Logger(replay) → UI. Core·Agent·Datalink는 띄우지 않는다.
- probe: 떠 있는 버스에 GCS(gcs-01)로 붙어 UI와 같은 형식의 MoveTo를 보내고, 기체가 목표에 닿는지와
  TaskStatus를 확인한다 (TC-INT-002).
- 버스: 모든 프로세스가 open_bus(Zenoh peer)로 연다 (DEC-026). 다른 세션의 버스와 섞이지 않도록 멀티캐스트를
  끄고, 프로세스 k는 tcp/127.0.0.1:<base+k>에서 대기하며 앞서 뜬 프로세스 전부에 연결한다(완전 연결).
- 종료: Ctrl+C 또는 실행 디렉터리에 STOP 파일 생성. 자식은 각자 프로세스 그룹으로 띄우고 Windows는 Ctrl+Break, 그 밖은 SIGINT를 보낸다.
"""

import argparse
import math
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIN = os.name == "nt"
EXE = ".exe" if WIN else ""
DEFAULT_SCENARIO = ROOT / "scenario" / "examples" / "p0_demo_20.json"
GCS = "gcs-01"


class Proc:
    def __init__(self, name: str, cmd: list[str], log_dir: Path, cwd: Path = ROOT, shell: bool = False):
        self.name = name
        self.log_path = log_dir / f"{name}.log"
        self.log = open(self.log_path, "wb")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if WIN else 0
        print(f"[p0] start {name}: {' '.join(cmd)}")
        self.p = subprocess.Popen(cmd, cwd=cwd, stdout=self.log, stderr=subprocess.STDOUT, creationflags=flags,
                                  start_new_session=not WIN, shell=shell)

    def alive(self) -> bool:
        return self.p.poll() is None

    def interrupt(self) -> None:
        if not self.alive():
            return
        try:
            if WIN:
                self.p.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(self.p.pid, signal.SIGINT)
        except OSError:
            pass

    def kill(self) -> None:
        if not self.alive():
            return
        if WIN:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.p.pid)], capture_output=True)
        else:
            os.killpg(self.p.pid, signal.SIGKILL)

    def tail(self, n: int = 5) -> str:
        lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join("    " + s for s in lines[-n:])


class Mesh:
    """프로세스마다 대기 엔드포인트 하나, 앞서 뜬 프로세스 전부에 연결"""

    def __init__(self, base_port: int):
        self.base = base_port
        self.n = 0

    def next(self) -> list[str]:
        args = ["--no-multicast", "--listen", f"tcp/127.0.0.1:{self.base + self.n}"]
        for k in range(self.n):
            args += ["--connect", f"tcp/127.0.0.1:{self.base + k}"]
        self.n += 1
        return args


def exe(build: Path, sub: str, name: str) -> str:
    p = build / sub / f"{name}{EXE}"
    if not p.exists():
        raise SystemExit(f"{p} 없음. 먼저 빌드한다: cmake --build --preset msvc-debug")
    return str(p)


def export_scenario(src: Path, out: Path) -> Path:
    import swarm_scenario
    import json

    msg = swarm_scenario.to_proto(swarm_scenario.from_dict(json.loads(src.read_text(encoding="utf-8"))))
    out.write_bytes(msg.SerializeToString())
    return out


def npm_dev(name: str, cwd: Path, port: int, log_dir: Path) -> Proc:
    npm = "npm.cmd" if WIN else "npm"
    return Proc(name, [npm, "run", "dev", "--", "--port", str(port), "--strictPort"], log_dir, cwd=cwd)


def supervise(procs: list[Proc], duration_s: float, stop_file: Path) -> int:
    t_end = time.monotonic() + duration_s if duration_s > 0 else math.inf
    rc = 0
    try:
        while time.monotonic() < t_end and not stop_file.exists():
            dead = [p for p in procs if not p.alive()]
            if dead:
                for p in dead:
                    print(f"[p0] {p.name} 종료 (code {p.p.returncode}), 로그 {p.log_path}\n{p.tail()}")
                rc = 1
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("[p0] Ctrl+C")
    stop(procs)
    return rc


def stop(procs: list[Proc]) -> None:
    # 뒤에 뜬 것부터 멈춘다. Logger는 MCAP을 닫을 시간을 준다
    for p in reversed(procs):
        p.interrupt()
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and any(p.alive() for p in procs):
        time.sleep(0.2)
    for p in procs:
        p.kill()
        p.log.close()


def run_dir(args: argparse.Namespace, tag: str) -> Path:
    d = Path(args.out) if args.out else ROOT / "out" / "p0_demo" / f"{tag}-{datetime.now():%Y%m%d-%H%M%S}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_live(args: argparse.Namespace) -> int:
    build = Path(args.build_dir)
    d = run_dir(args, "live")
    pb = export_scenario(Path(args.scenario), d / "scenario.pb")
    mesh = Mesh(args.base_port)
    py = sys.executable
    procs: list[Proc] = []
    try:
        if not args.no_record:
            mcap = d / "p0_demo.mcap"
            procs.append(Proc("logger", [exe(build, "logger", "swarm_logger"), "record", "--out", str(mcap),
                                         *mesh.next()], d))
        procs.append(Proc("datalink", [exe(build, "datalink", "swarm_datalink"), "--scenario", str(pb),
                                       "--no-frame-done", *mesh.next()], d))
        procs.append(Proc("agent", [py, "-m", "swarm_agent.cli", "--scenario", str(pb), *mesh.next()], d))
        procs.append(Proc("bridge", [py, "-m", "swarm_bridge.cli", "--port", str(args.bridge_port),
                                     *mesh.next()], d))
        time.sleep(args.settle)  # Zenoh 연결·구독 선언이 퍼질 시간
        core = [exe(build, "core", "swarm_core"), "--scenario", str(pb), *mesh.next()]
        if not args.no_autostart:
            core += ["--autostart", "--mode", "realtime"]
        procs.append(Proc("core", core, d))
        if not args.no_ui:
            procs.append(npm_dev("ui", ROOT / "ui", args.ui_port, d))
        if args.monitor:
            procs.append(npm_dev("monitor", ROOT / "ui" / "monitor", args.monitor_port, d))
    except BaseException:
        stop(procs)
        raise
    print(f"[p0] 로그: {d}")
    if not args.no_ui:
        print(f"[p0] UI: http://localhost:{args.ui_port}/?source=bus&gcs={GCS}"
              f"&bridge=ws://127.0.0.1:{args.bridge_port}/bus")
    if args.monitor:
        print(f"[p0] Monitor: http://localhost:{args.monitor_port}/?source=bridge"
              f"&url=ws://127.0.0.1:{args.bridge_port}/bus")
    print(f"[p0] probe: uv run python scripts/run_p0_demo.py probe --connect tcp/127.0.0.1:{args.base_port + 1}")
    print(f"[p0] 종료: Ctrl+C 또는 {d / 'STOP'} 파일 생성")
    return supervise(procs, args.duration, d / "STOP")


def cmd_replay(args: argparse.Namespace) -> int:
    build = Path(args.build_dir)
    d = run_dir(args, "replay")
    mesh = Mesh(args.base_port)
    procs: list[Proc] = []
    try:
        procs.append(Proc("bridge", [sys.executable, "-m", "swarm_bridge.cli", "--port", str(args.bridge_port),
                                     *mesh.next()], d))
        if not args.no_ui:
            procs.append(npm_dev("ui", ROOT / "ui", args.ui_port, d))
        if args.monitor:
            procs.append(npm_dev("monitor", ROOT / "ui" / "monitor", args.monitor_port, d))
        print(f"[p0] UI: http://localhost:{args.ui_port}/?source=bus&gcs="
              f"&bridge=ws://127.0.0.1:{args.bridge_port}/bus")
        if args.monitor:
            print(f"[p0] Monitor: http://localhost:{args.monitor_port}/?source=bridge&replay=1"
                  f"&url=ws://127.0.0.1:{args.bridge_port}/bus")
        time.sleep(args.settle)
        # 재생기가 끝나면 종료한다. 기록한 sim/ctrl/cmd·tx는 받는 쪽(Core·Datalink)이 없으므로 버스에 흘려도 무해하다
        procs.append(Proc("replay", [exe(build, "logger", "swarm_logger"), "replay", args.file, "--rate",
                                     str(args.rate), *mesh.next()], d))
    except BaseException:
        stop(procs)
        raise
    print(f"[p0] 로그: {d}")
    rc = 0
    try:
        while procs[-1].alive() and not (d / "STOP").exists():
            time.sleep(0.5)
        print(f"[p0] 재생 끝\n{procs[-1].tail(2)}")
        if args.linger > 0:
            time.sleep(args.linger)
    except KeyboardInterrupt:
        print("[p0] Ctrl+C")
    stop(procs)
    return rc


def cmd_probe(args: argparse.Namespace) -> int:
    """UI와 같은 형식(commands.ts)으로 MoveTo를 보내고 truth/state·TaskStatus로 도달을 확인한다"""
    from swarm_api import BusConfig, open_bus

    bus = open_bus(BusConfig(connect=args.connect, multicast_scouting=False))
    try:
        return _probe(args, bus)
    finally:
        bus.close()


def _probe(args: argparse.Namespace, bus) -> int:
    from swarm.v1 import c2_pb2, common_pb2, link_pb2, options_pb2, truth_pb2
    from swarm_agent.geo import ned_offset

    lock = threading.Lock()
    pos: dict[str, tuple[float, float, float]] = {}
    status: dict[str, list[str]] = {}
    clock = {"t": 0, "frame": 0}

    def on_truth(s):
        f = truth_pb2.TruthFrame.FromString(s.payload)
        with lock:
            clock["t"], clock["frame"] = f.header.sim_time_us, f.header.frame
            for e in f.entities:
                p = e.kinematics.position
                pos[e.id] = (p.lat_deg, p.lon_deg, p.alt_m)

    def on_rx(s):
        env = link_pb2.LinkEnvelope.FromString(s.payload)
        if env.msg_type != "swarm.v1.TaskStatus":
            return
        st = c2_pb2.TaskStatus.FromString(env.payload)
        with lock:
            status.setdefault(env.header.source, []).append(
                f"{st.task_id}:{common_pb2.CommandState.Name(st.state).removeprefix('COMMAND_STATE_')}")

    subs = [bus.subscribe("truth/state", on_truth), bus.subscribe(f"swarm/{GCS}/rx/**", on_rx)]
    targets = [t for t in args.targets.split(",") if t]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not all(t in pos for t in targets):
        time.sleep(0.2)
    if not all(t in pos for t in targets):
        print(f"[probe] truth/state에 {targets} 없음")
        return 1
    with lock:
        lat = sum(pos[t][0] for t in targets) / len(targets)
        lon = sum(pos[t][1] for t in targets) / len(targets)
        alt = sum(pos[t][2] for t in targets) / len(targets)
    # 북동쪽 args.distance m
    dlat = args.distance / math.sqrt(2) / 111_320.0
    dst = (lat + dlat, lon + dlat / math.cos(math.radians(lat)), alt)
    task_id = f"probe-{int(time.time()) % 100000}-t1"
    with lock:
        t_us, frame = clock["t"], clock["frame"]
    hdr = common_pb2.Header(sim_time_us=t_us, frame=frame, source=GCS, correlation_id=task_id, seq=1)
    task = c2_pb2.TaskCommand(header=hdr, task_id=task_id, assignees=targets)
    task.move_to.destination.lat_deg, task.move_to.destination.lon_deg, task.move_to.destination.alt_m = dst
    env = link_pb2.LinkEnvelope(header=hdr, dst=targets, iface=options_pb2.L1_INTERFACE_C2,
                                msg_type="swarm.v1.TaskCommand", payload=task.SerializeToString())
    bus.put(f"swarm/{GCS}/tx/c2/TaskCommand", env.SerializeToString(),
            "application/protobuf;swarm.v1.LinkEnvelope")
    t0 = time.monotonic()
    print(f"[probe] {task_id} MoveTo {dst[0]:.5f},{dst[1]:.5f} @{dst[2]:.0f} m → {targets} (sim {t_us * 1e-6:.1f} s)")
    reached: dict[str, float] = {}
    while time.monotonic() - t0 < args.timeout and len(reached) < len(targets):
        time.sleep(0.5)
        with lock:
            for t in targets:
                n, e = ned_offset(pos[t][0], pos[t][1], dst[0], dst[1])
                if t not in reached and math.hypot(float(n), float(e)) < args.radius:
                    reached[t] = time.monotonic() - t0
    with lock:
        for t in targets:
            n, e = ned_offset(pos[t][0], pos[t][1], dst[0], dst[1])
            r = f"도달 {reached[t]:.0f} s" if t in reached else "미도달"
            print(f"[probe] {t}: {r}, 남은 거리 {math.hypot(float(n), float(e)):.0f} m, TaskStatus {status.get(t, [])}")
    for s in subs:
        s.close()
    ok = len(reached) == len(targets) and all(any(task_id in x for x in status.get(t, [])) for t in targets)
    print(f"[probe] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔·리다이렉트에서도 한국어가 깨지지 않게 한다
    for f in (sys.stdout, sys.stderr):
        f.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(prog="run_p0_demo", description="P0 데모 실행기 (docs/20_p0_demo.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--build-dir", default=str(ROOT / "build" / "msvc-debug"))
        p.add_argument("--out", default="", help="로그·기록 디렉터리 (기본 out/p0_demo/<모드>-<시각>)")
        p.add_argument("--base-port", type=int, default=17600, help="Zenoh 대기 포트 시작값")
        p.add_argument("--bridge-port", type=int, default=8765)
        p.add_argument("--ui-port", type=int, default=5173)
        p.add_argument("--monitor-port", type=int, default=5174)
        p.add_argument("--no-ui", action="store_true", help="vite dev 서버를 띄우지 않는다")
        p.add_argument("--monitor", action="store_true", help="Traffic Monitor(ui/monitor) dev 서버도 띄운다")
        p.add_argument("--settle", type=float, default=2.0, help="Core·재생기 시작 전 대기(s)")

    lv = sub.add_parser("live", help="전체 프로세스를 실제 버스로 띄운다")
    common(lv)
    lv.add_argument("--scenario", default=str(DEFAULT_SCENARIO))
    lv.add_argument("--no-record", action="store_true", help="MCAP 기록을 끈다")
    lv.add_argument("--no-autostart", action="store_true", help="Core를 LOADED로 두고 UI의 시작 버튼을 기다린다")
    lv.add_argument("--duration", type=float, default=0, help="n초 뒤 종료 (0 = Ctrl+C까지)")

    rp = sub.add_parser("replay", help="MCAP 기록을 버스에 다시 발행한다")
    common(rp)
    rp.add_argument("file")
    rp.add_argument("--rate", type=float, default=1.0)
    rp.add_argument("--linger", type=float, default=0, help="재생이 끝난 뒤 브리지·UI를 n초 더 둔다")

    pr = sub.add_parser("probe", help="MoveTo를 보내 C2 → 데이터링크 → Agent 경로를 확인한다")
    pr.add_argument("--connect", action="append", default=[], help="버스 엔드포인트 (live가 출력한 값)")
    pr.add_argument("--targets", default="uav-001,uav-002,uav-003")
    pr.add_argument("--distance", type=float, default=1500.0, help="현재 중심에서 목표까지(m, 북동)")
    pr.add_argument("--radius", type=float, default=300.0, help="도달 판정 반경(m)")
    pr.add_argument("--timeout", type=float, default=180.0)

    a = ap.parse_args(argv)
    if a.cmd == "probe" and not a.connect:
        a.connect = ["tcp/127.0.0.1:17601"]
    return {"live": cmd_live, "replay": cmd_replay, "probe": cmd_probe}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

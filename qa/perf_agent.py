"""P1 성능 측정용 Agent 실행기 (TC-QA-114~). 제품 코드를 바꾸지 않고 swarm_agent.cli를 감싸 계측한다.

qa/perf_p1.py가 띄운다. 나머지 인자는 swarm_agent.cli에 그대로 넘긴다.
--perf-mode
  plain     계측 없음 (배속 측정용)
  timers    perf_counter 누적 (함수별 시간, 메시지 종류별 건수)
  cprofile  주 스레드 cProfile (비율만 본다. 절대 시간은 부풀려진다)
  no_fa     FA step을 건너뛴다. 항법 수신은 그대로 (시간 분해용. 비행은 무의미)
"""

import argparse
import cProfile
import ctypes
import json
import pstats
import sys
import time
from collections import defaultdict
from pathlib import Path

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--perf-mode", default="plain")
ap.add_argument("--perf-out", default="")
ap.add_argument("--perf-warm", type=int, default=250)
ap.add_argument("--perf-frames", type=int, default=1250)
ap.add_argument("--perf-switch", type=float, default=0.0, help="sys.setswitchinterval. 0이면 기본값")
ap.add_argument("--perf-narrow", action="store_true", help="DEC-081 뒤에는 효과 없음(런타임이 메시지별로 구독한다). onboard/<id>/*를 받는 메시지별 구독으로 바꾼다 (자기 ControlOutput 수신 제거 효과 측정)")
A, REST = ap.parse_known_args()

from swarm_api import Sample  # noqa: E402
from swarm_api import bus as busmod  # noqa: E402

from swarm_agent import cli, runtime as rtm, vehicle as vehmod  # noqa: E402
from swarm_agent.fa import DefaultFlightAutonomy  # noqa: E402

if A.perf_switch > 0:
    sys.setswitchinterval(A.perf_switch)

pc = time.perf_counter
_k32 = ctypes.PyDLL("kernel32")  # PyDLL: GIL을 놓지 않는다. 측정이 스레드 전환을 만들지 않게 한다
_k32.GetCurrentThread.restype = ctypes.c_void_p
_k32.QueryThreadCycleTime.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulonglong)]
_h = _k32.GetCurrentThread()


def cycles() -> int:
    v = ctypes.c_ulonglong()
    _k32.QueryThreadCycleTime(_h, ctypes.byref(v))
    return v.value


def calibrate() -> float:
    """사이클 → 초. CPU를 쓰는 동안의 벽시계 대비 사이클"""
    t0, c0 = pc(), cycles()
    while pc() - t0 < 0.3:
        pass
    return (cycles() - c0) / (pc() - t0)


HZ = calibrate()
T: dict[str, float] = defaultdict(float)
N: dict[str, int] = defaultdict(int)
ST = {"on": False, "done": False, "ticks": 0, "wall0": 0.0, "wall1": 0.0, "cyc": 0, "cyc0": 0, "pt": 0.0,
      "ma0": 0.0, "fa0": 0.0, "prof": None}


def key_class(key: str) -> str:
    if key == "sim/clock/tick":
        return "tick"
    if key.startswith("sim/clock/done/"):
        return "done"
    if key.startswith("onboard/"):
        return "onboard:" + key.rsplit("/", 1)[1]
    if key.startswith("onboard_batch/"):  # DEC-081
        return "batch:" + key.split("/")[1]
    if key.startswith("swarm/"):
        p = key.split("/")
        return f"swarm:{p[2]}:{p[3]}:{p[-1]}" if len(p) >= 5 else "swarm:?"
    if key.startswith("sim/param/"):
        return "sim/param"
    return key


def timed(name, fn):
    def w(*a, **k):
        if not ST["on"]:
            return fn(*a, **k)
        t = pc()
        try:
            return fn(*a, **k)
        finally:
            T[name] += pc() - t
            N[name] += 1
    return w


def finish(rt) -> None:
    ST["on"] = False
    ST["done"] = True
    ST["wall1"] = pc()
    wall = ST["wall1"] - ST["wall0"]
    ticks = A.perf_frames
    out: dict = {"mode": A.perf_mode, "ticks": ticks, "wall_s": wall, "vehicles": len(rt.vehicles),
                 "cycles_hz": HZ, "switch": sys.getswitchinterval(),
                 "ma_ms_per_tick": 1e3 * (rt.stats.ma_s - ST["ma0"]) / ticks,
                 "fa_ms_per_tick": 1e3 * (rt.stats.fa_s - ST["fa0"]) / ticks,
                 "late_onboard": rt.stats.late_onboard}
    if A.perf_mode in ("timers", "no_fa"):
        out["ms_per_tick"] = {k: 1e3 * v / ticks for k, v in sorted(T.items())}
        out["n_per_tick"] = {k: v / ticks for k, v in sorted(N.items())}
        out["process_tick_cpu_ms"] = 1e3 * (ST["cyc"] / HZ) / ticks
    if ST["prof"] is not None:
        ST["prof"].disable()
        p = Path(A.perf_out).with_suffix(".prof")
        ST["prof"].dump_stats(str(p))
        s = pstats.Stats(str(p))
        rows = [{"func": f"{Path(f[0]).name}:{f[1]}:{f[2]}", "ncalls": v[1], "tottime": v[2], "cumtime": v[3]}
                for f, v in s.stats.items()]
        rows.sort(key=lambda r: -r["tottime"])
        out["profile_total_s"] = s.total_tt
        out["profile"] = rows[:150]
    Path(A.perf_out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


_orig_init = rtm.AgentRuntime.__init__


def _init(self, *a, **k):
    _orig_init(self, *a, **k)
    if A.perf_mode in ("timers", "no_fa") and self._queue is not None:
        self._queue.get = timed("queue_get", self._queue.get)


rtm.AgentRuntime.__init__ = _init
_orig_tick = rtm.AgentRuntime._process_tick


def _process_tick(self, tick):
    measuring = ST["on"]
    t = pc()
    c = cycles() if measuring else 0
    _orig_tick(self, tick)
    if measuring:
        dt = pc() - t
        ST["cyc"] += cycles() - c
        T["process_tick"] += dt
        N["process_tick"] += 1
        ST["pt"] += dt
    ST["ticks"] += 1
    if A.perf_out and not ST["done"]:
        if not ST["on"] and ST["ticks"] == A.perf_warm:
            ST["ma0"], ST["fa0"], ST["wall0"], ST["on"] = self.stats.ma_s, self.stats.fa_s, pc(), True
            T.clear()
            N.clear()
            if A.perf_mode == "cprofile":
                ST["prof"] = cProfile.Profile()
                ST["prof"].enable()
        elif ST["on"] and ST["ticks"] == A.perf_warm + A.perf_frames:
            finish(self)


rtm.AgentRuntime._process_tick = _process_tick

if A.perf_mode in ("timers", "no_fa"):
    # 버스 콜백 전체 (Zenoh 스레드). 키 종류별. GIL 안에서 더하므로 드물게 덜 셀 수 있다
    def subscribe(self, keyexpr, callback):
        def on_sample(z):
            t = pc()
            s = Sample(str(z.key_expr), z.payload.to_bytes(), str(z.encoding))
            callback(s)
            if ST["on"]:
                c = "cb:" + key_class(s.key)
                T[c] += pc() - t
                N[c] += 1
        return busmod._ZenohSubscription(self._session.declare_subscriber(keyexpr, on_sample))
    busmod.ZenohBus.subscribe = subscribe

    _put = busmod.ZenohBus.put

    def put(self, key, payload, encoding):
        if not ST["on"]:
            return _put(self, key, payload, encoding)
        t = pc()
        _put(self, key, payload, encoding)
        c = "put:" + key_class(key)
        T[c] += pc() - t
        N[c] += 1
        T["put_bytes:" + key_class(key)] += len(payload) / 1e3  # /틱으로 나누면 ms가 아니라 바이트(ms_per_tick 값이 곧 B/틱)
    busmod.ZenohBus.put = put

    # 주 스레드 입력 처리: _process_tick을 뺀 순수 해석·분배 시간
    _handle = rtm.AgentRuntime._handle

    def handle(self, s):
        if not ST["on"]:
            return _handle(self, s)
        p0, t = ST["pt"], pc()
        _handle(self, s)
        c = "h:" + key_class(s.key)
        T[c] += pc() - t - (ST["pt"] - p0)
        N[c] += 1
    rtm.AgentRuntime._handle = handle

    for name in ("_release_rx", "_release_onboard", "_report_activity", "_send_done", "publish_onboard", "send_link",
                 "_apply_params", "_publish_params_due", "_step", "_publish_controls", "_on_nav_batch"):
        setattr(rtm.AgentRuntime, name, timed(name, getattr(rtm.AgentRuntime, name)))
    vehmod.Vehicle.begin_frame = timed("begin_frame", vehmod.Vehicle.begin_frame)
    DefaultFlightAutonomy.step = timed("fa_step", DefaultFlightAutonomy.step)

if A.perf_narrow:
    class _Multi:
        def __init__(self, subs):
            self.subs = subs

        def close(self):
            for s in self.subs:
                s.close()

    _sub = busmod.ZenohBus.subscribe

    def narrow(self, keyexpr, callback):
        if keyexpr.startswith("onboard/") and keyexpr.endswith("/*"):
            return _Multi([_sub(self, keyexpr[:-1] + n, callback) for n in sorted(rtm.ONBOARD_INBOUND)])
        return _sub(self, keyexpr, callback)
    busmod.ZenohBus.subscribe = narrow

if A.perf_mode == "no_fa":
    DefaultFlightAutonomy.step = lambda self, nav, dt: None

sys.exit(cli.main(REST))

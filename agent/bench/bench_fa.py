"""FA·런타임 성능 측정 (IMP-AGT-010). 기본 FA를 C++로 옮길지 정하는 근거 자료.

uv run python agent/bench/bench_fa.py [--n 20 100 300] [--seconds 20] [--ma hold]

측정 항목
- fa_step_us: DefaultFlightAutonomy.step 한 번(Waypoint 모드) 평균 µs. 버스·직렬화 없음
- frame_ms: 런타임의 프레임 처리 평균 ms. NavigationBatch 해석 + 틱(MA + FA + ControlBatch
  직렬화·발행 + FrameDone). 버스는 발행을 버리는 NullBus라 전송 비용은 빠진다
- fa_ms: 그중 FA 구간(step + ControlBatch 발행)
- rt_x: 50 Hz에서 런타임만의 최대 배속 = 20 ms / frame_ms
"""

import argparse
import time

from swarm.v1 import sim_pb2, vi_pb2
from swarm_api import Sample, keys
from swarm_agent import AgentRuntime, RuntimeConfig
from swarm_agent.fa import DefaultFlightAutonomy
from swarm_agent.geo import offset_geo
from swarm_agent.testing import make_scenario


class NullBus:
    def put(self, key, payload, encoding):
        pass

    def subscribe(self, keyexpr, callback):
        return self

    def close(self):
        pass


def bench_fa_step(iters: int = 200_000) -> float:
    fa = DefaultFlightAutonomy()
    fa.on_init("uav-001", {})
    cmd = vi_pb2.FlightCommand(command_id="w")
    wp = cmd.waypoint.waypoints.add()
    wp.position.lat_deg, wp.position.lon_deg = (float(x) for x in offset_geo(37.5, 128.0, 1e6, 0.0))
    fa.on_command(cmd)
    nav = vi_pb2.NavigationReport()
    k = nav.kinematics
    k.position.lat_deg, k.position.lon_deg, k.position.alt_m = 37.5, 128.0, 1500.0
    k.velocity_ned_mps.x, k.velocity_ned_mps.y = 20.0, 5.0
    t0 = time.perf_counter()
    for _ in range(iters):
        fa.step(nav, 0.02)
    return (time.perf_counter() - t0) / iters * 1e6


def bench_runtime(n: int, seconds: float, ma: str) -> tuple[float, float, float]:
    sc = make_scenario(n, ma, spacing_m=300.0)
    rt = AgentRuntime(NullBus(), RuntimeConfig())
    rt.load(sc)
    batch = vi_pb2.NavigationBatch()
    for e in sc.entities[1:]:
        nav = batch.reports.add()
        nav.header.source = e.id
        nav.kinematics.CopyFrom(e.initial)
    frames = round(seconds * 50)
    t_total = 0.0
    for f in range(frames):
        t_us = f * 20000
        batch.header.frame, batch.header.sim_time_us = f, t_us
        for nav in batch.reports:
            nav.header.frame, nav.header.sim_time_us = f, t_us
            # 위치를 조금씩 옮겨 FA가 매번 다른 입력을 받게 한다
            nav.kinematics.position.lat_deg += 1e-6
        samples = [Sample(keys.NAVIGATION_BATCH, batch.SerializeToString(), "")]
        tick = sim_pb2.ClockTick(frame=f, sim_time_us=t_us, dt_us=20000, mode=sim_pb2.RUN_MODE_LOCKSTEP)
        samples.append(Sample(keys.CLOCK_TICK, tick.SerializeToString(), ""))
        t0 = time.perf_counter()
        for s in samples:
            rt.handle(s)
        t_total += time.perf_counter() - t0
    st = rt.stats
    return 1e3 * t_total / frames, 1e3 * st.fa_s / st.ticks, 1e3 * st.ma_s / st.ticks


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, nargs="+", default=[20, 100, 300])
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--ma", default="hold")
    a = p.parse_args()
    print(f"fa_step_us={bench_fa_step():.1f}")
    print("n,ma,frame_ms,fa_ms,ma_ms,rt_x_at_50hz")
    for n in a.n:
        frame_ms, fa_ms, ma_ms = bench_runtime(n, a.seconds, a.ma)
        print(f"{n},{a.ma},{frame_ms:.3f},{fa_ms:.3f},{ma_ms:.3f},{20.0 / frame_ms:.1f}")


if __name__ == "__main__":
    main()

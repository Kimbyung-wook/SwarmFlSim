"""실행 파일 swarm-agent (IMP-AGT-008, DEC-026).

시나리오는 sim/ctrl/cmd의 LoadScenario로 받는다. --scenario를 주면 시작할 때 파일에서도 읽는다
(swarm_core --scenario로 시작해 LoadScenario가 버스에 나오지 않는 경우).
"""

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from google.protobuf import json_format

from swarm.v1 import sim_pb2
from swarm_api import BusConfig, open_bus

from .plugins import PluginRegistry
from .runtime import AgentRuntime, RuntimeConfig

log = logging.getLogger("swarm_agent")


def add_bus_args(p: argparse.ArgumentParser) -> None:
    """공통 버스 옵션 (docs/10_contracts.md §3.4)"""
    g = p.add_argument_group("bus")
    g.add_argument("--bus", default="", help="zenoh | memory (기본: zenoh가 있으면 zenoh)")
    g.add_argument("--zenoh-config", default="", help="Zenoh 설정 파일")
    g.add_argument("--zenoh-mode", default="", help="peer | client | router")
    g.add_argument("--connect", action="append", default=[], help="연결 엔드포인트 (반복 가능)")
    g.add_argument("--listen", action="append", default=[], help="수신 엔드포인트 (반복 가능)")
    g.add_argument("--no-multicast", action="store_true", help="멀티캐스트 탐색을 끈다")


def bus_config(a: argparse.Namespace) -> BusConfig:
    return BusConfig(backend=a.bus, zenoh_config_file=a.zenoh_config, zenoh_mode=a.zenoh_mode,
                     connect=a.connect, listen=a.listen, multicast_scouting=not a.no_multicast)


def read_scenario(path: str) -> sim_pb2.Scenario:
    """.pb(swarm.v1.Scenario 바이너리), proto JSON, 또는 시나리오 JSON(swarm_scenario가 있을 때)"""
    p = Path(path)
    data = p.read_bytes()
    if p.suffix != ".json":
        return sim_pb2.Scenario.FromString(data)
    try:
        return json_format.Parse(data.decode("utf-8"), sim_pb2.Scenario())
    except json_format.ParseError:
        pass
    try:
        import swarm_scenario
    except ImportError as e:
        raise SystemExit(f"{path}: not proto JSON, and swarm_scenario is not installed") from e
    return swarm_scenario.to_proto(swarm_scenario.load(p))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="swarm-agent", description="Vehicle Agent 런타임 (WP3)")
    p.add_argument("--participant", default="agent-0", help="lockstep 참여자 ID (sim/clock/done/<id>)")
    p.add_argument("--entities", action="append", default=[],
                   help="맡을 기체 ID, 쉼표 구분·반복 가능. 없으면 AutonomySpec이 있는 기체 전부")
    p.add_argument("--scenario", default="", help="시작할 때 읽을 시나리오 파일")
    p.add_argument("--frames", type=int, default=0, help="n 틱 처리 후 종료")
    p.add_argument("--activity-max-hz", type=float, default=10.0,
                   help="임무장비 상태 변화 보고의 키별 최대 빈도(Hz, 모의 시간). 키는 Sensor·Jammer가 (메시지, payload_id), "
                        "Strike가 (메시지, payload_id, weapon_entity). 0 이하면 제한 없음. "
                        "1 Hz 전체 보고는 이와 별개 (DEC-056, DEC-063)")
    p.add_argument("--list-plugins", action="store_true", help="등록된 MA/FA 플러그인 이름을 출력하고 종료")
    p.add_argument("-v", "--verbose", action="store_true")
    add_bus_args(p)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    registry = PluginRegistry()
    if a.list_plugins:
        print("swarm.ma:", ", ".join(registry.names("swarm.ma")))
        print("swarm.fa:", ", ".join(registry.names("swarm.fa")))
        return 0
    entities = {e for arg in a.entities for e in arg.split(",") if e} or None
    bus = open_bus(bus_config(a))
    rt = AgentRuntime(bus, RuntimeConfig(participant=a.participant, entities=entities,
                                         activity_max_hz=a.activity_max_hz), registry, threaded=True)
    if a.scenario:
        rt.load(read_scenario(a.scenario))

    stop = False

    def on_signal(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, on_signal)
    log.info("swarm-agent participant=%s ready", a.participant)
    t0 = time.perf_counter()
    try:
        rt.run(max_frames=a.frames, should_stop=lambda: stop)
    finally:
        s = rt.stats
        wall = time.perf_counter() - t0
        if s.ticks:
            fs = sorted(s.frame_s)
            log.info("ticks=%d vehicles=%d wall=%.1fs ma=%.3fms/tick fa=%.3fms/tick frame p50=%.3fms p99=%.3fms",
                     s.ticks, len(rt.vehicles), wall, 1e3 * s.ma_s / s.ticks, 1e3 * s.fa_s / s.ticks,
                     1e3 * fs[len(fs) // 2], 1e3 * fs[int(len(fs) * 0.99)])
        rt.close()
        bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

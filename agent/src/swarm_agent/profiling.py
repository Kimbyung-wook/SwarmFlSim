"""틱 단계별 계측 (IMP-AGT-042, DEC-086). 기본은 꺼져 있다.

켜는 법: `swarm-agent --profile <파일>` 또는 환경 변수 `SWARM_AGENT_PROFILE=<파일>`.
틱 처리(_process_tick)의 단계와 틱 사이 입력 처리(키 종류별)를 벽시계(perf_counter)로 재고,
프레임 위상(frame % 50, 1 Hz 주기 안의 자리)별로 더한다. 입력 처리 시간은 그 뒤에 처리한 틱의 위상에 넣는다
(프레임 P의 입력은 틱 P 앞에 온다). 결과는 `flush_every` 틱마다와 닫을 때 JSON으로 덮어쓴다(측정 도구가 프로세스를
강제로 끝내도 남게 한다). 의미·순서·발행 내용은 바꾸지 않는다.

JSON: {"ticks", "skip", "period", "phases": {위상: {"frames", "ms": {단계: 합계 ms}, "n": {단계: 횟수}}},
       "summary": {"phase0"|"phase4"|"other"|"all": {"frames", "ms_per_frame": {단계: ms}, "n_per_frame": {...}}}}
"""

import json
import os
import time
from collections import defaultdict
from pathlib import Path

PERIOD = 50          # 50 Hz에서 1 s
ENV = "SWARM_AGENT_PROFILE"


class TickProfile:
    def __init__(self, path: str | os.PathLike, skip: int = 250, flush_every: int = 500, period: int = PERIOD) -> None:
        self.path = Path(path)
        self.skip = skip                      # 앞의 틱은 버린다(적재·워밍업)
        self.flush_every = flush_every
        self.period = period
        self.ticks = 0
        self._ms: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._n: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._frames: dict[int, int] = defaultdict(int)
        self._pending: dict[str, float] = defaultdict(float)   # 다음 틱에 넣을 입력 처리 시간
        self._pending_n: dict[str, int] = defaultdict(int)
        self._tick: dict[str, float] = {}
        self._tick_n: dict[str, int] = defaultdict(int)
        self._last_done: float | None = None

    # ---- 입력 (틱 사이) ----

    def add_input(self, cls: str, dt: float) -> None:
        self._pending[cls] += dt
        self._pending_n[cls] += 1

    # ---- 틱 ----

    def begin_tick(self) -> None:
        self._tick = defaultdict(float)
        self._tick_n = defaultdict(int)

    def add(self, stage: str, dt: float, n: int = 1) -> None:
        self._tick[stage] += dt
        self._tick_n[stage] += n

    def end_tick(self, frame: int, total: float) -> None:
        now = time.perf_counter()
        self.ticks += 1
        if self.ticks > self.skip:
            ph = frame % self.period
            ms, n = self._ms[ph], self._n[ph]
            self._frames[ph] += 1
            for k, v in self._pending.items():
                ms["in:" + k] += 1e3 * v
                n["in:" + k] += self._pending_n[k]
            for k, v in self._tick.items():
                ms[k] += 1e3 * v
                n[k] += self._tick_n[k]
            ms["tick_total"] += 1e3 * total
            n["tick_total"] += 1
            ms["inputs_total"] += 1e3 * sum(self._pending.values())
            if self._last_done is not None:
                ms["done_to_done"] += 1e3 * (now - self._last_done)   # 지난 FrameDone 뒤 이번 FrameDone까지 벽시계
        self._last_done = now
        self._pending.clear()
        self._pending_n.clear()
        if self.flush_every and self.ticks > self.skip and (self.ticks - self.skip) % self.flush_every == 0:
            self.flush()

    # ---- 결과 ----

    def summary(self) -> dict:
        groups = {"phase0": [0], "phase4": [4], "other": [p for p in range(self.period) if p not in (0, 4)],
                  "all": list(range(self.period))}
        out = {}
        for g, phs in groups.items():
            frames = sum(self._frames.get(p, 0) for p in phs)
            ms, n = defaultdict(float), defaultdict(int)
            for p in phs:
                for k, v in self._ms.get(p, {}).items():
                    ms[k] += v
                for k, v in self._n.get(p, {}).items():
                    n[k] += v
            out[g] = {"frames": frames,
                      "ms_per_frame": {k: round(v / frames, 4) for k, v in sorted(ms.items())} if frames else {},
                      "n_per_frame": {k: round(v / frames, 3) for k, v in sorted(n.items())} if frames else {}}
        return out

    def flush(self) -> None:
        data = {"ticks": self.ticks, "skip": self.skip, "period": self.period, "summary": self.summary(),
                "phases": {str(p): {"frames": self._frames[p], "ms": {k: round(v, 3) for k, v in sorted(self._ms[p].items())},
                                    "n": dict(sorted(self._n[p].items()))} for p in sorted(self._frames)}}
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


def input_class(key: str) -> str:
    """입력 키 → 계측 분류"""
    if key == "sim/clock/tick":
        return "tick"
    if key.startswith("sim/clock/done/"):
        return "done"
    if key.startswith("onboard_batch/"):
        return "nav_batch"
    if key.startswith("onboard/"):
        return "onboard:" + key.rsplit("/", 1)[1]
    if key.startswith("swarm/"):
        p = key.split("/")
        return f"rx:{p[3]}:{p[-1]}" if len(p) >= 5 else "rx:?"
    return "other:" + key

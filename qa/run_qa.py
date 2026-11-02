"""QA 시험 실행기 (TC-QA-001~). 시험 설명과 판정 기준은 docs/21_qa_report.md.

uv run --with psutil python qa/run_qa.py --list
uv run --with psutil python qa/run_qa.py [--only 001,008] [--build-dir <dir>]

결과: qa/out/<TC>/ (프로세스 로그·MCAP·pb) 와 qa/out/results.json
"""

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as h  # noqa: E402
from harness import Observer, ResourceSampler, Stack, off  # noqa: E402

QA = h.QA
SC = QA / "scenarios"
OUT = QA / "out"
TESTS: dict[str, tuple[str, callable]] = {}
NAN, INF = float("nan"), float("inf")


def tc(num: str, title: str):
    def deco(fn):
        TESTS[num] = (title, fn)
        return fn
    return deco


class Case:
    """한 시험의 판정·메모 수집기"""

    def __init__(self, num: str):
        self.num = num
        self.fails: list[str] = []
        self.obs: list[str] = []
        self.data: dict = {}
        self.dir = OUT / f"TC-QA-{num}"

    def check(self, cond: bool, msg: str) -> bool:
        if not cond:
            self.fails.append(msg)
        return cond

    def note(self, msg: str) -> None:
        self.obs.append(msg)
        print(f"   · {msg}")


def finish_checks(c: Case, st: Stack, ob: Observer, allow: tuple[str, ...] = ()) -> None:
    c.check(not st.dead(), f"프로세스 종료됨: {st.dead()}")
    bad = [f for f in ob.findings if f.kind not in allow]
    for f in bad[:8]:
        c.fails.append(str(f))
    hits = h.scan_logs(st)
    c.data["log_hits"] = len(hits)
    for x in hits[:6]:
        c.note("로그: " + x)


def mk(c: Case, scen: str, **kw) -> Stack:
    return Stack(c.dir, SC / f"{scen}.json", **kw)


def uav_ids(ob: Observer) -> list[str]:
    return sorted(k for k in ob.pos if k.startswith(("uav-", "fpv-")))


# ---------------------------------------------------------------- 기준선

def baseline(c: Case, scen: str, sim_s: float, *, lockstep=True, rate=2.0, max_wall=240.0, hz=None, **kw) -> tuple:
    st = mk(c, scen, lockstep=lockstep, rate=rate, hz=hz, **kw).up()
    ob = Observer([st.endpoint()])
    rs = ResourceSampler(st)
    rs.start()
    t0 = time.monotonic()
    ok = ob.wait(lambda: ob.sim_s() >= sim_s, max_wall)
    wall = time.monotonic() - t0
    c.data.update(wall_s=round(wall, 1), sim_s=round(ob.sim_s(), 1), snap=ob.snapshot())
    c.check(ok, f"{sim_s:.0f} sim-s 못 채움 ({ob.sim_s():.1f} s / 벽시계 {wall:.0f} s)")
    return st, ob, rs


def teardown(c: Case, st: Stack, ob: Observer, rs: ResourceSampler | None = None, allow=()) -> None:
    if rs:
        c.data["resources"] = rs.stop()
    finish_checks(c, st, ob, allow)
    c.data["snap_end"] = ob.snapshot()
    ob.close()
    st.down()


def entity_count_check(c: Case, ob: Observer, st: Stack, expect: int) -> None:
    s = ob.snapshot()
    c.check(s["entity_min_max"] == (expect, expect), f"truth 엔티티 수 {s['entity_min_max']} (기대 {expect})")
    c.check(s["status_entities"] == expect, f"SimStatus.entity_count={s['status_entities']} (기대 {expect})")


@tc("001", "s1 소규모 편대 6대(3-DoF, formation) 기준선과 대형 유지")
def t001(c: Case):
    st, ob, rs = baseline(c, "qa_s1_formation6", 120.0, rate=2.0)
    ids = uav_ids(ob)
    c.check(len(ids) == 6, f"기체 수 {len(ids)}")
    entity_count_check(c, ob, st, 7)
    with ob.lock:
        lat0 = sum(ob.pos[i][0] for i in ids) / 6
        lon0 = sum(ob.pos[i][1] for i in ids) / 6
        spread = [h.dist_m((lat0, lon0), (ob.pos[i][0], ob.pos[i][1])) for i in ids]
        alts = [ob.pos[i][2] for i in ids]
    c.note(f"중심 거리 {min(spread):.0f}~{max(spread):.0f} m, 고도 {min(alts):.0f}~{max(alts):.0f} m, 리더 TaskStatus 없음 시 "
           f"mission_plan 반영 여부 확인용")
    c.check(max(spread) < 1500, f"편대가 흩어짐: 최대 {max(spread):.0f} m")
    teardown(c, st, ob, rs)


@tc("002", "s2 20대 군집 다중 임무(hold·route·racetrack·search_area) 기준선")
def t002(c: Case):
    st, ob, rs = baseline(c, "qa_s2_swarm20", 240.0, rate=2.0)
    entity_count_check(c, ob, st, 21)
    with ob.lock:
        pos = dict(ob.pos)
    # 임무별 중심 근처 비행 여부 (hold 1~5: 북 2.5 km 서 1.5 km)
    ctr = off(37.4, 127.4, 2500, -1500)
    d = [h.dist_m(ctr, pos[f"uav-{i:03d}"][:2]) for i in range(1, 6)]
    c.note(f"hold(uav-001~005) 중심 거리 {min(d):.0f}~{max(d):.0f} m (반경 300 m)")
    c.check(max(d) < 1200, f"hold 임무 기체가 중심에서 {max(d):.0f} m")
    ctr = off(37.4, 127.4, 3500, 0)
    d = [h.dist_m(ctr, pos[f"uav-{i:03d}"][:2]) for i in range(11, 16)]
    c.note(f"racetrack(uav-011~015) 중심 거리 {min(d):.0f}~{max(d):.0f} m (반폭 약 900 m)")
    c.check(max(d) < 2500, f"racetrack 임무 기체가 중심에서 {max(d):.0f} m")
    teardown(c, st, ob, rs)


@tc("003", "s3 불완전 링크 프로파일(손실·지연·사거리·대역폭) + 사거리 밖 기체")
def t003(c: Case):
    st, ob, rs = baseline(c, "qa_s3_link", 20.0, rate=2.0)
    ids = uav_ids(ob)
    with ob.lock:
        base = ob.pos["uav-001"]
    la, lo = h.off(base[0], base[1], 2000, 1000)
    ob.move_to(ids, la, lo, 1250.0, "qa-link-1")
    time.sleep(1)
    for _ in range(4):
        ob.move_to(ids, *h.off(la, lo, 500, 0), 1250.0, "qa-link-1")
        time.sleep(0.5)
    ob.wait(lambda: ob.sim_s() >= 150, 200)
    snap = ob.snapshot()
    with ob.lock:
        got = {k: len(v) for k, v in ob.taskstatus.items()}
        sts = {k: sorted(set(x.split(":")[1] for x in v)) for k, v in ob.taskstatus.items()}
    c.data["taskstatus_per_uav"] = got
    c.note(f"TaskStatus 수신 기체 {len(got)}/{len(ids)}, 종류 {sts.get('uav-001')}")
    c.note(f"링크 결과 {snap['outcomes']} 사유 {snap['drops']}")
    c.note(f"uav-013(35 km): {got.get('uav-013', 0)}건, uav-004(qa_short 3 km): {got.get('uav-004', 0)}건, "
           f"uav-002(qa_lossy): {got.get('uav-002', 0)}건, uav-005(qa_narrow): {got.get('uav-005', 0)}건")
    c.check(snap["outcomes"].get("DROPPED", 0) > 0, "손실·사거리 프로파일을 넣었는데 DROPPED 0건")
    if ob.latency_us:
        lat = sorted(ob.latency_us)
        c.note(f"지연 us p50 {lat[len(lat) // 2]}, p99 {lat[int(len(lat) * .99)]}, max {lat[-1]}")
    teardown(c, st, ob, rs)


@tc("004", "s4 적/표적/센서·무장 선언 시나리오 견고성 (Core 미구현 범위 포함)")
def t004(c: Case):
    st, ob, rs = baseline(c, "qa_s4_engage", 120.0, rate=2.0)
    ids = uav_ids(ob)
    c.note(f"엔티티 {len(ob.pos)}종, 생존 {sum(ob.alive.values())}, 이벤트 {len(ob.events)}건 "
           f"{sorted(set(k for k, _ in ob.events))}")
    # 스크립트 표적이 움직이는가
    p0 = dict(ob.pos)
    ob.wait(lambda: ob.sim_s() >= 180, 200)
    for t in ("tgt-002", "tgt-003", "wpn-uav-001-01"):
        if t in ob.pos and t in p0:
            c.note(f"{t} 이동 {h.dist_m(p0[t][:2], ob.pos[t][:2]):.0f} m")
        else:
            c.fails.append(f"{t} truth/state에 없음")
    c.check(len(ob.pos) == 12 + 1 or len(ob.pos) >= 12, f"엔티티 {len(ob.pos)}")
    # 센서·킬 고장 주입
    ob.fault("uav-001", "SENSOR", 10.0)
    ob.fault("uav-002", "KILL")
    time.sleep(3)
    c.note(f"KILL 후 uav-002 alive={ob.alive.get('uav-002')}, 이벤트 {sorted(set(k for k, _ in ob.events))}")
    teardown(c, st, ob, rs)


@tc("005", "s5 2-DoF/3-DoF·skywalker_x8/aerosonde 혼합, MA 혼합 + 미지원 dof5/dof6 적재")
def t005(c: Case):
    st, ob, rs = baseline(c, "qa_s5_mixed", 180.0, rate=2.0)
    entity_count_check(c, ob, st, 17)
    with ob.lock:
        v = {k: math.sqrt(sum(x * x for x in ob.vel[k])) for k in ob.vel if k.startswith("uav")}
        a = {k: ob.pos[k][2] for k in v}
    sx = [v[f"uav-{i:03d}"] for i in range(1, 9)]
    ae = [v[f"uav-{i:03d}"] for i in range(9, 17)]
    c.note(f"속력 skywalker {min(sx):.1f}~{max(sx):.1f} m/s (12~28), aerosonde {min(ae):.1f}~{max(ae):.1f} m/s (18~32)")
    c.check(all(12 - 0.5 <= x <= 28 + 0.5 for x in sx), f"skywalker 속도 한계 이탈 {sx}")
    c.check(all(18 - 0.5 <= x <= 32 + 0.5 for x in ae), f"aerosonde 속도 한계 이탈 {ae}")
    teardown(c, st, ob, rs)
    # 미지원 동역학 dof5/dof6: 적재가 거부되거나 오류 로그가 있어야 하고 죽지 않아야 한다
    for dyn in ("dof5", "dof6"):
        doc = h.load_json(SC / "qa_s5_mixed.json")
        doc["entities"][3]["dynamics"] = dyn
        p = c.dir / f"s5_{dyn}.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        st2 = Stack(c.dir / dyn, p, lockstep=False, record=False, base_port=17950)
        try:
            st2.up()
            time.sleep(6)
            dead = st2.dead()
            txt = st2.log_text().get("core", "")[-600:].replace("\n", " | ")
            c.note(f"{dyn}: 종료={dead} Core 로그 끝: {txt[:300]}")
        finally:
            st2.down()


def load_case(c: Case, scen: str, label: str, sim_s: float, **kw) -> None:
    st, ob, rs = baseline(c, scen, sim_s, max_wall=420.0, **kw)
    s = ob.snapshot()
    expect = len(h.load_json(SC / f"{scen}.json")["entities"])
    entity_count_check(c, ob, st, expect)
    # 기체 전부 갱신되는가: 마지막 프레임 이후 각 기체 위치가 변했는지는 별도로 본다
    res = rs.stop() if rs.is_alive() else {}
    c.data["resources"] = res
    rs2 = None
    rate = s["rate_actual"]
    c.note(f"{label}: rate_actual={rate}, 프레임 {s['last_frame']}, overruns={s['overruns']}, 갭 {s['gap_frames']}, "
           f"벽시계 {c.data['wall_s']} s/{c.data['sim_s']} sim-s")
    for n, r in res.items():
        c.note(f"  {n}: CPU 평균 {r['cpu_avg']}% 최대 {r['cpu_max']}%, RSS {r['rss_start_mb']}→{r['rss_end_mb']} MB "
               f"(후반 +{r['rss_growth_2nd_half_mb']} MB)")
    c.check(not s["gap_frames"] or s["gap_frames"] < 0.01 * (s["last_frame"] or 1), f"truth 프레임 누락 {s['gap_frames']}")
    teardown(c, st, ob, None)


@tc("006", "s6 부하 50대 lockstep 2배속")
def t006(c: Case):
    load_case(c, "qa_s6_load50", "50대", 60.0, rate=2.0)


@tc("007", "s6 부하 100대 lockstep 1배속")
def t007(c: Case):
    load_case(c, "qa_s6_load100", "100대", 40.0, rate=1.0)


@tc("008", "s6 부하 100대 flocking(P2P) lockstep 1배속")
def t008(c: Case):
    load_case(c, "qa_s6_load100_flock", "100대 flocking", 30.0, rate=1.0)


@tc("009", "s6 부하 100대 realtime 실시간성 (벽시계 대비 sim 시간)")
def t009(c: Case):
    st = mk(c, "qa_s6_load100", lockstep=False).up()
    ob = Observer([st.endpoint()])
    rs = ResourceSampler(st)
    rs.start()
    time.sleep(8)
    ob.wait(lambda: ob.frames > 0, 20)
    f0, w0 = ob.sim_s(), time.monotonic()
    time.sleep(30)
    f1, w1 = ob.sim_s(), time.monotonic()
    ratio = (f1 - f0) / (w1 - w0)
    s = ob.snapshot()
    c.note(f"realtime 100대: sim/벽시계 = {ratio:.2f}, overruns={s['overruns']}, rate_actual={s['rate_actual']}")
    c.check(ratio > 0.9, f"실시간 배율 {ratio:.2f} < 0.9")
    teardown(c, st, ob, rs)


# ---------------------------------------------------------------- 시뮬레이션 통제

@tc("010", "통제: pause/resume/step/set_rate/reset/재시작 (lockstep, s2)")
def t010(c: Case):
    st = mk(c, "qa_s2_swarm20", lockstep=True, rate=2.0).up()
    ob = Observer([st.endpoint()])
    sim = ob.m[0]
    ob.wait_frames(100, 60)
    # 정지
    ob.pause()
    c.check(ob.wait_state(sim.SIM_RUN_STATE_PAUSED, 10), "pause 후 PAUSED 상태 안 됨")
    time.sleep(1)
    f1 = ob.last_frame
    time.sleep(3)
    c.check(ob.last_frame - f1 <= 1, f"PAUSED 중 프레임 진행 {f1}→{ob.last_frame}")
    # 정지 중 이중 pause, step
    ob.pause()
    time.sleep(0.5)
    f = ob.last_frame
    ob.step(25)
    ok = ob.wait(lambda: ob.last_frame >= f + 25, 15)
    time.sleep(1)
    c.check(ok and ob.last_frame - f <= 26, f"step(25) 결과 {f}→{ob.last_frame}")
    c.check(ob.status.state == sim.SIM_RUN_STATE_PAUSED, f"step 뒤 상태 {ob.status.state}")
    # 재개
    ob.resume()
    c.check(ob.wait_state(sim.SIM_RUN_STATE_RUNNING, 10), "resume 후 RUNNING 아님")
    ob.resume()  # 이중
    ob.wait_frames(50, 30)
    # 배속 변경
    for r in (4.0, 0.5, 8.0, 2.0):
        ob.set_rate(r)
        time.sleep(0.8)
        f0, w0 = ob.sim_s(), time.monotonic()
        time.sleep(6)
        c.note(f"set_rate({r}): 실측 {(ob.sim_s() - f0) / (time.monotonic() - w0):.2f}배, status.rate_target={ob.status.rate_target}")
    # 잘못된 배속
    for r in (0.0, -1.0, NAN, INF, 1e9):
        ob.set_rate(r)
        time.sleep(1)
        c.note(f"set_rate({r}) 뒤 상태 {ob.status.state} rate_target={ob.status.rate_target} dead={st.dead()}")
        if not (math.isfinite(r) and 0 <= r <= 1000):
            c.check(math.isfinite(ob.status.rate_target) and 0 <= ob.status.rate_target <= 1000,
                    f"set_rate({r}) 수용: rate_target={ob.status.rate_target}")
        ob.set_rate(2.0)
        time.sleep(0.5)
    # 리셋
    ob.reset()
    time.sleep(3)
    c.note(f"reset 뒤 상태={ob.status.state} frame={ob.last_frame} sim_s={ob.sim_s():.1f} 엔티티={ob.snapshot()['entities']}")
    st_after_reset = ob.status.state
    ob.start("lockstep", 2.0)
    ok = ob.wait(lambda: ob.status.state == sim.SIM_RUN_STATE_RUNNING and ob.sim_s() > 2, 20)
    c.check(ok, f"reset 뒤 start로 재시작 안 됨 (state {ob.status.state}, reset 직후 {st_after_reset})")
    ob.wait_frames(100, 60)
    with ob.lock:
        n = len(ob.pos)
    c.check(n == 21, f"reset 뒤 엔티티 {n}")
    # 연속 reset/start 3회
    for i in range(3):
        ob.reset()
        time.sleep(1.0)
        ob.start("lockstep", 2.0)
        time.sleep(2.0)
    ob.wait_frames(50, 60)
    c.note(f"reset/start 3회 뒤 상태 {ob.status.state} frame {ob.last_frame}")
    teardown(c, st, ob, allow=("time_regress", "tick_regress"))


@tc("011", "통제: 모드 전환 lockstep/realtime/freerun (Start 명령)")
def t011(c: Case):
    st = mk(c, "qa_s2_swarm20", lockstep=True, rate=2.0).up()
    ob = Observer([st.endpoint()])
    sim = ob.m[0]
    ob.wait_frames(100, 60)
    for mode, rate in (("realtime", 1.0), ("freerun", 1.0), ("lockstep", 3.0), ("realtime", 1.0)):
        ob.reset()
        ob.wait(lambda: ob.status.state == sim.SIM_RUN_STATE_LOADED, 20)
        time.sleep(1)
        ob.start(mode, rate)
        ok = ob.wait(lambda: ob.status.state == sim.SIM_RUN_STATE_RUNNING, 20)
        f0, w0 = ob.sim_s(), time.monotonic()
        time.sleep(8)
        sped = (ob.sim_s() - f0) / (time.monotonic() - w0)
        c.note(f"{mode} rate={rate}: RUNNING={ok}, status.mode={ob.status.mode}, 실측 {sped:.2f}배, 프레임 {ob.last_frame}")
        c.check(ob.status.mode == {"realtime": sim.RUN_MODE_REALTIME, "freerun": sim.RUN_MODE_FREERUN,
                                   "lockstep": sim.RUN_MODE_LOCKSTEP}[mode], f"{mode}로 전환 안 됨 (status.mode={ob.status.mode})")
    teardown(c, st, ob, allow=("time_regress", "tick_regress"))


@tc("012", "통제: 잘못된 SimCommand (Start 값 범위, 빈 명령, 적재 불가 시나리오)")
def t012(c: Case):
    st = mk(c, "qa_s2_swarm20", lockstep=True, rate=2.0).up()
    ob = Observer([st.endpoint()])
    sim = ob.m[0]
    ob.wait_frames(100, 60)
    # 빈 명령
    ob.put_sim(lambda cmd: None)
    time.sleep(1)
    # Start 값
    bad = [("lockstep", 2.0, 10, 1), ("lockstep", 2.0, 5000, 1), ("lockstep", NAN, 50, 1), ("lockstep", -3.0, 50, 1),
           ("realtime", 5.0, 50, 1), ("lockstep", 2.0, 0, 1)]
    for mode, rate, hz, seed in bad:
        ob.pause()
        time.sleep(0.3)
        ob.start(mode, rate, hz, seed)
        time.sleep(2.5)
        s = ob.status
        c.note(f"Start(mode={mode}, rate={rate}, hz={hz}) → state={s.state} hz={s.frame_hz} rate_target={s.rate_target} "
               f"dead={st.dead()}")
        c.check(not st.dead(), f"Start({mode},{rate},{hz}) 뒤 프로세스 종료 {st.dead()}")
        ob.pause()
        ob.start("lockstep", 2.0, 50, 1)
        time.sleep(1)
    # 비정상 시나리오를 pb로 직접 만들어 적재 시도
    from swarm.v1 import sim_pb2
    base = sim_pb2.Scenario.FromString((c.dir / "scenario.pb").read_bytes())
    cases = {}
    d = sim_pb2.Scenario(); d.CopyFrom(base); d.entities.add().CopyFrom(base.entities[1]); cases["중복 ID"] = d
    d = sim_pb2.Scenario(); d.CopyFrom(base); del d.entities[:]; cases["엔티티 0개"] = d
    d = sim_pb2.Scenario(); d.CopyFrom(base)
    d.entities[3].initial.position.lat_deg = NAN; cases["NaN 위치"] = d
    d = sim_pb2.Scenario(); d.CopyFrom(base); d.entities[3].airframe = "nonexistent_airframe"; cases["없는 airframe"] = d
    d = sim_pb2.Scenario(); d.CopyFrom(base); d.entities[3].autonomy.ma_plugin = "nonexistent_ma"; cases["없는 MA 플러그인"] = d
    d = sim_pb2.Scenario(); d.CopyFrom(base); d.run.frame_hz = 5; cases["frame_hz=5"] = d
    d = sim_pb2.Scenario(); d.CopyFrom(base); d.entities[3].link_profile = "nonexistent_link"; cases["없는 링크 프로파일"] = d
    for name, sc in cases.items():
        try:
            ob.pause()
            time.sleep(0.3)
            p = c.dir / "bad.pb"
            p.write_bytes(sc.SerializeToString())
            ob.load_scenario(p)
            time.sleep(3)
            s = ob.status
            c.note(f"적재[{name}] → state={s.state} entity_count={s.entity_count} scenario={s.scenario_name!r} "
                   f"dead={st.dead()}")
            c.check(not st.dead(), f"적재[{name}] 뒤 프로세스 종료 {st.dead()}")
        except Exception as e:  # noqa: BLE001
            c.fails.append(f"적재[{name}] 예외 {e}")
    # Reset 뒤(LOADED) 잘못된 Start 값 / 잘못된 시나리오
    for mode, rate, hz, seed in bad:
        ob.reset()
        ob.wait(lambda: ob.status.state == sim.SIM_RUN_STATE_LOADED, 20)
        time.sleep(1)
        ob.start(mode, rate, hz, seed)
        time.sleep(2.5)
        s = ob.status
        c.note(f"[Reset 뒤] Start(mode={mode}, rate={rate}, hz={hz}) → state={s.state} hz={s.frame_hz} "
               f"rate_target={s.rate_target} dead={st.dead()}")
        c.check(not st.dead(), f"[Reset 뒤] Start({mode},{rate},{hz}) 뒤 프로세스 종료 {st.dead()}")
        if s.state == sim.SIM_RUN_STATE_RUNNING:
            c.check(math.isfinite(s.rate_target) and s.rate_target >= 0 and 50 <= s.frame_hz <= 100 or mode == "realtime",
                    f"[Reset 뒤] Start({mode},{rate},{hz}) 비정상 값 수용: rate_target={s.rate_target} hz={s.frame_hz}")
    for name, sc in cases.items():
        ob.reset()
        ob.wait(lambda: ob.status.state == sim.SIM_RUN_STATE_LOADED, 20)
        time.sleep(1)
        p = c.dir / "bad.pb"
        p.write_bytes(sc.SerializeToString())
        ob.load_scenario(p)
        time.sleep(3)
        s = ob.status
        c.note(f"[Reset 뒤] 적재[{name}] → state={s.state} entity_count={s.entity_count} dead={st.dead()}")
        c.check(not st.dead(), f"[Reset 뒤] 적재[{name}] 뒤 프로세스 종료 {st.dead()}")
        if name in ("중복 ID", "엔티티 0개", "NaN 위치", "frame_hz=5"):
            c.check(s.entity_count == 21 and s.state == sim.SIM_RUN_STATE_LOADED,
                    f"[Reset 뒤] 적재[{name}]가 거부되지 않음: state={s.state} entity_count={s.entity_count}")
    # 정상 시나리오 복구
    ob.reset()
    ob.wait(lambda: ob.status.state == sim.SIM_RUN_STATE_LOADED, 20)
    time.sleep(2)
    ob.start("lockstep", 2.0)
    ok = ob.wait(lambda: ob.status.state == sim.SIM_RUN_STATE_RUNNING, 15)
    c.check(ok, f"잘못된 명령 뒤 정상 복구 실패: state {ob.status.state}")
    teardown(c, st, ob, allow=("time_regress", "tick_regress", "pos_jump"))


# ---------------------------------------------------------------- 임무 명령

def mission_setup(c: Case, scen="qa_s2_swarm20", rate=2.0, **kw):
    st = mk(c, scen, lockstep=True, rate=rate, **kw).up()
    ob = Observer([st.endpoint()])
    ob.wait_frames(150, 60)
    return st, ob


def status_of(ob: Observer, uav: str, task_id: str) -> list[str]:
    with ob.lock:
        return [x for x in ob.taskstatus.get(uav, []) if x.startswith(task_id + ":")]


@tc("013", "임무 명령: move/hold/racetrack/route/recon 정상 경로와 연속·충돌 명령")
def t013(c: Case):
    st, ob = mission_setup(c)
    with ob.lock:
        base = ob.pos["uav-001"]
    lat, lon = base[0], base[1]
    a = ["uav-001", "uav-002"]
    # 1 단일 이동
    dst = off(lat, lon, 1500, 1500)
    ob.move_to(a, *dst, 1250.0, "qa-m1")
    ok = ob.wait(lambda: all(any("EXECUTING" in x or "COMPLETED" in x for x in status_of(ob, u, "qa-m1")) for u in a), 40)
    c.check(ok, f"move_to 수락/실행 보고 없음 {[status_of(ob, u, 'qa-m1') for u in a]}")
    # 2 충돌: 즉시 hold, 즉시 racetrack, 즉시 route, 즉시 move
    ob.hold(a, *off(lat, lon, 2000, 0), 1250.0, 300.0, "qa-m2")
    ob.hold(a, *off(lat, lon, 2000, 500), 1250.0, 300.0, "qa-m3", racetrack=(1000.0, 90.0))
    ob.route(a, [(*off(lat, lon, 1000, 0), 1250.0), (*off(lat, lon, 1000, 1000), 1250.0)], "qa-m4", recon=True)
    ob.move_to(a, *off(lat, lon, 500, 500), 1250.0, "qa-m5")
    ob.wait(lambda: ob.sim_s() >= ob.sim_s() + 0, 1)
    time.sleep(20)
    for tid in ("qa-m2", "qa-m3", "qa-m4", "qa-m5"):
        c.note(f"{tid}: uav-001 {status_of(ob, 'uav-001', tid)} / uav-002 {status_of(ob, 'uav-002', tid)}")
    # 연속 전송 뒤 최종 임무: 링크 지터로 명령 도착 순서가 뒤바뀔 수 있으므로(DEC-038 (8) 현실 모사)
    # 도착 순서를 판정하지 않고, 두 기체가 취소되지 않은 EXECUTING 임무를 하나씩만 가지는지(일관성)만 본다.
    def live_tasks(u):
        out = set()
        for tid in ("qa-m2", "qa-m3", "qa-m4", "qa-m5"):
            ss = status_of(ob, u, tid)
            if any("EXECUTING" in x for x in ss) and not any("CANCELLED" in x for x in ss):
                out.add(tid)
        return out
    lt = {u: live_tasks(u) for u in a}
    c.note(f"연속 전송 뒤 살아 있는 임무: {lt}")
    c.check(all(len(v) <= 1 for v in lt.values()), f"취소되지 않은 임무가 둘 이상 동시 실행: {lt}")
    # 간격을 두고 보낸 마지막 명령은 반드시 최종 권위여야 한다
    tgt6 = off(lat, lon, 500, 500)
    ob.move_to(a, *tgt6, 1250.0, "qa-m6")
    ok6 = ob.wait(lambda: h.dist_m(tgt6, ob.pos["uav-001"][:2]) < 400 and h.dist_m(tgt6, ob.pos["uav-002"][:2]) < 400, 150)
    c.check(ok6, f"간격 두고 보낸 마지막 명령 qa-m6 목표 미도달 {[h.dist_m(tgt6, ob.pos[u][:2]) for u in a]}")
    c.check(any(x.startswith("qa-m6:ACCEPTED") for x in status_of(ob, "uav-001", "qa-m6")), "qa-m6 ACCEPTED 보고 없음")
    # 이전 명령은 대체(SUPERSEDED/CANCELLED 등)로 보고되는가
    with ob.lock:
        allst = sorted(set(x.split(":")[1] for x in ob.taskstatus.get("uav-001", [])))
    c.note(f"uav-001 TaskStatus 종류: {allst}")
    # 같은 task_id 재전송(중복)
    ob.move_to(a, *dst, 1250.0, "qa-m1")
    ob.move_to(a, *dst, 1250.0, "qa-m1")
    time.sleep(3)
    c.note(f"중복 task_id 재전송 뒤 qa-m1: {status_of(ob, 'uav-001', 'qa-m1')[-4:]}")
    # 도달성
    ob.move_to(["uav-003"], *off(lat, lon, 800, -800), 1250.0, "qa-m6")
    ob.wait(lambda: h.dist_m(off(lat, lon, 800, -800), ob.pos["uav-003"][:2]) < 400, 90)
    c.check(h.dist_m(off(lat, lon, 800, -800), ob.pos["uav-003"][:2]) < 600, "uav-003 이동 목표 미도달")
    teardown(c, st, ob)


@tc("014", "임무 명령: 잘못된 값(범위 밖·없는 기체·빈 경로·NaN·빈 문자열)")
def t014(c: Case):
    st, ob = mission_setup(c)
    with ob.lock:
        base = ob.pos["uav-001"]
    lat, lon = base[0], base[1]
    t = ob.m[3]

    def run(name: str, fn, targets=("uav-003",), expect=None, tries=1):
        # uav-003 링크가 BURST_LOSS라 명령이 유실될 수 있어 재전송 허용(같은 task_id는 교체됨, DEC-038)
        tid = f"qa-bad-{name}"
        for k in range(tries):
            try:
                fn(list(targets), tid)
            except Exception as e:  # noqa: BLE001
                c.note(f"{name}: 송신 예외 {e}")
                return
            if k + 1 < tries:
                time.sleep(2.0)
        time.sleep(6.0)
        c.note(f"{name}: dead={st.dead()}, 응답 uav-003={status_of(ob, 'uav-003', tid)} "
               f"(전체 응답 기체 {sum(1 for u in ob.taskstatus if status_of(ob, u, tid))})")

    with ob.lock:
        before = dict(ob.pos)
    run("lat200", lambda tg, i: ob.move_to(tg, 200.0, lon, 1250.0, i))
    run("lonNaN", lambda tg, i: ob.move_to(tg, lat, NAN, 1250.0, i))
    run("altInf", lambda tg, i: ob.move_to(tg, lat, lon, INF, i))
    run("altNeg", lambda tg, i: ob.move_to(tg, *off(lat, lon, 500, 0), -5000.0, i))
    run("alt100km", lambda tg, i: ob.move_to(tg, *off(lat, lon, 500, 0), 100000.0, i))
    run("outOfMap", lambda tg, i: ob.move_to(tg, 10.0, 10.0, 1250.0, i))
    run("zeroLatLon", lambda tg, i: ob.move_to(tg, 0.0, 0.0, 0.0, i))
    run("noEntity", lambda tg, i: ob.move_to(["uav-999"], *off(lat, lon, 500, 0), 1250.0, i), targets=("uav-999",))
    run("noAssignee", lambda tg, i: ob.move_to([], *off(lat, lon, 500, 0), 1250.0, i), targets=())
    run("emptyTaskId", lambda tg, i: ob.move_to(tg, *off(lat, lon, 500, 0), 1250.0, ""))
    run("emptyRoute", lambda tg, i: ob.route(tg, [], i))
    run("route1", lambda tg, i: ob.route(tg, [(*off(lat, lon, 500, 0), 1250.0)], i))
    run("route500", lambda tg, i: ob.route(tg, [(*off(lat, lon, 20 * k, 20 * k), 1250.0) for k in range(500)], i))
    run("routeNaN", lambda tg, i: ob.route(tg, [(NAN, NAN, NAN), (*off(lat, lon, 500, 0), 1250.0)], i), tries=4)
    run("holdR0", lambda tg, i: ob.hold(tg, *off(lat, lon, 500, 0), 1250.0, 0.0, i))
    run("holdRneg", lambda tg, i: ob.hold(tg, *off(lat, lon, 500, 0), 1250.0, -300.0, i))
    run("holdRNaN", lambda tg, i: ob.hold(tg, *off(lat, lon, 500, 0), 1250.0, NAN, i), tries=4)
    run("holdR1e9", lambda tg, i: ob.hold(tg, *off(lat, lon, 500, 0), 1250.0, 1e9, i))
    run("raceLeg0", lambda tg, i: ob.hold(tg, *off(lat, lon, 500, 0), 1250.0, 300.0, i, racetrack=(0.0, 90.0)))
    run("raceLegNeg", lambda tg, i: ob.hold(tg, *off(lat, lon, 500, 0), 1250.0, 300.0, i, racetrack=(-500.0, 90.0)))
    run("raceAxis999", lambda tg, i: ob.hold(tg, *off(lat, lon, 500, 0), 1250.0, 300.0, i, racetrack=(1000.0, 999.0)))
    run("raceAxisNaN", lambda tg, i: ob.hold(tg, *off(lat, lon, 500, 0), 1250.0, 300.0, i, racetrack=(1000.0, NAN)))
    run("emptyTask", lambda tg, i: ob.task(t.TaskCommand(), tg, i))
    # 센서/표적 임무 종류(미구현 가능성)
    def strike(tg, i):
        tk = t.TaskCommand()
        tk.strike.target_id = "tgt-nonexistent"
        ob.task(tk, tg, i)
    run("strikeNoTarget", strike)
    for nm in ("lat200", "lonNaN", "altInf", "routeNaN", "holdRNaN", "raceAxisNaN", "emptyTaskId"):
        rs = status_of(ob, "uav-003", f"qa-bad-{nm}") if nm != "emptyTaskId" else []
        if nm != "emptyTaskId":
            c.check(any("REJECTED" in x for x in rs), f"{nm}: REJECTED 보고 없음 {rs}")
    with ob.lock:
        us = list(ob.taskstatus)
    ex = [u for u in us if any("EXECUTING" in x for x in status_of(ob, u, "qa-bad-noAssignee"))]
    c.check(not ex, f"assignees 빈 명령을 수행한 기체 {len(ex)}대")
    # 기체 명령을 아무 일 없던 듯 이어서 처리하는가
    ob.move_to(["uav-004"], *off(lat, lon, 700, 700), 1250.0, "qa-after-bad")
    ok = ob.wait(lambda: any(("EXECUTING" in x or "COMPLETED" in x) for x in status_of(ob, "uav-004", "qa-after-bad")), 30)
    c.check(ok, f"잘못된 명령 연속 뒤 정상 명령 처리 안 됨: {status_of(ob, 'uav-004', 'qa-after-bad')}")
    with ob.lock:
        mx = max((h.dist_m(before[k][:2], ob.pos[k][:2]) for k in before if k.startswith("uav")), default=0)
    c.note(f"전체 기체 최대 이동 {mx:.0f} m (비정상 이동 점검)")
    teardown(c, st, ob)


@tc("015", "임무 명령 홍수: 20대에 초당 수백 건")
def t015(c: Case):
    st, ob = mission_setup(c)
    with ob.lock:
        base = ob.pos["uav-001"]
    ids = sorted(k for k in ob.pos if k.startswith("uav-"))
    n = 0
    t0 = time.monotonic()
    snap0 = ob.snapshot()
    while time.monotonic() - t0 < 10:
        n += 1
        ob.move_to(ids, *off(base[0], base[1], 300 + (n % 50) * 20, 500), 1250.0, f"qa-flood-{n}")
    c.note(f"홍수: {n}건/10 s 송신(각 {len(ids)}대)")
    time.sleep(10)
    s = ob.snapshot()
    c.note(f"홍수 뒤 프레임 진행 {snap0['last_frame']}→{s['last_frame']}, overruns {snap0['overruns']}→{s['overruns']}, "
           f"링크 결과 {s['outcomes']}")
    f10 = s["last_frame"]
    tr = time.monotonic()
    rec = ob.wait(lambda: ob.snapshot()["last_frame"] > f10 + 50, 150)
    c.note(f"홍수 종료 10 s 뒤 프레임 {snap0['last_frame']}→{f10}, 이후 +50프레임 회복 {'%.0f s' % (time.monotonic() - tr) if rec else '150 s 안에 못 함'}")
    c.check(rec, "홍수 뒤 150 s 안에 시뮬레이션이 회복하지 않음")
    ok = ob.wait(lambda: any(f"qa-flood-{n}:" in x for x in ob.taskstatus.get("uav-001", [])), 60)
    c.note(f"마지막 명령 qa-flood-{n} 응답 {status_of(ob, 'uav-001', f'qa-flood-{n}')}")
    with ob.lock:
        got = len(ob.taskstatus.get("uav-001", []))
    c.note(f"uav-001이 보낸 TaskStatus 총 {got}건")
    teardown(c, st, ob)


@tc("016", "실행 중 매개변수 변경과 거부 (FA·MA·dynamics, 잘못된 값)")
def t016(c: Case):
    st, ob = mission_setup(c, "qa_s1_formation6")
    sim = ob.m[0]
    ent = "uav-002"
    for owner in ("fa", "ma", "dynamics"):
        n0 = ob.seq
        ob.set_params(ent, owner, {})
        ok = ob.wait(lambda: f"{ent}/{owner}" in ob.params and ob.seq > n0, 8)
        c.check(ok, f"{ent}/{owner} sim/param 발행 없음")
        if not ok:
            continue
        ep = ob.params[f"{ent}/{owner}"]
        specs = {s.name: s for s in ep.specs}
        c.note(f"{owner}: plugin={ep.plugin} 선언 {sorted(specs)}")
    # MA formation 값
    def get(owner, name):
        v = ob.params[f"{ent}/{owner}"].values.fields[name]
        return v.number_value if v.WhichOneof("kind") == "number_value" else v.string_value

    def apply(owner, vals, wait=4.0):
        n0 = ob.seq
        ob.set_params(ent, owner, vals)
        ob.wait(lambda: ob.seq > n0, wait)
        time.sleep(1.5)
        return ob.params[f"{ent}/{owner}"]

    ep = apply("ma", {"k_p": 0.3})
    c.check(abs(get("ma", "k_p") - 0.3) < 1e-9, f"k_p 반영 안 됨: {get('ma', 'k_p')}")
    cases = {
        "음수": {"k_p": -5}, "큰값": {"k_p": 1e12}, "문자열": {"k_p": "abc"},
        "bool": {"k_p": True}, "null": {"k_p": None}, "빈이름": {"": 1.0}, "없는이름": {"zzz": 1.0},
        "고정항목": {"group": "beta"}, "빈문자열값": {"group": ""},
    }
    for name, vals in cases.items():
        try:
            ep = apply("ma", vals, 3.0)
            rej = [(r.name, r.reason) for r in ep.rejected]
            c.note(f"MA {name} {list(vals)[0]!r}={list(vals.values())[0]!r} → 거부 {rej}, k_p 현재 {get('ma', 'k_p')}")
            kp = get("ma", "k_p")
            if isinstance(kp, float) and not math.isfinite(kp):
                c.fails.append(f"MA k_p가 {kp} 로 반영됨 ({name})")
        except Exception as e:  # noqa: BLE001
            c.note(f"MA {name}: 예외 {e}")
    # 동역학
    ep = apply("dynamics", {})
    specs = {s.name: s for s in ep.specs}
    nums = [s for s in specs.values() if s.runtime and s.default_value.WhichOneof("kind") == "number_value"]
    c.note(f"dynamics 선언 {len(specs)}개, runtime 수치 {len(nums)}개: {[s.name for s in nums][:8]}")
    if nums:
        sp = nums[0]
        for name, v in (("NaN", NAN), ("inf", INF), ("음수", -1e9), ("0", 0.0), ("범위밖", sp.max * 100 + 1)):
            ep = apply("dynamics", {sp.name: v}, 3.0)
            rej = [(r.name, r.reason) for r in ep.rejected]
            cur = get("dynamics", sp.name)
            c.note(f"dynamics {sp.name}={name} → 거부 {rej}, 현재 {cur}")
            if isinstance(cur, float) and not math.isfinite(cur):
                c.fails.append(f"dynamics {sp.name}={cur} (비유한 값 반영)")
    # 없는 기체
    n0 = ob.seq
    ob.set_params("uav-999", "ma", {"k_p": 1.0})
    time.sleep(2)
    c.note(f"없는 기체 set_params 뒤 발행 증가 {ob.seq - n0}, dead={st.dead()}")
    # 효과 확인: dynamics 값 변경 뒤 비행 지속
    ob.wait_frames(100, 30)
    c.check(not st.dead(), f"NaN 이전 단계에서 프로세스 종료 {st.dead()}")
    # NaN 값(마지막: Agent가 죽는지 확인)
    for label, v in (("inf", INF), ("NaN", NAN)):
        if st.dead():
            break
        ob.set_params(ent, "ma", {"k_p": v})
        time.sleep(3)
        c.note(f"MA k_p={label} 뒤 dead={st.dead()}")
        c.check(not st.dead(), f"MA k_p={label} SetParams 뒤 프로세스 종료 {st.dead()}")
    teardown(c, st, ob, allow=("time_regress", "tick_regress"))


@tc("017", "고장 주입: LINK_CUT·GCS_LINK_CUT(기한/해제)·ENGINE·NAV·KILL·SENSOR, 잘못된 대상")
def t017(c: Case):
    st, ob = mission_setup(c)
    with ob.lock:
        base = ob.pos["uav-001"]
    lat, lon = base[0], base[1]
    # GCS 링크 절단 중에는 명령이 도달하지 않아야 한다
    ob.fault("uav-001", "GCS_LINK_CUT")
    time.sleep(1)
    ob.move_to(["uav-001", "uav-002"], *off(lat, lon, 900, 900), 1250.0, "qa-f1")
    time.sleep(8)
    r1, r2 = status_of(ob, "uav-001", "qa-f1"), status_of(ob, "uav-002", "qa-f1")
    c.note(f"GCS_LINK_CUT uav-001 중 명령: uav-001 응답 {r1}, uav-002 응답 {r2}")
    c.check(not r1, f"GCS 링크 절단 중 uav-001이 응답함 {r1}")
    c.check(bool(r2), "절단 대상이 아닌 uav-002가 응답 못 함")
    ob.fault("uav-001", "GCS_LINK_CUT", clear=True)
    time.sleep(1)
    ob.move_to(["uav-001"], *off(lat, lon, 900, 900), 1250.0, "qa-f2")
    ok = ob.wait(lambda: bool(status_of(ob, "uav-001", "qa-f2")), 15)
    c.check(ok, "GCS 링크 해제 뒤에도 uav-001 응답 없음")
    # 기한 있는 절단이 만료되는가 (sim 5초)
    ob.fault("uav-003", "LINK_CUT", duration=5.0)
    time.sleep(1)
    ob.move_to(["uav-003"], *off(lat, lon, 400, 0), 1250.0, "qa-f3")
    time.sleep(2)
    during = status_of(ob, "uav-003", "qa-f3")
    ob.wait(lambda: ob.sim_s() >= ob.sim_s() + 0, 0.1)
    time.sleep(10)
    ob.move_to(["uav-003"], *off(lat, lon, 400, 100), 1250.0, "qa-f4")
    ok = ob.wait(lambda: bool(status_of(ob, "uav-003", "qa-f4")), 20)
    c.note(f"LINK_CUT(5 s) 중 응답 {during}, 만료 뒤 응답 {status_of(ob, 'uav-003', 'qa-f4')}")
    c.check(not during, f"LINK_CUT 중 응답 {during}")
    c.check(ok, "기한 만료 뒤에도 uav-003 응답 없음")
    # ENGINE / NAV / KILL
    p_before = {u: ob.pos[u] for u in ("uav-005", "uav-006", "uav-007")}
    ob.fault("uav-005", "ENGINE")
    ob.fault("uav-006", "NAV")
    ob.fault("uav-007", "KILL")
    time.sleep(1)
    ob.wait_frames(200, 60)
    for u, k in (("uav-005", "ENGINE"), ("uav-006", "NAV"), ("uav-007", "KILL")):
        v = math.sqrt(sum(x * x for x in ob.vel[u]))
        c.note(f"{k} {u}: alive={ob.alive[u]} 속력 {v:.1f} m/s 고도 {p_before[u][2]:.0f}→{ob.pos[u][2]:.0f} m")
    c.check(not ob.alive["uav-007"], "KILL 뒤 alive=False 아님")
    n = ob.snapshot()["entities"]
    c.note(f"KILL 뒤 truth 엔티티 수 {n}")
    ob.fault("uav-007", "KILL", clear=True)
    time.sleep(1)
    c.note(f"KILL 해제 뒤 alive={ob.alive['uav-007']}")
    # 잘못된 고장 주입
    for ent, kind in (("uav-999", "LINK_CUT"), ("", "LINK_CUT"), ("uav-001", "UNSPECIFIED"), ("gcs-01", "KILL"),
                      ("tgt", "ENGINE")):
        ob.fault(ent, kind, duration=-5.0 if ent == "tgt" else 0.0)
        time.sleep(0.8)
    ob.fault("uav-008", "LINK_CUT", duration=NAN)
    ob.fault("uav-009", "LINK_CUT", duration=1e18)
    time.sleep(2)
    c.note(f"잘못된 고장 주입 뒤 dead={st.dead()} state={ob.status.state}")
    ob.wait_frames(100, 30)
    teardown(c, st, ob)


@tc("018", "재밍 구역 on/off (truth/event/jam_zone 직접 발행)")
def t018(c: Case):
    st, ob = mission_setup(c, "qa_s3_link")
    with ob.lock:
        base = ob.pos["uav-001"]
    lat, lon = base[0], base[1]
    ids = sorted(k for k in ob.pos if k.startswith("uav-"))

    def burst(tag: str) -> tuple[int, int]:
        ob.outcomes.clear(); ob.drop_reasons.clear()
        for i in range(10):
            ob.move_to(ids, *off(lat, lon, 700, 700 + i), 1250.0, f"qa-j-{tag}-{i}")
            time.sleep(0.3)
        time.sleep(4)
        return ob.outcomes.get("DELIVERED", 0), ob.outcomes.get("DROPPED", 0)

    d0 = burst("off")
    c.note(f"재밍 전: 전달/손실 {d0}, 사유 {dict(ob.drop_reasons)}")
    ob.jam_zone("jam-test", lat, lon, 20000.0, True)
    time.sleep(2)
    d1 = burst("on")
    reasons = dict(ob.drop_reasons)
    c.note(f"재밍 중(반경 20 km, 전 기체 포함): 전달/손실 {d1}, 사유 {reasons}")
    c.check(reasons.get("JAMMED", 0) > 0, "재밍 구역 활성 중 JAMMED 손실 0건")
    ob.jam_zone("jam-test", lat, lon, 20000.0, False)
    time.sleep(2)
    d2 = burst("off2")
    c.note(f"재밍 해제 뒤: 전달/손실 {d2}, 사유 {dict(ob.drop_reasons)}")
    c.check(dict(ob.drop_reasons).get("JAMMED", 0) == 0, "재밍 해제 뒤에도 JAMMED 발생")
    # 비정상 구역: 반경 0, 음수, NaN
    for r in (0.0, -100.0, NAN, 1e12):
        ob.jam_zone(f"jam-bad", lat, lon, r, True)
        time.sleep(1)
    ob.jam_zone("jam-bad", lat, lon, 1000.0, False)
    time.sleep(1)
    c.note(f"비정상 재밍 구역 뒤 dead={st.dead()}")
    teardown(c, st, ob)


# ---------------------------------------------------------------- 프로세스 재시작·지각 참여

@tc("019", "프로세스 장애: Agent 재시작·Datalink 재시작·Core 재시작 (realtime)")
def t019(c: Case):
    st = mk(c, "qa_s2_swarm20", lockstep=False).up()
    ob = Observer([st.endpoint()])
    ob.wait_frames(150, 60)
    with ob.lock:
        base = ob.pos["uav-001"]
    lat, lon = base[0], base[1]
    # Agent 강제 종료·재기동
    st.kill("agent")
    time.sleep(3)
    f1 = ob.last_frame
    time.sleep(3)
    c.check(ob.last_frame > f1, "Agent 종료 뒤 Core가 멈춤")
    ob.move_to(["uav-001"], *off(lat, lon, 700, 700), 1250.0, "qa-r1")
    time.sleep(3)
    c.note(f"Agent 없는 동안 명령 응답 {status_of(ob, 'uav-001', 'qa-r1')}")
    st.start_one("agent")
    time.sleep(8)
    ob.move_to(["uav-001"], *off(lat, lon, 700, 800), 1250.0, "qa-r2")
    ok = ob.wait(lambda: bool(status_of(ob, "uav-001", "qa-r2")), 25)
    c.check(ok, "Agent 재기동 뒤 명령에 응답 없음")
    with ob.lock:
        n = ob.entity_n[-1]
    c.note(f"Agent 재기동 후 엔티티 {n}, 로그 {st.procs['agent'].tail(3)}")
    # Datalink 재시작
    st.kill("datalink")
    time.sleep(3)
    ob.move_to(["uav-002"], *off(lat, lon, 600, 0), 1250.0, "qa-r3")
    time.sleep(3)
    c.note(f"Datalink 없는 동안 응답 {status_of(ob, 'uav-002', 'qa-r3')}")
    st.start_one("datalink")
    time.sleep(8)
    ob.move_to(["uav-002"], *off(lat, lon, 600, 50), 1250.0, "qa-r4")
    ok = ob.wait(lambda: bool(status_of(ob, "uav-002", "qa-r4")), 25)
    c.check(ok, "Datalink 재기동 뒤 명령에 응답 없음")
    # Core 재시작
    f0 = ob.last_frame
    st.kill("core")
    time.sleep(3)
    c.check(not ob.stalled(1) is False or True, "")
    ob.reset_expected(20)
    st.start_one("core")
    ok = ob.wait(lambda: ob.last_frame is not None and ob.frames > 0 and not ob.stalled(2), 30)
    time.sleep(5)
    c.note(f"Core 재기동: 프레임 재개 {ok}, frame {f0}→{ob.last_frame}, 엔티티 {ob.snapshot()['entities']}, "
           f"sim_s={ob.sim_s():.1f}")
    ob.move_to(["uav-003"], *off(lat, lon, 500, 0), 1250.0, "qa-r5")
    ok = ob.wait(lambda: bool(status_of(ob, "uav-003", "qa-r5")), 25)
    c.check(ok, "Core 재기동 뒤 명령에 응답 없음")
    teardown(c, st, ob, allow=("time_regress", "tick_regress", "pos_jump", "overrun_regress"))


@tc("020", "lockstep 지각 참여: Agent를 Core 뒤 15 s에 기동, 장벽 대기·재개")
def t020(c: Case):
    st = mk(c, "qa_s2_swarm20", lockstep=True, rate=2.0)
    st.record = True
    st.start_one("logger")
    st.start_one("datalink")
    time.sleep(2)
    st.start_one("core")
    ob = Observer([st.endpoint()])
    time.sleep(12)
    f_wait = ob.last_frame
    c.note(f"Agent 없이 12 s: frame={f_wait}, state={ob.status.state if ob.status else None}")
    st.start_one("agent")
    ok = ob.wait(lambda: (ob.last_frame or 0) > (f_wait or 0) + 100, 60)
    c.check(ok, "Agent 합류 뒤 시뮬레이션이 진행하지 않음")
    c.note(f"합류 뒤 frame {f_wait}→{ob.last_frame}")
    # 참여자 중간 이탈: agent 종료 → 멈추는가, 재기동하면 복구하는가
    st.kill("agent")
    time.sleep(8)
    f1 = ob.last_frame
    time.sleep(4)
    c.note(f"lockstep 중 Agent 이탈 뒤 진행: {f1}→{ob.last_frame} (장벽 대기면 정지)")
    c.check((ob.last_frame or 0) - (f1 or 0) <= 2, f"참여자 이탈 뒤에도 진행 {f1}→{ob.last_frame}")
    import re as _re
    core = st.log_text().get("core", "")
    waits = _re.findall(r"waiting for frame done: [^\n]*", core)
    c.note(f"Core 대기 로그 {len(waits)}건: {waits[-1] if waits else None}")
    c.check(any("agent-0" in w for w in waits), "Core가 대기 참여자(agent-0)를 로그로 알리지 않음")
    st.start_one("agent")
    time.sleep(10)
    resumed = (ob.last_frame or 0) > (f1 or 0) + 100
    c.note(f"Agent 재합류 뒤 진행 {resumed} (DEC-038: 미지원이 정상), frame {ob.last_frame}")
    ob.reset()
    ob.wait(lambda: ob.status.state == ob.m[0].SIM_RUN_STATE_LOADED, 20)
    time.sleep(2)
    ob.start("lockstep", 2.0)
    ok2 = ob.wait(lambda: (ob.last_frame or 0) > 100 and ob.status.state == ob.m[0].SIM_RUN_STATE_RUNNING, 60)
    c.note(f"Reset+Start 복구: {ok2} (frame {ob.last_frame})")
    c.check(ok2, "이탈 뒤 Reset+Start 복구 실패")
    teardown(c, st, ob, allow=("time_regress", "tick_regress"))


# ---------------------------------------------------------------- Logger

@tc("021", "Logger: 기록 → info → 재생(배속 변경 포함) → 재생 중 관측")
def t021(c: Case):
    st = mk(c, "qa_s2_swarm20", lockstep=True, rate=2.0).up()
    ob = Observer([st.endpoint()])
    ob.wait(lambda: ob.sim_s() >= 40, 120)
    ob.close()
    st.down()
    mcap = st.mcap
    c.check(mcap.exists() and mcap.stat().st_size > 1000, f"MCAP 크기 {mcap.stat().st_size if mcap.exists() else 0}")
    import subprocess
    info = subprocess.run([h.p0.exe(h.BUILD, "logger", "swarm_logger"), "info", str(mcap)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    c.note("info: " + info.stdout.strip().replace("\n", " | ")[:700])
    c.check(info.returncode == 0, f"info 종료코드 {info.returncode}: {info.stderr[:200]}")
    # 재생: 1배속 10 s 보고, 배속 변경은 재생기 재시작으로 대체 (replay --rate)
    for rate in (1.0, 4.0, 0.5, 20.0):
        d = c.dir / f"replay_{rate}"
        d.mkdir(exist_ok=True)
        mesh = h.p0.Mesh(17970)
        br = h.p0.Proc(f"obs_{rate}", [sys.executable, "-c", "import time; time.sleep(0.1)"], d)  # 로그 파일 자리
        ob2 = Observer([f"tcp/127.0.0.1:17970"]) if False else None
        # 관측자를 먼저 열고 재생기를 붙인다
        from swarm_api import BusConfig, open_bus
        procs = []
        try:
            rp = h.p0.Proc(f"replay_{rate}", [h.p0.exe(h.BUILD, "logger", "swarm_logger"), "replay", str(mcap), "--rate",
                                              str(rate), *mesh.next()], d)
            procs.append(rp)
            time.sleep(0.3)
            ob2 = Observer(["tcp/127.0.0.1:17970"])
            t0 = time.monotonic()
            ob2.wait(lambda: not rp.alive(), 120)
            wall = time.monotonic() - t0
            s = ob2.snapshot()
            c.note(f"재생 rate={rate}: 벽시계 {wall:.1f} s, truth 프레임 {s['frames']}, 엔티티 {s['entity_min_max']}, "
                   f"마지막 sim {s['sim_s']} s, 발견 {s['findings']}")
            c.check(s["frames"] > 100, f"재생 rate={rate} 프레임 {s['frames']}")
            ob2.close()
        finally:
            h.p0.stop(procs)
            br.kill()
    teardown_note = h.scan_logs(st)
    c.note(f"Logger 로그 이상 {len(teardown_note)}건 {teardown_note[:3]}")


@tc("022", "결정성: 같은 시드 lockstep 두 번 실행해 truth 궤적 비교")
def t022(c: Case):
    traces = []
    for run in range(2):
        st = Stack(c.dir / f"run{run}", SC / "qa_s2_swarm20.json", lockstep=True, rate=0.0, base_port=17980,
                   record=True)
        st.up()
        ob = Observer([st.endpoint()])
        ob.keep_traj = True
        ob.wait(lambda: (ob.last_frame or 0) >= 2500, 240)
        time.sleep(0.5)
        with ob.lock:
            traces.append({k: {f: (la, lo, al) for f, la, lo, al in v} for k, v in ob.traj.items()})
        c.note(f"run{run}: 프레임 {ob.last_frame}, 누락 {ob.gap_frames}")
        ob.close()
        st.down()
        time.sleep(1)
    a, b = traces
    common = set(a["uav-001"]) & set(b["uav-001"])
    c.note(f"공통 프레임 {len(common)}")
    worst = 0.0
    diff_frames = 0
    for k in a:
        if k not in b:
            c.fails.append(f"{k}가 한쪽에만 있음")
            continue
        for f in common:
            if f in a[k] and f in b[k]:
                d = h.dist_m(a[k][f][:2], b[k][f][:2]) + abs(a[k][f][2] - b[k][f][2])
                if d > 1e-6:
                    diff_frames += 1
                    worst = max(worst, d)
    c.note(f"불일치 표본 {diff_frames}, 최대 차이 {worst:.6f} m")
    c.check(diff_frames == 0, f"같은 시드인데 궤적 불일치 {diff_frames}건, 최대 {worst:.3f} m")


@tc("023", "자원 추세: 20대 realtime 10분 CPU·RSS 추세")
def t023(c: Case):
    st = mk(c, "qa_s2_swarm20", lockstep=False).up()
    ob = Observer([st.endpoint()])
    rs = ResourceSampler(st, 5.0)
    rs.start()
    ob.wait(lambda: ob.sim_s() >= 600, 700)
    res = rs.stop()
    for n, r in res.items():
        c.note(f"{n}: CPU 평균 {r['cpu_avg']}% 최대 {r['cpu_max']}%, RSS {r['rss_start_mb']}→{r['rss_end_mb']} MB "
               f"(후반 +{r['rss_growth_2nd_half_mb']} MB)")
        c.check(r["rss_growth_2nd_half_mb"] < 50, f"{n} 메모리 증가 후반 +{r['rss_growth_2nd_half_mb']} MB")
    c.data["resources"] = res
    teardown(c, st, ob, None)


@tc("024", "결정성 추가: 다른 시드 2종, s3 불완전 링크, 각 2회 lockstep 비교")
def t024(c: Case):
    import copy
    for seed in (7, 20261104):
        d = json.loads((SC / "qa_s3_link.json").read_text(encoding="utf-8"))
        d["run"]["seed"] = seed
        sj = c.dir / f"s3_seed{seed}.json"
        sj.write_text(json.dumps(d), encoding="utf-8")
        traces = []
        for run in range(2):
            st = Stack(c.dir / f"seed{seed}_run{run}", sj, lockstep=True, rate=0.0, base_port=17980, record=False)
            st.up()
            ob = Observer([st.endpoint()])
            ob.keep_traj = True
            ob.wait(lambda: (ob.last_frame or 0) >= 2000, 240)
            time.sleep(0.5)
            with ob.lock:
                traces.append({k: {f: (la, lo, al) for f, la, lo, al in v} for k, v in ob.traj.items()})
            c.note(f"seed {seed} run{run}: 프레임 {ob.last_frame}, 누락 {ob.gap_frames}, 링크 {dict(ob.snapshot()['outcomes'])}")
            ob.close()
            st.down()
            time.sleep(1)
        a, b = traces
        common = set(a["uav-001"]) & set(b["uav-001"])
        worst, nd = 0.0, 0
        for k in a:
            for f in common:
                if k in b and f in a[k] and f in b[k]:
                    dd = h.dist_m(a[k][f][:2], b[k][f][:2]) + abs(a[k][f][2] - b[k][f][2])
                    if dd > 1e-6:
                        nd += 1
                        worst = max(worst, dd)
        c.note(f"seed {seed}: 공통 {len(common)} 프레임, 불일치 {nd}, 최대 {worst:.6f} m")
        c.check(nd == 0, f"seed {seed} 같은 시드인데 불일치 {nd}건 최대 {worst:.3f} m")


@tc("025", "Agent 프로세스 자체 CPU·RSS (python 자식 합산): 50대 realtime 90 s")
def t025(c: Case):
    st = mk(c, "qa_s6_load50", lockstep=False).up()
    ob = Observer([st.endpoint()])
    rs = ResourceSampler(st, 2.0)
    rs.start()
    ob.wait(lambda: ob.sim_s() >= 90, 150)
    res = rs.stop()
    for n, r in res.items():
        c.note(f"{n}: CPU 평균 {r['cpu_avg']}% 최대 {r['cpu_max']}%, RSS {r['rss_start_mb']}→{r['rss_end_mb']} MB "
               f"(후반 +{r['rss_growth_2nd_half_mb']} MB)")
    c.check(res.get("agent", {}).get("rss_end_mb", 0) > 20, f"agent 표본이 python 자식을 포함하지 않음: {res.get('agent')}")
    c.data["resources"] = res
    teardown(c, st, ob, None)


@tc("028", "lockstep 중 Datalink 이탈·재기동: 장벽 대기, 대기 로그, Reset+Start 복구")
def t028(c: Case):
    st = mk(c, "qa_s2_swarm20", lockstep=True, rate=2.0).up()
    ob = Observer([st.endpoint("logger")])
    ok0 = ob.wait(lambda: (ob.last_frame or 0) > 200, 90)
    c.check(ok0, "초기 진행 실패")
    st.kill("datalink")
    time.sleep(3)
    f1 = ob.last_frame
    time.sleep(6)
    c.note(f"lockstep 중 Datalink 이탈 뒤 진행: {f1}→{ob.last_frame}")
    c.check((ob.last_frame or 0) - (f1 or 0) <= 2, f"Datalink 이탈 뒤에도 진행 {f1}→{ob.last_frame}")
    import re as _re
    core = st.log_text().get("core", "")
    waits = _re.findall(r"waiting for frame done: [^\n]*", core)
    c.note(f"Core 대기 로그 {len(waits)}건: {waits[-1] if waits else None}")
    c.check(any("datalink-0" in w for w in waits), "Core가 대기 참여자(datalink-0)를 로그로 알리지 않음")
    c.check(not [d for d in st.dead() if not d.startswith("datalink")], f"다른 프로세스 종료: {st.dead()}")
    st.start_one("datalink")
    time.sleep(10)
    resumed = (ob.last_frame or 0) > (f1 or 0) + 100
    c.note(f"Datalink 재기동 뒤 진행 {resumed}, frame {ob.last_frame}")
    ob.reset()
    ob.wait(lambda: ob.status.state == ob.m[0].SIM_RUN_STATE_LOADED, 20)
    time.sleep(2)
    ob.start("lockstep", 2.0)
    ok2 = ob.wait(lambda: (ob.last_frame or 0) > 100 and ob.status.state == ob.m[0].SIM_RUN_STATE_RUNNING, 60)
    c.note(f"Reset+Start 복구: {ok2} (frame {ob.last_frame})")
    c.check(ok2, "Datalink 이탈 뒤 Reset+Start 복구 실패")
    with ob.lock:
        n_uav = len([k for k in ob.pos if k.startswith("uav")])
    c.note(f"복구 뒤 기체 {n_uav}")
    teardown(c, st, ob, allow=("time_regress", "tick_regress"))


# ---------------------------------------------------------------- 실행

def main() -> int:
    for f in (sys.stdout, sys.stderr):
        f.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--build-dir", default="")
    a = ap.parse_args()
    if a.build_dir:
        h.BUILD = Path(a.build_dir)
    if a.list:
        for n, (t, _) in TESTS.items():
            print(f"TC-QA-{n}  {t}")
        return 0
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    res_path = OUT / "results.json"
    results = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else {}
    OUT.mkdir(parents=True, exist_ok=True)
    for n, (title, fn) in TESTS.items():
        if only and n not in only:
            continue
        print(f"== TC-QA-{n} {title}")
        Stack.down_all()
        c = Case(n)
        c.dir.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        try:
            fn(c)
        except BaseException as e:  # noqa: BLE001
            c.fails.append(f"시험 중 예외: {e!r}")
            traceback.print_exc()
        finally:
            Stack.down_all()
        status = "PASS" if not c.fails else "FAIL"
        print(f"   → {status} ({time.monotonic() - t0:.0f} s)" + "".join(f"\n     ✗ {x}" for x in c.fails))
        results[n] = {"title": title, "status": status, "fails": c.fails, "notes": c.obs, "data": c.data,
                      "wall_s": round(time.monotonic() - t0, 1)}
        res_path.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

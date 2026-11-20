"""판정 로직 (docs/44_standards_conformance.md C1~C7). 입력은 평범한 dict·list이고 프로세스·파일을 건드리지 않는다.

각 판정 함수는 {"verdict": 통과|실패|정보, "fail": [사유...], ...세부} 를 돌려준다. 단위 시험(tests/test_judges.py)이
일부러 위반을 넣은 입력으로 이 함수들이 실패를 내는지 본다.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from confcommon import FAIL, INFO, PASS

# ---------------------------------------------------------------------------------------------------------- 공용


def verdict(fails: list, info_only: bool = False) -> str:
    if info_only:
        return INFO
    return FAIL if fails else PASS


# ---------------------------------------------------------------------------------------------------------- C1


INSIDE = "Gateway 범위 밖(기체 내부)"


def judge_c1(proto: list[dict], xsd: set[str], converters: list[dict], also: list[dict], registry: list[dict],
             trace: dict[str, dict], effective_import: list[str], observed: set[str] | None = None,
             scope: dict[str, dict] | None = None) -> dict:
    """적용 범위 표와 실패 조건(STD의 uci_name·uci_also가 XSD에 없음, GCS 경계 STD인데 변환기 없음, 변환기는 있는데 STD 아님).

    scope: static.contract_scope 결과(DEC-094). 계약상 swarm 밖 키로만 오가고 Gateway 변환기도 없는 STD는 기체 내부로 보고
    변환기 없음을 실패로 보지 않는다. 변환기가 있으면 실제로 경계를 넘으므로 GCS 경계다(계약과 다르면 정보로 적는다).
    scope가 없으면 모든 STD를 GCS 경계로 본다(DEC-094 전 동작).
    """
    fails: list[str] = []
    info: list[str] = []
    by_full = {p["full_name"]: p for p in proto}
    conv = {c["proto"]: c for c in converters}
    also_by = {a["uci"]: a for a in also}
    std = [p for p in proto if p["mapping"] == "STD"]
    scope = scope or {}
    inside: dict[str, bool] = {}
    for p in std:
        sc = scope.get(p["short"], {})
        has_conv = p["full_name"] in conv or any(also_by.get(u) for u in p["uci_also"])
        inside[p["short"]] = bool(sc.get("inside")) and not has_conv
        if sc.get("inside") and has_conv:
            info.append(f"{p['short']}: 계약 키 표로는 swarm 밖 키({', '.join(sc['named_keys'])})로만 오가지만 Gateway 변환기가 "
                        "있어 GCS 경계로 본다")
    for p in std:
        if not p["uci_name"]:
            fails.append(f"{p['short']}: STD인데 uci_name이 없다")
        elif p["uci_name"] not in xsd:
            fails.append(f"{p['short']}: uci_name {p['uci_name']}이 XSD 최상위 요소에 없다")
        for u in p["uci_also"]:
            if u not in xsd:
                fails.append(f"{p['short']}: uci_also {u}이 XSD 최상위 요소에 없다")
            a = also_by.get(u)
            if not inside[p["short"]] and (a is None or (a["protos"] and p["full_name"] not in a["protos"])):
                fails.append(f"{p['short']}: STD인데 uci_also {u} 변환기가 없다")
        if p["full_name"] not in conv and not inside[p["short"]]:
            fails.append(f"{p['short']} ({p['uci_name']}): STD인데 변환기가 없다")
    for c in converters:
        p = by_full.get(c["proto"])
        if p is None or p["mapping"] != "STD":
            fails.append(f"변환기 {c['cls']}({c['proto']}): 대응 메시지가 STD가 아니다 "
                         f"({p['mapping'] if p else 'proto에 없음'})")
    used_also = {u for p in std for u in p["uci_also"]}
    for a in also:
        if a["uci"] not in used_also:
            fails.append(f"추가 변환기 {a['cls']}({a['uci']}): 어느 STD 메시지의 uci_also에도 없다")

    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    imp = set(effective_import)
    observed = observed or set()

    def row_for(l1: str, inter: str, uci: str, p: dict | None, src: str) -> dict:
        if p is None:
            return {"l1": l1, "interaction": inter, "uci": uci, "dir": "—", "cls": "STD", "internal": "—",
                    "converter": "없음", "imp": "", "tc": "", "status": "미구현", "source": src}
        c = conv.get(p["full_name"])
        is_also = uci in p["uci_also"]
        has = (also_by.get(uci) is not None) if is_also else (c is not None)
        if uci in imp:
            direction = "수신"
        elif has and (is_also or c["export"]):
            direction = "송신"
        else:
            direction = "—"
        tr = trace.get(p["short"], {})
        tr_u = trace.get(uci, {})
        imps = sorted(set(tr.get("imp", [])) | set(tr_u.get("imp", [])))
        tcs = sorted(set(tr.get("tc", [])) | set(tr_u.get("tc", [])))
        if p["mapping"] == "STD" and inside.get(p["short"]):
            status = INSIDE
        elif not has or p["mapping"] != "STD":
            status = "미구현"
        elif uci in observed and imps and tcs:
            status = "구현·시험됨"
        else:
            status = "부분"
        return {"l1": l1, "interaction": inter, "uci": uci, "dir": direction, "cls": p["mapping"],
                "internal": p["short"], "converter": "있음" if has else "없음", "imp": ", ".join(imps),
                "tc": ", ".join(tcs), "status": status, "source": src, "observed": uci in observed,
                "scope": "기체 내부" if inside.get(p["short"]) else "GCS 경계",
                "scope_why": _scope_why(scope.get(p["short"], {}), inside.get(p["short"], False))}

    by_uci: dict[str, list[dict]] = defaultdict(list)
    for p in std:
        for u in [p["uci_name"], *p["uci_also"]]:
            if u:
                by_uci[u].append(p)
    for r in registry:
        for cand in r["candidates"]:
            ps = by_uci.get(cand) or [None]
            for p in ps:
                key = (cand, p["full_name"] if p else "")
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row_for(r["l1"], r["interaction"], cand, p, "등록부 §5"))
        if r["cls"] == "EXT" and not r["candidates"]:
            rows.append({"l1": r["l1"], "interaction": r["interaction"], "uci": "—", "dir": "—", "cls": "EXT",
                         "internal": "", "converter": "—", "imp": "", "tc": "", "status": "확장(외부 비공개)",
                         "source": "등록부 §5"})
    for p in std:
        for u in [p["uci_name"], *p["uci_also"]]:
            if u and (u, p["full_name"]) not in seen:
                seen.add((u, p["full_name"]))
                rows.append(row_for(p["l1"], "(등록부 표에 없음)", u, p, "proto"))
    for p in proto:
        if p["mapping"] == "EXT":
            rows.append({"l1": p["l1"], "interaction": "(proto EXT)", "uci": "—", "dir": "—", "cls": "EXT",
                         "internal": p["short"], "converter": "있음" if p["full_name"] in conv else "없음",
                         "imp": "", "tc": "", "status": "확장(외부 비공개)", "source": "proto"})
    ucis = {u for u in by_uci}
    summary = {
        "xsd_top": len(xsd), "xsd_ma": sum(1 for x in xsd if x.startswith("MA_")),
        "mapped_uci": len(ucis), "mapped_uci_ma": sum(1 for u in ucis if u.startswith("MA_")),
        "send": len({r["uci"] for r in rows if r["dir"] == "송신"}),
        "recv": len({r["uci"] for r in rows if r["dir"] == "수신"}),
        "std": len(std), "ext": sum(1 for p in proto if p["mapping"] == "EXT"),
        "sim": sum(1 for p in proto if p["mapping"] == "SIM"),
        "status": dict(Counter(r["status"] for r in rows)),
        "inside": sorted(k for k, v in inside.items() if v),
    }
    return {"verdict": verdict(fails), "fail": fails, "info": info, "rows": rows, "summary": summary,
            "scope": {k: {**scope.get(k, {}), "inside_eff": v} for k, v in inside.items()}}


def _scope_why(sc: dict, inside: bool) -> str:
    if inside:
        return "계약 키 " + ", ".join(sc.get("named_keys", [])) + "로만 오감"
    if sc.get("swarm_ctx"):
        return "계약 " + sc["swarm_ctx"][0].lstrip("- ").strip()
    return "swarm/** 교환(LinkEnvelope)"


# ---------------------------------------------------------------------------------------------------------- C2


def judge_c2(rx: list[dict], sent: list[dict], negatives: list[dict]) -> dict:
    """rx: [{client, name, ok}], sent: [{tag, name, xsd_ok, pub, negative}], negatives: [{tag, on_bus, how}]"""
    fails: list[str] = []
    by = defaultdict(lambda: [0, 0])
    for r in rx:
        by[r["name"]][0] += 1
        by[r["name"]][1] += 0 if r["ok"] else 1
    for name, (n, bad) in sorted(by.items()):
        if bad:
            fails.append(f"수신 {name}: XSD 재검증 실패 {bad}/{n}")
    sent_by = defaultdict(lambda: [0, 0])
    for s in sent:
        if s.get("negative"):
            continue
        sent_by[s["name"]][0] += 1
        if not s.get("xsd_ok"):
            sent_by[s["name"]][1] += 1
            fails.append(f"송신 {s['tag'] or s['name']}: 외부가 보낸 정상 메시지가 XSD 재검증에 실패")
        if not str(s.get("pub", "")).startswith("+OK"):
            fails.append(f"송신 {s['tag'] or s['name']}: CAL Server가 정상 메시지를 받지 않음 ({s.get('pub')})")
    for n in negatives:
        if n["on_bus"]:
            fails.append(f"부정 입력 {n['tag']}: 버스로 나감 ({n.get('bus_key', '')})")
        elif not n.get("how"):
            fails.append(f"부정 입력 {n['tag']}: 거부 기록이 없다")
    if not rx:
        fails.append("외부 수신이 0건")
    return {"verdict": verdict(fails), "fail": fails,
            "rx": {k: {"n": v[0], "fail": v[1]} for k, v in sorted(by.items())},
            "sent": {k: {"n": v[0], "fail": v[1]} for k, v in sorted(sent_by.items())},
            "negatives": negatives}


# ---------------------------------------------------------------------------------------------------------- C3

TOL = {
    "pos_rad": 1e-9,          # 위경도 rad (deg→rad 변환은 배정밀도, 1e-9 rad ≈ 6 mm)
    "alt_m": 1e-6,
    "vel_mps": 1e-9,
    "att_rad": 1e-6,          # 오일러각 (도구가 회전행렬로 따로 계산한 값과의 차)
    "ts_spread_s": 0.5,       # (UCI Timestamp − 모의 시각) 의 실행 중 변동 폭
    "route_deg": 1e-9,        # 수신 RoutePlan 위경도 (rad→deg 왕복)
    "route_alt_m": 1e-9,
}

# DEC-090: 내부 상태 → 공개 XSD enum. TaskStatus는 RequirementExecutionStateEnum, FlightCommandStatus는
# CommandProcessingStateEnum(EXECUTING·COMPLETED가 ACCEPTED로 보인다)
STATE_MAP = {
    "TaskStatus": {"UNSPECIFIED": "EXECUTION_PENDING", "ACCEPTED": "EXECUTION_PENDING", "EXECUTING": "EXECUTING",
                   "COMPLETED": "COMPLETED", "REJECTED": "DROPPED", "FAILED": "FAILED", "CANCELLED": "CANCELED"},
    "FlightCommandStatus": {"UNSPECIFIED": "RECEIVED", "ACCEPTED": "ACCEPTED", "EXECUTING": "ACCEPTED",
                            "COMPLETED": "ACCEPTED", "REJECTED": "REJECTED", "FAILED": "REJECTED",
                            "CANCELLED": "CANCELED"},
}


def wrap_pi(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def euler_from_quat_matrix(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
    """NED→FRD 회전(쿼터니언)의 ZYX 오일러각 (yaw, pitch, roll). 회전행렬 원소로 따로 계산한다(Gateway 식과 다른 경로)"""
    n = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n
    r00 = 1 - 2 * (y * y + z * z)
    r10 = 2 * (x * y + w * z)
    r20 = 2 * (x * z - w * y)
    r21 = 2 * (y * z + w * x)
    r22 = 1 - 2 * (x * x + y * y)
    yaw = math.atan2(r10, r00)
    pitch = -math.asin(max(-1.0, min(1.0, r20)))
    roll = math.atan2(r21, r22)
    return yaw, pitch, roll


def compare_position(bus: dict, uci: dict) -> dict:
    """bus: {lat_deg, lon_deg, alt_m, vel:(n,e,d)|None, q:(w,x,y,z)|None}, uci: {lat, lon, alt, ref, vel, ypr}(rad)"""
    out = {"lat": abs(math.radians(bus["lat_deg"]) - uci["lat"]),
           "lon": abs(wrap_pi(math.radians(bus["lon_deg"]) - uci["lon"])),
           "alt": abs(bus["alt_m"] - uci["alt"]), "alt_ref": uci.get("ref") == "MSL"}
    if bus.get("vel") is not None:
        if uci.get("vel") is None:
            out["vel"] = math.inf
        else:
            out["vel"] = max(abs(a - b) for a, b in zip(bus["vel"], uci["vel"]))
    if bus.get("q") is not None and any(bus["q"]):
        if uci.get("ypr") is None:
            out["att"] = math.inf
        else:
            ref = euler_from_quat_matrix(*bus["q"])
            out["att"] = max(abs(wrap_pi(a - b)) for a, b in zip(ref, uci["ypr"]))
    return out


def judge_epoch(epoch: dict | None, ts_offsets: list[float]) -> dict:
    """DEC-098 (a) UCI Timestamp − 모의 시각 = sim/ctrl/scenario의 epoch_utc_us (허용 오차 TOL ts_spread_s),
    (b) Gateway epoch_changed 카운터 0. 관측한 epoch가 둘 이상이면 마지막 값과 비교하고 정보로 적는다"""
    out: dict = {"checked": epoch is not None, "fail": [], "info": []}
    if epoch is None:
        out["info"].append("시각 기준(DEC-098) 확인 안 함: 원자료에 sim/ctrl/scenario epoch 기록이 없다(33차 이전)")
        return out
    vals = [e["epoch_utc_us"] for e in epoch.get("scenario", [])]
    nz = [v for v in vals if v > 0]
    out["scenario_epochs"] = vals
    out["log"] = epoch.get("log", [])
    if not vals:
        out["fail"].append("sim/ctrl/scenario 관측 0건: 시각 기준 epoch를 확인하지 못함")
    elif not nz:
        out["fail"].append("sim/ctrl/scenario의 run.epoch_utc_us가 0이다(Core가 적재 때 채우지 않음, DEC-098)")
    else:
        if len(set(nz)) > 1:
            out["info"].append(f"관측한 epoch_utc_us 값 {len(set(nz))}개: {sorted(set(nz))}. 마지막 값과 비교한다")
        e_s = nz[-1] * 1e-6
        out["epoch_utc_us"] = nz[-1]
        if ts_offsets:
            dev = [o - e_s for o in ts_offsets]
            out["dev_s"] = {"n": len(dev), "min": min(dev), "max": max(dev), "abs_max": max(abs(d) for d in dev)}
            if out["dev_s"]["abs_max"] > TOL["ts_spread_s"]:
                out["fail"].append(f"UCI Timestamp − 모의 시각이 시나리오 epoch_utc_us와 다름: 최대 차 "
                                   f"{out['dev_s']['abs_max']:.3f} s > {TOL['ts_spread_s']} s (DEC-098)")
    gw = epoch.get("gw")
    out["gw"] = gw
    if gw is None:
        out["fail"].append("Gateway 카운터 기록 없음: epoch_changed를 확인하지 못함")
    elif gw.get("epoch_changed", 0):
        out["fail"].append(f"Gateway epoch_changed {gw['epoch_changed']}: 실행 중 UCI 시각 기준이 바뀌었다(DEC-098)")
    return out


def judge_c3(pos_pairs: list[dict], ts_offsets: list[float], ids: dict, states: list[dict], routes: list[dict],
             unpaired: dict | None = None, epoch: dict | None = None) -> dict:
    """pos_pairs: compare_position 결과에 {who, topic} 추가. ts_offsets: UCI Timestamp − 모의 시각(s)
    epoch: analyze.c3_epoch 결과(DEC-098). None이면 시각 기준 확인을 건너뛰고 정보로 적는다(33차 이전 원자료)
    ids: {kind: [(label, uuid), ...]}. states: [{msg, internal, external}]. routes: [{route, sent:[(lat,lon,alt)], bus:[...]}]"""
    fails: list[str] = []
    worst = {"lat": 0.0, "lon": 0.0, "alt": 0.0, "vel": 0.0, "att": 0.0}
    nref = 0
    for p in pos_pairs:
        for k in worst:
            if k in p:
                worst[k] = max(worst[k], p[k])
        if not p["alt_ref"]:
            nref += 1
    if not pos_pairs:
        fails.append("위치 대조 쌍이 0건")
    if worst["lat"] > TOL["pos_rad"] or worst["lon"] > TOL["pos_rad"]:
        fails.append(f"위치 위경도 최대 차 {max(worst['lat'], worst['lon']):.3g} rad > {TOL['pos_rad']}")
    if worst["alt"] > TOL["alt_m"]:
        fails.append(f"고도 최대 차 {worst['alt']:.3g} m > {TOL['alt_m']}")
    if nref:
        fails.append(f"고도 기준이 MSL이 아닌 보고 {nref}건")
    if worst["vel"] > TOL["vel_mps"]:
        fails.append(f"NED 속도 최대 차 {worst['vel']:.3g} m/s > {TOL['vel_mps']}")
    if worst["att"] > TOL["att_rad"]:
        fails.append(f"자세(NED→FRD 오일러) 최대 차 {worst['att']:.3g} rad > {TOL['att_rad']}")
    ts = {}
    if ts_offsets:
        ts = {"n": len(ts_offsets), "min": min(ts_offsets), "max": max(ts_offsets),
              "spread": max(ts_offsets) - min(ts_offsets)}
        if ts["spread"] > TOL["ts_spread_s"]:
            fails.append(f"UCI Timestamp가 모의 시각을 따르지 않음: (Timestamp − 모의 시각) 변동 {ts['spread']:.3f} s "
                         f"> {TOL['ts_spread_s']} s")
    else:
        fails.append("Timestamp 대조 0건")
    ep = judge_epoch(epoch, ts_offsets)
    fails += ep["fail"]
    id_res = {}
    for kind, pairs in ids.items():
        by_label, by_uuid = defaultdict(set), defaultdict(set)
        for label, u in pairs:
            by_label[label].add(u)
            by_uuid[u].add(label)
        multi_u = {k: sorted(v) for k, v in by_label.items() if len(v) > 1}
        multi_l = {k: sorted(v) for k, v in by_uuid.items() if len(v) > 1}
        empty = sum(1 for label, _ in pairs if not label)
        id_res[kind] = {"labels": len(by_label), "refs": len(pairs), "label_multi_uuid": multi_u,
                        "uuid_multi_label": multi_l, "empty_label": empty}
        if multi_u:
            fails.append(f"{kind}: 같은 내부 ID에 UUID 여러 개 {list(multi_u)[:3]}")
        if multi_l:
            fails.append(f"{kind}: 같은 UUID에 DescriptiveLabel 여러 개 {list(multi_l)[:3]}")
        if empty:
            fails.append(f"{kind}: DescriptiveLabel 없는 참조 {empty}건")
    st_bad = Counter()
    st_n = Counter()
    for s in states:
        st_n[s["msg"]] += 1
        exp = STATE_MAP.get(s["msg"], {}).get(s["internal"])
        if exp != s["external"]:
            st_bad[(s["msg"], s["internal"], s["external"], exp)] += 1
    for (m, i, e, x), n in st_bad.items():
        fails.append(f"상태값 {m} {i} → {e} (DEC-090 표: {x}) {n}건")
    if not states:
        fails.append("상태값 대조 0건")
    r_res = []
    for r in routes:
        ok_order = len(r["sent"]) == len(r["bus"])
        dmax = amax = 0.0
        if ok_order:
            for a, b in zip(r["sent"], r["bus"]):
                dmax = max(dmax, abs(a[0] - b[0]), abs(a[1] - b[1]))
                amax = max(amax, abs(a[2] - b[2]))
        r_res.append({"route": r["route"], "where": r.get("where", ""), "n_sent": len(r["sent"]),
                      "n_bus": len(r["bus"]), "deg_max": dmax, "alt_max": amax})
        if not ok_order:
            fails.append(f"수신 경로 {r['route']}({r.get('where', '')}): 항로점 수 {len(r['sent'])} → {len(r['bus'])}")
        elif dmax > TOL["route_deg"] or amax > TOL["route_alt_m"]:
            fails.append(f"수신 경로 {r['route']}({r.get('where', '')}): 좌표·순서 차 {dmax:.3g}°, 고도 {amax:.3g} m")
    if not routes:
        fails.append("수신 경로 대조 0건")
    return {"verdict": verdict(fails), "fail": fails, "n_pos": len(pos_pairs), "worst": worst, "ts": ts, "epoch": ep, "info": ep["info"],
            "ids": id_res, "states": {"n": dict(st_n), "bad": [list(k) + [v] for k, v in st_bad.items()]},
            "routes": r_res, "unpaired": unpaired or {}, "tol": TOL}


# ---------------------------------------------------------------------------------------------------------- C4


def _chunks(k: str) -> list[str]:
    return [c for c in k.strip("/").split("/") if c != ""]


def keyexpr_includes(pattern: str, expr: str) -> bool:
    """expr(키 또는 키 표현식)가 나타내는 키 집합이 pattern 안에 드는가. '*'는 한 마디, '**'는 0개 이상 마디"""
    p, e = _chunks(pattern), _chunks(expr)

    def go(i: int, j: int) -> bool:
        if i == len(p):
            return j == len(e)
        if p[i] == "**":
            return any(go(i + 1, k) for k in range(j, len(e) + 1))
        if j == len(e):
            return False
        if e[j] == "**":
            return False                   # 한 마디 이상 임의 길이는 '**' 패턴만 덮는다
        if p[i] == "*" or p[i] == e[j]:
            return go(i + 1, j + 1)
        if "*" in p[i] and "*" not in e[j]:
            return re.fullmatch(re.escape(p[i]).replace(r"\*", "[^/]*"), e[j]) is not None and go(i + 1, j + 1)
        return False
    return go(0, 0)


def parse_contract_keys(md: str) -> list[dict]:
    """계약 §3.2 키 목록 표 → [{key, pattern, msg, pub, sub}]. <x> 자리표시는 '*'로 바꾼다"""
    sec = md.split("### 3.2 키 목록", 1)[1].split("### 3.3", 1)[0]
    rows = []
    for ln in sec.splitlines():
        if not ln.startswith("| `"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        key = cells[0].strip("`")
        rows.append({"key": key, "pattern": re.sub(r"<[^>]+>", "*", key), "msg": cells[1], "pub": cells[2],
                     "sub": cells[3]})
    return rows


AGENT_WORDS = ("Agent 런타임", "모든 참여자의 런타임", "송신 엔티티 런타임", "수신 엔티티 런타임", "해당 기체 런타임")


def agent_allowed(rows: list[dict]) -> dict:
    """§3.2에서 Agent가 발행·구독할 수 있는 키. '참여자'(lockstep 장벽 FrameDone 발행)도 Agent에 해당한다"""
    pub, sub = [], []
    for r in rows:
        if any(w in r["pub"] for w in AGENT_WORDS) or r["pub"] == "참여자" or "⇄ 해당 기체 런타임" in r["pub"]:
            pub.append({"pattern": r["pattern"], "src": f"§3.2 `{r['key']}` 발행: {r['pub']}"})
        if any(w in r["sub"] for w in AGENT_WORDS) or "해당 기체 런타임" in r["pub"]:
            sub.append({"pattern": r["pattern"], "src": f"§3.2 `{r['key']}` 구독: {r['sub']}"})
    return {"pub": pub, "sub": sub}


# §3.2 표에 Agent가 구독자로 적혀 있지 않지만 §3.3 본문이 Agent 구독을 정한 키 (보고서에 근거와 함께 싣는다)
SUPPLEMENT_SUB = [
    {"pattern": "sim/clock/done/*", "src": "§3.3 lockstep 수신 결정성(DEC-040)·송신 개수 장벽(DEC-044): Agent는 Datalink의 FrameDone을 받는다"},
    {"pattern": "sim/ctrl/cmd", "src": "§3.3 기체별 매개변수(DEC-035): Agent 런타임은 sim/ctrl/cmd를 구독해 set_params를 처리한다"},
    {"pattern": "swarm/*/rx/**", "src": "§3.3 송신 개수 장벽(DEC-044): Agent는 자기 기체의 swarm/<e>/rx/** 개수를 확인한다 "
                                        "(§3.2 표의 키 형식은 swarm/<dst>/rx/<iface>/<msg>)"},
]
FORBIDDEN_PREFIX = ("truth",)
ENTITY_SCOPED = (("swarm", 1), ("onboard", 1))   # (첫 마디, 엔티티 마디 위치)
FORBIDDEN_IMPORTS = ("zenoh", "swarm_api.bus", "swarm_api.keys", "swarm.v1.truth_pb2", "swarm.v1.sim_pb2",
                     "swarm.v1.link_pb2", "swarm.v1.fa_pb2", "swarm_core", "swarm_bus", "swarm_bridge", "swarm_gateway",
                     "swarm_datalink", "swarm_logger", "swarm_agent.runtime", "swarm_agent.cli", "swarm_agent.vehicle",
                     "swarm_agent.ports")
FORBIDDEN_NAMES = ("open_bus", "Bus", "BusConfig", "Sample")   # swarm_api에서 가져오면 버스 직접 접근
PLUGIN_API = ("swarm_api", "swarm.v1")                          # 계약 §5 플러그인 API와 L1 메시지
L1_OK = ("C2", "VI", "MS", "MP", "MD", "P2P")


def judge_c4(subs: list[str], puts: list[str], allowed: dict, hosted: list[str], imports: list[dict],
             port_msgs: list[dict], proto: dict[str, dict], mcap_topics: list[str] | None = None,
             rx_keys: dict[str, int] | None = None) -> dict:
    """subs: Agent가 연 구독 키 표현식, puts: 발행한 키, imports: [{file, line, module, names}],
    port_msgs: [{port, dir, msg, n}], proto: full_name → {mapping, l1}, rx_keys: 구독 콜백에 실제 들어온 키 → 수.
    엔티티 자리에 이름을 쓴 구독·발행이 맡지 않은 엔티티면 실패. 엔티티 자리가 '*'인 구독은 §3.2 패턴(<e>) 안이라 통과로 두고,
    실제로 받은 맡지 않은 엔티티 키 수를 정보로 적는다(런타임이 받는 범위이고 MA에 가는지는 포트 기록으로 본다)"""
    fails: list[str] = []
    info: list[str] = []
    sub_pat = [a["pattern"] for a in allowed["sub"]] + [a["pattern"] for a in SUPPLEMENT_SUB]
    pub_pat = [a["pattern"] for a in allowed["pub"]]
    hosted_set = set(hosted)
    sub_rows, put_rows = [], []
    for k in sorted(set(subs)):
        ok = any(keyexpr_includes(p, k) for p in sub_pat)
        why = ""
        if _chunks(k)[0] in FORBIDDEN_PREFIX or k.startswith("**"):
            ok, why = False, "truth/** 또는 전체 구독"
        ok, why = _scope(k, hosted_set, ok, why)
        sub_rows.append({"key": k, "ok": ok, "why": why})
        if not ok:
            fails.append(f"Agent 구독 {k}: 허용 키 밖 {why}".strip())
    for k in sorted(set(puts)):
        ok = any(keyexpr_includes(p, k) for p in pub_pat)
        why = ""
        if _chunks(k)[0] in FORBIDDEN_PREFIX:
            ok, why = False, "truth/**"
        ok, why = _scope(k, hosted_set, ok, why)
        put_rows.append({"key": k, "ok": ok, "why": why})
        if not ok:
            fails.append(f"Agent 발행 {k}: 허용 키 밖 {why}".strip())
    if not subs:
        fails.append("Agent 구독 기록이 없다(래퍼 실패)")
    foreign_rx: Counter = Counter()
    for k, n in (rx_keys or {}).items():
        c = _chunks(k)
        if c[0] in FORBIDDEN_PREFIX:
            fails.append(f"Agent가 truth 키 {k}를 받음 ({n}건)")
        for first, pos in ENTITY_SCOPED:
            if c[0] == first and len(c) > pos and hosted_set and c[pos] not in hosted_set:
                foreign_rx[f"{first}/{c[pos]}/{c[pos + 1] if len(c) > pos + 1 else ''}"] += n
    if foreign_rx:
        info.append("엔티티 와일드카드 구독으로 맡지 않은 엔티티 키를 받음: "
                    + ", ".join(f"{k}… {v}건" for k, v in foreign_rx.most_common(6)))
    mcap = {}
    if mcap_topics is not None:
        tops = set(mcap_topics)
        missing = sorted(k for k in set(puts) if k not in tops)
        mcap = {"channels": len(tops), "agent_put_missing_in_mcap": missing[:20],
                "truth_channels": sorted(t for t in tops if t.startswith("truth/"))}
        if missing:
            info.append(f"Agent 발행 키 중 MCAP에 없는 채널 {len(missing)}개")
    imp_rows = []
    for im in imports:
        mod = im["module"]
        bad = [f for f in FORBIDDEN_IMPORTS if mod == f or mod.startswith(f + ".")]
        bad_names = [n for n in im.get("names", []) if mod.split(".")[0] == "swarm_api" and n in FORBIDDEN_NAMES]
        if mod == "swarm.v1" and any(n in ("truth_pb2", "sim_pb2", "link_pb2", "fa_pb2") for n in im.get("names", [])):
            bad_names += [n for n in im["names"] if n in ("truth_pb2", "sim_pb2", "link_pb2", "fa_pb2")]
        api = mod.split(".")[0] in ("swarm_api",) or mod.startswith("swarm.v1")
        kind = "금지" if (bad or bad_names) else ("API" if api else ("런타임 내부" if mod.startswith("swarm_agent")
                                                                     else "일반"))
        imp_rows.append({**im, "kind": kind})
        if bad or bad_names:
            fails.append(f"{im['file']}:{im['line']} import {mod} {bad_names or ''}: 버스·truth·Core 모듈".strip())
        elif kind == "런타임 내부":
            info.append(f"{im['file']}:{im['line']} {mod}: 플러그인 API(§5) 밖의 Agent 런타임 모듈")
    port_rows = []
    for pm in port_msgs:
        p = proto.get(pm["msg"])
        if pm["msg"] == "md.record":
            tag = ("MD", "—")
        elif p is None:
            tag = ("?", "?")
        else:
            tag = (p["l1"], p["mapping"])
        ok = tag[0] in L1_OK and tag[1] != "SIM" or tag[1] == "EXT"
        if tag[1] == "SIM":
            ok = False
        port_rows.append({**pm, "l1": tag[0], "mapping": tag[1], "ok": ok})
        if not ok:
            fails.append(f"MA 포트 {pm['port']} {pm['dir']} {pm['msg']}: L1 {tag[0]} / {tag[1]}")
    if not port_msgs:
        fails.append("MA 포트 기록이 없다(래퍼 실패)")
    return {"verdict": verdict(fails), "fail": fails, "info": info, "subs": sub_rows, "puts": put_rows,
            "allowed": {"pub": allowed["pub"], "sub": allowed["sub"] + SUPPLEMENT_SUB}, "imports": imp_rows,
            "ports": port_rows, "mcap": mcap, "foreign_rx": dict(foreign_rx)}


def _scope(k: str, hosted: set[str], ok: bool, why: str) -> tuple[bool, str]:
    c = _chunks(k)
    for first, pos in ENTITY_SCOPED:
        if c and c[0] == first and len(c) > pos and hosted:
            e = c[pos]
            if e not in hosted and e not in ("*", "**"):
                return False, f"맡지 않은 엔티티 {e}"
    return ok, why


# ---------------------------------------------------------------------------------------------------------- C5

TERMINAL_INT = {"COMPLETED", "CANCELLED", "FAILED", "REJECTED"}
# 내부 TaskStatus·FlightCommandStatus (CommandState). 키 None = 첫 보고
TRANS_INT = {
    None: {"ACCEPTED", "EXECUTING", "REJECTED", "FAILED"},
    "ACCEPTED": {"EXECUTING", "REJECTED", "CANCELLED", "FAILED"},
    "EXECUTING": {"COMPLETED", "CANCELLED", "FAILED"},
}
# 내부 FlightCommandStatus: FA는 수락하면 곧바로 끝낼 수 있다(goto 도착 COMPLETED).
# 첫 보고 CANCELLED는 접수 전에 대체된 명령이다(DEC-097, O-47)
TRANS_FCS = {
    None: {"ACCEPTED", "EXECUTING", "REJECTED", "CANCELLED"},
    "ACCEPTED": {"EXECUTING", "COMPLETED", "REJECTED", "CANCELLED", "FAILED"},
    "EXECUTING": {"COMPLETED", "CANCELLED", "FAILED"},
}
TERMINAL_EXT_TASK = {"COMPLETED", "CANCELED", "FAILED", "DROPPED"}
# 외부 MA_TaskStatus ExecutionState (RequirementExecutionStateEnum, DEC-090)
TRANS_EXT_TASK = {
    None: {"EXECUTION_PENDING", "EXECUTING", "DROPPED", "FAILED"},
    "EXECUTION_PENDING": {"EXECUTING", "DROPPED", "CANCELED", "FAILED"},
    "EXECUTING": {"COMPLETED", "CANCELED", "FAILED"},
}
# 외부 MA_*CommandStatus CommandProcessingState: 공개 UCI Command-2 상태 기계(DEC-097, docs/44 C5 "명령 상태").
# ACCEPTED·REJECTED·CANCELED는 끝 상태다. 첫 보고는 RECEIVED 없이 끝 상태여도 된다
TERMINAL_EXT_CMD = {"ACCEPTED", "REJECTED", "CANCELED"}
TRANS_EXT_CMD = {
    None: {"RECEIVED", "ACCEPTED", "REJECTED", "CANCELED"},
    "RECEIVED": {"ACCEPTED", "REJECTED", "CANCELED"},
}
# 표 이름 → (전이 표, 끝 상태, 끝 상태 뒤 같은 상태 반복도 실패인가)
# 외부 명령 상태는 DEC-097 "끝 상태 뒤 보고가 있으면 실패": 같은 CommandID에 끝 상태를 보낸 뒤에는 같은 상태도 다시 보내지 않는다
TABLES = {"TaskStatus(내부)": (TRANS_INT, TERMINAL_INT, False),
          "FlightCommandStatus(내부)": (TRANS_FCS, TERMINAL_INT, False),
          "MA_TaskStatus(외부)": (TRANS_EXT_TASK, TERMINAL_EXT_TASK, False),
          "MA_FlightCommandStatus(외부)": (TRANS_EXT_CMD, TERMINAL_EXT_CMD, True)}


def check_sequence(states: list[str], table: dict, terminal: set[str], strict_terminal: bool = False) -> list[str]:
    """같은 상태 반복은 허용(변화 보고 재송신). 끝 상태 뒤의 다른 상태와 표 밖 전이를 돌려준다.
    strict_terminal이면 끝 상태 뒤의 같은 상태 반복도 실패다(DEC-097 외부 명령 상태)"""
    bad, prev = [], None
    for s in states:
        if s == prev:
            if strict_terminal and prev in terminal:
                bad.append(f"{prev}→{s}(끝 상태 뒤 반복)")
            continue
        if prev in terminal:
            bad.append(f"{prev}→{s}(끝 상태 뒤)")
        elif s not in table.get(prev, set()):
            bad.append(f"{prev or '시작'}→{s}")
        prev = s
    return bad


def judge_c5(seqs: dict[str, dict[str, list[str]]], approvals: list[dict], commands: list[dict]) -> dict:
    """seqs: 표 이름 → {대상: [상태...]} (대상은 '기체/작업' 또는 '기체/명령'. 새 명령이 오면 분절은 호출 쪽이 나눈다)
    approvals: [{entity, task, need, response: approved|rejected|None, t_resp, t_exec}] (시각은 모의 s, None 가능)
    commands: [{entity, task, src, status_seen: bool}] 링크 정상 구간의 외부 명령"""
    fails: list[str] = []
    res = {}
    for name, per in seqs.items():
        table, term, strict = TABLES[name]
        bad_all = {}
        for tgt, st in per.items():
            bad = check_sequence(st, table, term, strict)
            if bad:
                bad_all[tgt] = bad
                fails.append(f"{name} {tgt}: 허용 전이 밖 {', '.join(bad)} (순서 {' → '.join(st)})")
        res[name] = {"targets": len(per), "bad": bad_all}
    ap_rows = []
    for a in approvals:
        row = dict(a)
        if a["need"]:
            if a["t_exec"] is not None and (a["response"] != "approved" or a["t_resp"] is None
                                           or a["t_exec"] < a["t_resp"]):
                row["ok"] = False
                fails.append(f"승인 필요 작업 {a['entity']}/{a['task']}: 승인 응답({a['response']}, {a['t_resp']}) "
                             f"전에 수행 {a['t_exec']}")
            else:
                row["ok"] = True
        ap_rows.append(row)
    miss = [c for c in commands if not c["status_seen"]]
    for c in miss:
        fails.append(f"명령 {c['src']} {c['entity']}/{c['task']}: 상태 보고 없음")
    if not commands:
        fails.append("외부 명령 0건")
    return {"verdict": verdict(fails), "fail": fails, "seq": res, "approvals": ap_rows,
            "commands": {"n": len(commands), "missing": len(miss)},
            "tables": {k: {"transitions": {str(a): sorted(b) for a, b in t.items()}, "terminal": sorted(term),
                           "strict_terminal": strict}
                       for k, (t, term, strict) in TABLES.items()}}


# ---------------------------------------------------------------------------------------------------------- C6


def parse_declared(yaml_text: str) -> dict[str, dict[str, set[str]]]:
    """lacal_server.yaml의 services.<svc>.declared.pub·sub (흐름 목록 [a@t, ...] 형식, 여러 줄 가능)"""
    out: dict[str, dict[str, set[str]]] = {}
    svc = None
    in_services = False
    buf, field = "", None
    for raw in yaml_text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("services:"):
            in_services = True
            continue
        if not in_services:
            continue
        ind = len(line) - len(line.lstrip())
        s = line.strip()
        if field is not None:
            buf += s
            if "]" in s:
                out[svc][field] |= {x.strip() for x in buf.split("[", 1)[1].split("]", 1)[0].split(",") if x.strip()}
                field, buf = None, ""
            continue
        if ind == 2 and s.endswith(":"):
            svc = s[:-1]
            out[svc] = {"pub": set(), "sub": set()}
        elif s.startswith(("pub:", "sub:")) and svc:
            f = s[:3]
            if "]" in s:
                out[svc][f] |= {x.strip() for x in s.split("[", 1)[1].split("]", 1)[0].split(",") if x.strip()}
            else:
                field, buf = f, s
    return out


def graph_flows(graph: dict) -> dict[str, dict[str, Counter]]:
    """/graph 스냅샷 → 서비스 라벨 → {pub: Counter(name@topic → msg_count), sub: Counter}"""
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    out: dict[str, dict[str, Counter]] = defaultdict(lambda: {"pub": Counter(), "sub": Counter()})
    for e in graph.get("edges", []):
        if e["kind"] == "pub":
            svc, top = nodes.get(e["source"]), nodes.get(e["target"])
        else:
            top, svc = nodes.get(e["source"]), nodes.get(e["target"])
        if not svc or not top or svc.get("kind") != "service":
            continue
        out[svc["label"]][e["kind"]][f"{top['message_name']}@{top['topic']}"] += e.get("msg_count", 0)
    return out


def judge_c6(declared: dict, flows: dict, tap: Counter, ext_rx: Counter, inbound_bus: dict[str, int],
             services: tuple[str, ...] = ("swarm_gateway", "external_c2")) -> dict:
    """declared: 설정 파일. flows: graph_flows. tap: (name@topic) → /tap 건수(Gateway 발신).
    ext_rx: (name@topic) → 시작부터 붙어 있던 외부 클라이언트 수신 수. inbound_bus: 외부 송신 UCI → 버스 tx 수"""
    fails: list[str] = []
    rows = []
    for svc in services:
        d = declared.get(svc, {"pub": set(), "sub": set()})
        f = flows.get(svc, {"pub": Counter(), "sub": Counter()})
        for kind in ("pub", "sub"):
            obs = {k for k, v in f[kind].items() if kind == "sub" or v > 0}
            for k in sorted(d[kind] | obs):
                st = "일치" if k in d[kind] and k in obs else ("선언만" if k in d[kind] else "선언 밖")
                rows.append({"service": svc, "kind": kind, "flow": k, "count": f[kind].get(k, 0), "state": st})
                if st == "선언만":
                    fails.append(f"{svc} {kind} {k}: 선언했지만 교환되지 않음")
                elif st == "선언 밖":
                    fails.append(f"{svc} {kind} {k}: 선언 밖 교환 ({f[kind].get(k, 0)}건)")
        if svc not in flows:
            fails.append(f"{svc}: CAL Server 그래프에 서비스가 없다")
    tap_rows = []
    for k in sorted(set(tap) | set(ext_rx)):
        a, b = tap.get(k, 0), ext_rx.get(k, 0)
        tap_rows.append({"flow": k, "tap": a, "ext": b, "ok": a == b})
        if a != b:
            fails.append(f"/tap {k} {a}건 ≠ 외부 수신 {b}건")
    for name, n in sorted(inbound_bus.items()):
        if n <= 0:
            fails.append(f"외부 송신 {name}: 버스에 나가지 않음")
    if not tap:
        fails.append("/tap 기록 0건")
    return {"verdict": verdict(fails), "fail": fails, "declared": rows, "tap": tap_rows, "inbound_bus": inbound_bus}


# ---------------------------------------------------------------------------------------------------------- C7


def strip_numbers(text: str) -> str:
    """반복 실행 비교용: 문구의 수치(건수·시간 차 등)를 #으로 바꾼다. 엔티티·작업 이름 안의 번호(uav-007)는 둔다"""
    return re.sub(r"(?<![\w-])\d+(?:\.\d+)?(?:e[-+]?\d+)?", "#", text)


APPLICABLE = ("해당", "부분")


def check_applicability(app: dict, files: set[str], decs: set[str]) -> dict:
    """docs/46 적용성 표(DEC-093): 해당·부분 행 근거의 파일 경로·DEC ID가 저장소에 있는지, §3 요약 건수가 §4 상세와 맞는지.

    app: static.amsgra_applicability 결과. files: 저장소 파일 경로(posix). decs: 등록부의 DEC ID.
    경로에 '/'가 없으면 같은 이름의 파일이 어디든 있으면 있다고 본다.
    """
    import static  # noqa: PLC0415 (판정 함수는 순수 함수로 두고 근거 추출만 빌린다)
    base = {f.rsplit("/", 1)[-1] for f in files}
    fails, info, rows = [], [], []
    for r in app["rows"]:
        if r["verdict"] not in APPLICABLE:
            continue
        refs = static.basis_refs(r["basis"])
        miss_p = [p for p in refs["paths"] if not (p in files or ("/" not in p and p in base))]
        miss_d = [d for d in refs["decs"] if d not in decs]
        rows.append({"id": r["id"], "verdict": r["verdict"], "paths": refs["paths"], "decs": refs["decs"],
                     "missing": miss_p + miss_d})
        for x in miss_p:
            fails.append(f"적용성 {r['id']}({r['verdict']}): 근거 파일 {x}이 저장소에 없다")
        for x in miss_d:
            fails.append(f"적용성 {r['id']}({r['verdict']}): 근거 {x}가 등록부에 없다")
    # §3 요약의 '계' 행과 §4 상세 건수 대조 (어긋나면 정보)
    cnt = {"해당": 0, "부분": 0, "해당없음": 0}
    for r in app["rows"]:
        if r["verdict"] in cnt:
            cnt[r["verdict"]] += 1
    head = app.get("head", [])
    tot = next((s for s in app["summary"] if s and s[0] == "계"), None)
    if tot and all(h in head for h in ("계", *cnt)):
        want = {h: tot[head.index(h)] for h in ("계", *cnt)}
        got = {"계": str(len(app["rows"])), **{k: str(v) for k, v in cnt.items()}}
        if want != got:
            info.append(f"적용성 §3 요약 계 {want}와 §4 상세 건수 {got}가 다르다")
    else:
        info.append("적용성 §3 요약에 '계' 행이나 판정 열이 없다")
    if not rows:
        fails.append("적용성 표에서 해당·부분 행을 찾지 못했다")
    return {"fail": fails, "info": info, "rows": rows, "counts": cnt, "n": len(app["rows"])}


def judge_c7(direct_open: list[str], entries: dict[str, bool], ms_services: dict[str, list[str]],
             loadout_rows: list[str], determinism: dict, applicability: dict | None = None) -> dict:
    """추적 항목이라 판정은 정보다. 다만 버스를 open_bus 밖에서 여는 코드는 실패로 적는다(ASB 개념 반영 확인).

    applicability: check_applicability 결과(DEC-093). 해당·부분 행 근거가 저장소에 없으면 실패다.
    """
    fails = [f"버스 직접 열기: {x}" for x in direct_open]
    fails += [f"진입점 {k}: open_bus를 쓰지 않음" for k, v in entries.items() if not v]
    info = []
    if applicability is not None:
        fails += applicability["fail"]
        info += applicability["info"]
    return {"verdict": FAIL if fails else INFO, "fail": fails, "info": info, "direct_open": direct_open,
            "entries": entries, "ms_services": ms_services, "loadout": loadout_rows, "determinism": determinism,
            "applicability": applicability}

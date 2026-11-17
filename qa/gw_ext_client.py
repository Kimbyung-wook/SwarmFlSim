"""QA 15차 외부 CAL Client (TC-QA-069~073). gateway/.venv의 python으로 띄운다.

- agra_lacal CAL Server에 `external_c2` 서비스로 접속해 Gateway 발행 13종과 MA_PositionReport(vi·p2p, DEC-072)를 구독한다.
- 받은 메시지마다 이 프로세스가 따로 적재한 공개 XSD(A-GRA 6.0a)로 다시 검증한다(서버 검증과 별개).
- 관리 포트 /tap으로 서버를 지나간 모든 메시지 이름·발신 서비스를 센다(구독하지 않은 이름도 보인다).
- <out>/cmd/NNN.json 명령 파일을 읽어 MA_TaskCommand를 PUB한다. Gateway 변환기를 쓰지 않고 JSON을 직접 만든다.
- <out>/ext.json에 수신 기록을 1 s마다 쓴다. <out>/STOP 파일이 생기면 끝낸다.
- 28차: `--approve <json>`({task_id: APPROVED|REJECTED})이면 MA_ApprovalRequest를 받는 즉시 그 작업의 요청에
  MA_ApprovalRequestStatus로 답한다(목록에 없는 작업은 답하지 않는다). DEC-088 4종의 내용 요약을 extra에 남긴다.
- 29차(표준 적합성 점검, DEC-092): ext.json을 쓸 때 다른 프로세스가 읽는 중이면 Windows에서 os.replace가
  PermissionError를 낸다(데모에서 클라이언트가 죽었다). 임시 파일을 프로세스별 이름으로 쓰고 replace를 0.05 s 간격으로
  재시도하며, 끝내 실패하면 그 회차는 건너뛰고 errors에 센다(클라이언트는 죽지 않는다).
  `--full <file>`이면 받은 메시지와 보낸 메시지 전체를 JSON 줄로 덧붙여 쓴다(교체 없이 append). /tap 기록에 토픽을 더했다(tap3).

gateway/.venv/Scripts/python.exe qa/gw_ext_client.py --url ws://127.0.0.1:18765 --admin 127.0.0.1:18766 --out <dir>
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "third_party" / "agra_lacal"))

from client.lacal_client import CalError, LaCalClient  # noqa: E402
from server.omsjson import OmsJsonCodec  # noqa: E402

XSD = ROOT / "third_party" / "agra_lacal" / "schema" / "A-GRA_MessageDefinitions_v6_0_a.xsd"

# gateway/README.md "교환 메시지" 표에서 옮겼다 (Gateway 코드에서 읽지 않는다)
EXPORTS = {
    "MA_NavigationReport": "vi", "SystemStatus": "vi", "MA_FlightCommandStatus": "vi", "MA_FlightCapability": "vi",
    "MA_TaskStatus": "c2", "MA_ApprovalRequest": "c2",
    "MA_PackagePartnerStatusReport": "p2p", "MA_LeaderUpdateRequest": "p2p", "MA_Entity": "p2p",
    "PO_Activity": "ms", "EA_Activity": "ms", "StrikeActivity": "ms", "StoreLoadoutConfiguration": "ms",
}
# DEC-072 uci_also: NavigationReport → swarm.vi, PeerStatus → swarm.p2p (16차)
EXTRA_SUBS = [("MA_PositionReport", "vi"), ("MA_PositionReport", "p2p")]
VI_DETAIL = ("SystemStatus", "MA_FlightCommandStatus", "MA_FlightCapability")


def ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ref(label: str) -> dict:
    return {"UUID": str(uuid.uuid4()), "DescriptiveLabel": label}


def task_command(system_uuid: str, task_id: str, entities: list[str], kind: str, cancel: bool = False) -> dict:
    cmds = [{"Capability": {
        "CommandID": ref(f"{task_id}/{e}"),
        "CommandState": "CANCEL" if cancel else "NEW",
        "CapabilityID": ref(f"{e}/{kind}"),
        "Ranking": {"Rank": {"Priority": 0, "PrecedenceWithinPriority": 0}},
        "TaskID": ref(task_id),
    }} for e in entities]
    return {"MA_TaskCommand": {
        "SecurityInformation": {"Classification": "U", "OwnerProducer": [{"GovernmentIdentifier": "USA"}]},
        "MessageHeader": {"SystemID": {"UUID": system_uuid}, "Timestamp": ts(), "SchemaVersion": "006.0.ASK",
                          "Mode": "SIMULATION"},
        "MessageData": {"Command": cmds},
    }}


def envelope(system_uuid: str, name: str, data: dict) -> dict:
    return {name: {
        "SecurityInformation": {"Classification": "U", "OwnerProducer": [{"GovernmentIdentifier": "USA"}]},
        "MessageHeader": {"SystemID": {"UUID": system_uuid}, "Timestamp": ts(), "SchemaVersion": "006.0.ASK",
                          "Mode": "SIMULATION"},
        "MessageData": data,
    }}


async def send_raw(cli, codec, ext, fname: str, c: dict) -> None:  # noqa: ANN001
    """XSD를 통과하지 않는 메시지도 그대로 보내 서버 응답을 기록한다"""
    msg = envelope(cli.system_uuid, c["raw"], c["data"])
    rec = {"file": fname, "tag": c.get("tag", ""), "name": c["raw"], "topic": c["topic"], "t": round(time.time(), 3)}
    try:
        codec.to_xml_bytes(msg)
        rec["xsd_ok"] = True
    except Exception as e:  # noqa: BLE001
        rec["xsd_ok"], rec["xsd_err"] = False, str(e)[:200]
    try:
        await cli.publish(c["topic"], msg)
        rec["pub"] = "+OK"
    except CalError as e:
        rec["pub"] = f"-ERR {e}"[:200]
    ext.cmds.append(rec)
    ext.write_full("tx", rec["t"], c["raw"], c["topic"], msg[c["raw"]], rec["xsd_ok"])


def label(obj) -> str:  # noqa: ANN001
    return obj.get("DescriptiveLabel", "") if isinstance(obj, dict) else ""


class Ext:
    def __init__(self, out: Path, codec: OmsJsonCodec) -> None:
        self.out, self.codec = out, codec
        self.t0 = time.monotonic()
        self.rx: list[list] = []          # [t, name, topic, xsd_ok, origin_system, extra]
        self.xsd_fail: list[str] = []
        self.tap: Counter = Counter()      # (name, origin service) 서버 통과 수
        self.tap3: Counter = Counter()     # 29차: (name, origin service, topic)
        self.full = None                   # 29차: --full 파일 (append)
        self.dump_retry_fail = 0
        self.tap_t: list[list] = []        # [t, name]
        self.cmds: list[dict] = []
        self.errors: list[str] = []
        self.on_approval = None            # 28차: 승인 요청 콜백
        self.sub_t: float | None = None    # 28차: 구독을 마친 시각 (늦은 구독자 판정)

    def on_msg(self, topic: str):  # noqa: ANN201
        def cb(name: str, obj: dict) -> None:
            t = round(time.time(), 3)
            ok = True
            try:
                self.codec.to_xml_bytes(obj)
            except Exception as e:  # noqa: BLE001
                ok = False
                if len(self.xsd_fail) < 20:
                    self.xsd_fail.append(f"{name}: {e}"[:300])
            body = obj.get(name, {})
            md = body.get("MessageData", {})
            extra = {}
            if name == "MA_TaskStatus":
                extra = {"task": label(md.get("TaskID")), "state": md.get("ExecutionState"),
                         "by": label((md.get("ExecutingSystemOrPackage") or {}).get("SystemID"))}
            elif name == "MA_PositionReport":
                ins = md.get("InertialState", {})
                pos = ins.get("Position", {})
                import math as _m
                extra = {"who": md.get("DisplayName", ""), "lat": _m.degrees(pos.get("Latitude", 0.0)),
                         "lon": _m.degrees(pos.get("Longitude", 0.0)), "alt": pos.get("Altitude"),
                         "ts": pos.get("Timestamp", ""), "vel": "DomainVelocity" in ins,
                         "ori": "Orientation" in ins}
            elif name == "MA_NavigationReport":
                extra = {"keys": sorted(md.keys())[:8], "who": label(md.get("SystemID"))}
            elif name in VI_DETAIL:
                extra = {"md": json.dumps(md, ensure_ascii=False, sort_keys=True)[:1500],
                         "who": label(md.get("SystemID")), "cmd": label(md.get("CommandID")),
                         "state": md.get("SystemState") or md.get("CommandProcessingState") or ""}
            elif name in ("PO_Activity", "EA_Activity", "StrikeActivity"):
                extra = {"keys": sorted(md.keys())[:6]}
            elif name == "MA_ApprovalRequest":     # 28차 (DEC-088)
                rq = md.get("RequestID") or {}
                item = ((md.get("ApprovalReferences") or {}).get("ApprovalItem") or {})
                tid = ((item.get("RequirementExecutionApproval") or {}).get("RequirementID") or {}).get("TaskID")
                extra = {"req": label(rq), "req_uuid": rq.get("UUID", ""), "task": label(tid),
                         "state": md.get("RequestState", "")}
                if self.on_approval is not None:
                    self.on_approval(extra)
            elif name in ("MA_LeaderUpdateRequest", "MA_Entity", "StoreLoadoutConfiguration"):
                extra = {"md": json.dumps(md, ensure_ascii=False, sort_keys=True)[:1500]}
            sysid = (body.get("MessageHeader") or {}).get("SystemID", {}).get("UUID", "")
            mode = (body.get("MessageHeader") or {}).get("Mode", "")
            self.rx.append([t, name, topic, ok, sysid, mode, extra])
            self.write_full("rx", t, name, topic, body, ok)
        return cb

    def write_full(self, kind: str, t: float, name: str, topic: str, body: dict, ok: bool) -> None:
        if self.full is not None:
            self.full.write(json.dumps({"k": kind, "t": t, "name": name, "topic": topic, "ok": ok, "body": body},
                                       ensure_ascii=False) + "\n")

    def dump(self) -> None:
        d = {"rx": self.rx, "xsd_fail": self.xsd_fail, "tap": [[k[0], k[1], v] for k, v in self.tap.items()],
             "tap3": [[*k, v] for k, v in self.tap3.items()],
             "tap_t": self.tap_t, "cmds": self.cmds, "errors": self.errors, "t_wall": time.monotonic() - self.t0,
             "sub_t": self.sub_t, "dump_retry_fail": self.dump_retry_fail}
        if self.full is not None:
            self.full.flush()
        tmp = self.out / f"ext.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        for _ in range(40):                 # 29차: 읽는 쪽이 파일을 잡고 있으면 PermissionError (Windows)
            try:
                os.replace(tmp, self.out / "ext.json")
                return
            except PermissionError:
                time.sleep(0.05)
        self.dump_retry_fail += 1


async def tap_loop(ext: Ext, admin: str) -> None:
    from websockets.asyncio.client import connect
    while True:
        try:
            async with connect(f"ws://{admin}/tap", max_size=16 * 2**20) as ws:
                async for raw in ws:
                    m = json.loads(raw)
                    if "message_name" not in m:
                        continue
                    ext.tap[(m["message_name"], m.get("origin", ""))] += 1
                    ext.tap3[(m["message_name"], m.get("origin", ""), m.get("topic", ""))] += 1
                    ext.tap_t.append([round(time.time(), 3), m["message_name"]])
        except Exception as e:  # noqa: BLE001
            ext.errors.append(f"tap: {e}"[:200])
            await asyncio.sleep(1.0)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:18765")
    ap.add_argument("--admin", default="127.0.0.1:18766")
    ap.add_argument("--service", default="external_c2")
    ap.add_argument("--out", required=True)
    ap.add_argument("--approve", default="", help="28차: {task_id: APPROVED|REJECTED} JSON")
    ap.add_argument("--full", default="", help="29차: 주고받은 메시지 전체를 JSON 줄로 덧붙일 파일")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "cmd").mkdir(parents=True, exist_ok=True)
    codec = OmsJsonCodec(XSD)
    ext = Ext(out, codec)
    if a.full:
        ext.full = open(a.full, "a", encoding="utf-8")  # noqa: SIM115
    cli = LaCalClient(a.url, a.service)
    for _ in range(60):
        try:
            await cli.connect()
            break
        except Exception:  # noqa: BLE001
            await asyncio.sleep(0.5)
    else:
        raise SystemExit("CAL Server 접속 실패")
    sub_err = {}
    for name, iface in EXPORTS.items():
        try:
            await cli.subscribe(name, f"swarm.{iface}", ext.on_msg(f"swarm.{iface}"))
        except CalError as e:
            sub_err[name] = str(e)
    for name, iface in EXTRA_SUBS:
        try:
            await cli.subscribe(name, f"swarm.{iface}", ext.on_msg(f"swarm.{iface}"))
        except CalError as e:
            sub_err[f"{name}@{iface}"] = str(e)
    ext.errors += [f"sub {k}: {v}" for k, v in sub_err.items()]
    ext.sub_t = round(time.time(), 3)
    rules = json.loads(a.approve) if a.approve else {}
    pending: list[dict] = []
    if rules:
        ext.on_approval = pending.append
    asyncio.create_task(tap_loop(ext, a.admin))
    print(f"ext ready system={cli.system_uuid} subs={len(EXPORTS) + len(EXTRA_SUBS) - len(sub_err)}", flush=True)
    (out / "ext.ready").write_text("ok", encoding="utf-8")
    done: set[str] = set()
    last = 0.0
    while not (out / "STOP").exists():
        while pending:                      # 28차: 승인 응답
            q = pending.pop(0)
            state = rules.get(q["task"])
            if state is None:
                continue
            c = {"raw": "MA_ApprovalRequestStatus", "topic": "swarm.c2", "tag": f"approve {q['task']} {state}",
                 "data": {"RequestID": {"UUID": q["req_uuid"], "DescriptiveLabel": q["req"]},
                          "RequestProcessingState": "COMPLETED", "ApprovalRequestProcessingState": state}}
            await send_raw(cli, codec, ext, f"approve-{q['req']}", c)
            print(f"approve {q['req']} {q['task']} -> {state} {ext.cmds[-1].get('pub')}", flush=True)
        for f in sorted((out / "cmd").glob("*.json")):
            if f.name in done:
                continue
            done.add(f.name)
            c = json.loads(f.read_text(encoding="utf-8"))
            if "raw" in c:          # 18차: 임의 UCI 메시지 (MessageData를 그대로 싣는다)
                await send_raw(cli, codec, ext, f.name, c)
                continue
            msg = task_command(cli.system_uuid, c["task_id"], c["entities"], c.get("kind", "hold"),
                               c.get("cancel", False))
            rec = {**c, "t": round(time.time(), 3), "file": f.name}
            try:
                codec.to_xml_bytes(msg)
                rec["xsd_ok"] = True
            except Exception as e:  # noqa: BLE001
                rec["xsd_ok"] = False
                rec["xsd_err"] = str(e)[:200]
            try:
                await cli.publish("swarm.c2", msg)
                rec["pub"] = "+OK"
            except CalError as e:
                rec["pub"] = f"-ERR {e}"
            ext.cmds.append(rec)
            ext.write_full("tx", rec["t"], "MA_TaskCommand", "swarm.c2", msg["MA_TaskCommand"], rec["xsd_ok"])
            print(f"cmd {f.name} {c['kind'] if 'kind' in c else ''} -> {rec['pub']}", flush=True)
        if time.monotonic() - last > 1.0:
            ext.dump()
            last = time.monotonic()
        await asyncio.sleep(0.1)
    ext.dump()
    if ext.full is not None:
        ext.full.close()
    await cli.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

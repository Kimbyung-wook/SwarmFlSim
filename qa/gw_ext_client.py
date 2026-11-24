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
- 39차(DEC-111 봉투): `--envelope on`(기본, Gateway 기본과 같다)이면 MA_TxDataPayloadCommand를 vi·c2·p2p·ms에서 구독해
  봉투를 XSD로 검증하고 EncodedPayload(hexBinary)를 풀어 내부 메시지를 다시 검증한다. 보내는 것은 모두 MA_RxDataPayload로
  싼다. 봉투 처리는 Gateway 코드(envelope.py)를 쓰지 않고 README 설명대로 따로 만든다. rx 줄 끝(8번째)에 봉투 정보
  {name, ok, err, mt, mt_ok, dest}를 붙이고, full.jsonl rx 줄에는 내부 이름·본문과 함께 "env"(봉투 본문 요약)를 남긴다.
  명령 파일의 "env" {dest: [UUID], mtype: 값, none: true}로 부정 입력(주소 밖·MessageType 불일치·봉투 없음)을 만든다.
  `--envelope off`는 예전 흐름(내부 메시지를 그대로 주고받음)이다.

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
TX, RX = "MA_TxDataPayloadCommand", "MA_RxDataPayload"      # 39차: 봉투 (gateway/README.md "외부 교환 봉투")
ENV_SUBS = ("vi", "c2", "p2p", "ms")
ENVELOPE = True                                               # main()이 --envelope으로 바꾼다

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


def task_command(system_uuid: str, task_id: str, entities: list[str], kind: str, cancel: bool = False,
                 label_suffix: str = "") -> dict:
    cmds = [{"Capability": {
        "CommandID": ref(f"{task_id}/{e}"),
        "CommandState": "CANCEL" if cancel else "NEW",
        "CapabilityID": ref(f"{e}/{kind}"),
        "Ranking": {"Rank": {"Priority": 0, "PrecedenceWithinPriority": 0}},
        "TaskID": ref(task_id + label_suffix),
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


def message_type(name: str) -> str:
    """39차: 메시지 이름 → MessageTypeEnum 값 (MA_TaskCommand → MA_TASK_COMMAND)"""
    import re
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name).upper()


def inner_xml(codec, msg: dict) -> bytes:  # noqa: ANN001
    """내부 메시지 XML 문서. XSD 위반 부정 입력도 싸야 하므로 여기서는 검증하지 않는다"""
    from lxml import etree
    return etree.tostring(codec.json_to_xml(msg), xml_declaration=True, encoding="UTF-8")


def wrap_rx(cli, codec, msg: dict, env: dict) -> dict:  # noqa: ANN001
    """39차: 내부 메시지 → MA_RxDataPayload (외부 쪽 CAL이 하는 일). env: {dest, mtype}"""
    (name, body), = msg.items()
    hdr = dict(body["MessageHeader"])
    data = {"RxDataPayloadID": {"UUID": str(uuid.uuid4())}, "DataPayloadOriginatorID": {"UUID": cli.system_uuid},
            "EncodedPayload": inner_xml(codec, msg).hex().upper(), "Timestamp": hdr["Timestamp"],
            "MessageType": env.get("mtype") or message_type(name), "DestinationRouting": "TOPIC_AND_SPECIFIC_DESTINATION"}
    if env.get("dest"):
        data["SpecificDestinationID"] = [{"UUID": u} for u in env["dest"]]
    return {RX: {"SecurityInformation": body["SecurityInformation"], "MessageHeader": hdr, "MessageData": data}}


async def publish(cli, codec, ext, rec: dict, topic: str, msg: dict, env: dict | None = None) -> None:  # noqa: ANN001
    """msg(내부)를 검증해 rec에 남기고, 봉투 모드면 싸서 보낸다. rec: xsd_ok(내부), env_xsd_ok(봉투), pub"""
    env = env or {}
    name = next(iter(msg))
    try:
        codec.to_xml_bytes(msg)
        rec["xsd_ok"] = True
    except Exception as e:  # noqa: BLE001
        rec["xsd_ok"], rec["xsd_err"] = False, str(e)[:200]
    out = msg
    if ENVELOPE and not env.get("none"):
        try:
            out = wrap_rx(cli, codec, msg, env)
            codec.to_xml_bytes(out)
            rec["env_xsd_ok"] = True
        except Exception as e:  # noqa: BLE001
            rec["env_xsd_ok"], rec["env_err"] = False, str(e)[:200]
        rec["env"] = {"name": RX, "mt": out.get(RX, {}).get("MessageData", {}).get("MessageType"),
                      "dest": env.get("dest", [])}
    try:
        await cli.publish(topic, out)
        rec["pub"] = "+OK"
    except CalError as e:
        rec["pub"] = f"-ERR {e}"[:200]
    except Exception as e:  # noqa: BLE001  봉투를 못 만든 경우
        rec["pub"] = f"-ERR client {e}"[:200]
    ext.cmds.append(rec)
    ext.write_full("tx", rec["t"], name, topic, msg[name], rec["xsd_ok"],
                   env=(out[RX]["MessageData"] | {"EncodedPayload": f"<{len(out[RX]['MessageData']['EncodedPayload'])//2} B>"})
                   if RX in out else None)


async def send_raw(cli, codec, ext, fname: str, c: dict) -> None:  # noqa: ANN001
    """XSD를 통과하지 않는 메시지도 그대로 보내 서버 응답을 기록한다"""
    msg = envelope(cli.system_uuid, c["raw"], c["data"])
    rec = {"file": fname, "tag": c.get("tag", ""), "name": c["raw"], "topic": c["topic"], "t": round(time.time(), 3)}
    await publish(cli, codec, ext, rec, c["topic"], msg, c.get("env"))


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

    def on_env(self, topic: str):  # noqa: ANN201
        """39차: MA_TxDataPayloadCommand → 봉투 검증 → 내부 메시지 풀기·검증 → on_msg 처리"""
        from lxml import etree
        inner_cb = self.on_msg(topic)

        def cb(name: str, obj: dict) -> None:
            info = {"name": name, "ok": True, "err": "", "mt": "", "mt_ok": None, "dest": []}
            try:
                self.codec.to_xml_bytes(obj)
            except Exception as e:  # noqa: BLE001
                info["ok"], info["err"] = False, f"envelope: {e}"[:300]
            md = (obj.get(name) or {}).get("MessageData", {})
            info["mt"] = md.get("MessageType", "")
            info["dest"] = [d.get("UUID", "") for d in md.get("SpecificDestinationID", [])]
            try:
                raw = bytes.fromhex(md["EncodedPayload"])
                root = etree.fromstring(raw, parser=etree.XMLParser(resolve_entities=False, no_network=True))
                iname = etree.QName(root).localname
            except Exception as e:  # noqa: BLE001
                info["ok"], info["err"] = False, f"payload: {e}"[:300]
                inner_cb(name, obj, env=info, inner_ok=False)
                return
            inner_ok = True
            try:
                self.codec.validate_xml(root)
                inner = self.codec.xml_to_json(root)
            except Exception as e:  # noqa: BLE001
                inner_ok, info["err"] = False, (info["err"] + f" inner: {e}")[:300]
                inner = {iname: {}}
            info["mt_ok"] = info["mt"] == message_type(iname)
            info["inner_ascii"] = raw.isascii()
            info["inner_bytes"] = len(raw)
            body = obj.get(name, {})
            info["hdr_same"] = (body.get("MessageHeader") == (inner.get(iname) or {}).get("MessageHeader"))
            inner_cb(iname, inner, env=info, inner_ok=inner_ok)
        return cb

    def on_msg(self, topic: str):  # noqa: ANN201
        def cb(name: str, obj: dict, env: dict | None = None, inner_ok: bool = True) -> None:
            t = round(time.time(), 3)
            ok = inner_ok
            if env is not None:      # 봉투로 온 것: 내부는 on_env가 이미 검증했다
                if not inner_ok and len(self.xsd_fail) < 20:
                    self.xsd_fail.append(f"{name} (inner): {env.get('err')}"[:300])
                if not env["ok"] and len(self.xsd_fail) < 20:
                    self.xsd_fail.append(f"{env['name']} -> {name}: {env.get('err')}"[:300])
            else:
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
            elif name == "QueryDataRequestStatus":    # 39차 (DEC-112)
                res = (md.get("Result") or {}).get("Message", [])
                extra = {"req": label(md.get("RequestID")), "state": md.get("RequestProcessingState", ""),
                         "n": len(res), "types": sorted({k for r in res for k in r if k != "$type"} |
                                                         {r.get("$type", "") for r in res})[:6]}
            elif name in ("MA_LeaderUpdateRequest", "MA_Entity", "StoreLoadoutConfiguration"):
                extra = {"md": json.dumps(md, ensure_ascii=False, sort_keys=True)[:1500]}
            sysid = (body.get("MessageHeader") or {}).get("SystemID", {}).get("UUID", "")
            mode = (body.get("MessageHeader") or {}).get("Mode", "")
            row = [t, name, topic, ok, sysid, mode, extra]
            if env is not None:
                row.append(env)
            self.rx.append(row)
            self.write_full("rx", t, name, topic, body, ok, env=env)
        return cb

    def write_full(self, kind: str, t: float, name: str, topic: str, body: dict, ok: bool,
                   env: dict | None = None) -> None:
        if self.full is not None:
            d = {"k": kind, "t": t, "name": name, "topic": topic, "ok": ok, "body": body}
            if env is not None:
                d["env"] = env
            self.full.write(json.dumps(d, ensure_ascii=False) + "\n")

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
    ap.add_argument("--envelope", choices=("on", "off"), default="on", help="39차: 봉투(DEC-111). Gateway와 맞춘다")
    a = ap.parse_args()
    global ENVELOPE
    ENVELOPE = a.envelope == "on"
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
    for iface in (ENV_SUBS if ENVELOPE else ()):
        try:
            await cli.subscribe(TX, f"swarm.{iface}", ext.on_env(f"swarm.{iface}"))
        except CalError as e:
            sub_err[f"{TX}@{iface}"] = str(e)
    for name, iface in ({} if ENVELOPE else EXPORTS).items():
        try:
            await cli.subscribe(name, f"swarm.{iface}", ext.on_msg(f"swarm.{iface}"))
        except CalError as e:
            sub_err[name] = str(e)
    for name, iface in ([] if ENVELOPE else EXTRA_SUBS):
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
    nsub = len(ENV_SUBS) if ENVELOPE else len(EXPORTS) + len(EXTRA_SUBS)
    print(f"ext ready system={cli.system_uuid} envelope={'on' if ENVELOPE else 'off'} subs={nsub - len(sub_err)}",
          flush=True)
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
                               c.get("cancel", False), c.get("label_suffix", ""))
            rec = {**c, "t": round(time.time(), 3), "file": f.name}
            await publish(cli, codec, ext, rec, "swarm.c2", msg, c.get("env"))
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

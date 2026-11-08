"""QA 15차 외부 CAL Client (TC-QA-069~073). gateway/.venv의 python으로 띄운다.

- agra_lacal CAL Server에 `external_c2` 서비스로 접속해 Gateway 발행 13종을 모두 구독한다.
- 받은 메시지마다 이 프로세스가 따로 적재한 공개 XSD(A-GRA 6.0a)로 다시 검증한다(서버 검증과 별개).
- 관리 포트 /tap으로 서버를 지나간 모든 메시지 이름·발신 서비스를 센다(구독하지 않은 이름도 보인다).
- <out>/cmd/NNN.json 명령 파일을 읽어 MA_TaskCommand를 PUB한다. Gateway 변환기를 쓰지 않고 JSON을 직접 만든다.
- <out>/ext.json에 수신 기록을 1 s마다 쓴다. <out>/STOP 파일이 생기면 끝낸다.

gateway/.venv/Scripts/python.exe qa/gw_ext_client.py --url ws://127.0.0.1:18765 --admin 127.0.0.1:18766 --out <dir>
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
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


def label(obj) -> str:  # noqa: ANN001
    return obj.get("DescriptiveLabel", "") if isinstance(obj, dict) else ""


class Ext:
    def __init__(self, out: Path, codec: OmsJsonCodec) -> None:
        self.out, self.codec = out, codec
        self.t0 = time.monotonic()
        self.rx: list[list] = []          # [t, name, topic, xsd_ok, origin_system, extra]
        self.xsd_fail: list[str] = []
        self.tap: Counter = Counter()      # (name, origin service) 서버 통과 수
        self.tap_t: list[list] = []        # [t, name]
        self.cmds: list[dict] = []
        self.errors: list[str] = []

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
            elif name in ("PO_Activity", "EA_Activity", "StrikeActivity"):
                extra = {"keys": sorted(md.keys())[:6]}
            sysid = (body.get("MessageHeader") or {}).get("SystemID", {}).get("UUID", "")
            mode = (body.get("MessageHeader") or {}).get("Mode", "")
            self.rx.append([t, name, topic, ok, sysid, mode, extra])
        return cb

    def dump(self) -> None:
        d = {"rx": self.rx, "xsd_fail": self.xsd_fail, "tap": [[k[0], k[1], v] for k, v in self.tap.items()],
             "tap_t": self.tap_t, "cmds": self.cmds, "errors": self.errors, "t_wall": time.monotonic() - self.t0}
        tmp = self.out / "ext.tmp"
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.out / "ext.json")


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
    a = ap.parse_args()
    out = Path(a.out)
    (out / "cmd").mkdir(parents=True, exist_ok=True)
    codec = OmsJsonCodec(XSD)
    ext = Ext(out, codec)
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
    ext.errors += [f"sub {k}: {v}" for k, v in sub_err.items()]
    asyncio.create_task(tap_loop(ext, a.admin))
    print(f"ext ready system={cli.system_uuid} subs={len(EXPORTS) - len(sub_err)}", flush=True)
    (out / "ext.ready").write_text("ok", encoding="utf-8")
    done: set[str] = set()
    last = 0.0
    while not (out / "STOP").exists():
        for f in sorted((out / "cmd").glob("*.json")):
            if f.name in done:
                continue
            done.add(f.name)
            c = json.loads(f.read_text(encoding="utf-8"))
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
            print(f"cmd {f.name} {c['kind'] if 'kind' in c else ''} -> {rec['pub']}", flush=True)
        if time.monotonic() - last > 1.0:
            ext.dump()
            last = time.monotonic()
        await asyncio.sleep(0.1)
    ext.dump()
    await cli.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

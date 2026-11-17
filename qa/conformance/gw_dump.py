"""C1 입력 수집: proto descriptor 옵션과 Gateway 변환기 등록을 JSON으로 낸다. gateway/.venv의 python으로 띄운다.

- proto 옵션은 swarm.v1 모듈의 descriptor에서 직접 읽는다(Gateway mapping.py를 거치지 않는다).
- 변환기는 Gateway의 등록 함수(load_converters, load_also_converters)가 돌려주는 그대로(Gateway가 걸러 내기 전)와,
  Gateway 객체를 만든 뒤 실제로 쓰는 것(export_targets, import_names)을 따로 적는다.

gateway/.venv/Scripts/python.exe qa/conformance/gw_dump.py <out.json>
"""
from __future__ import annotations

import inspect
import json
import sys

from swarm.v1 import (c2_pb2, common_pb2, entity_pb2, fa_pb2, link_pb2, mp_pb2, ms_pb2, options_pb2, p2p_pb2,
                      sim_pb2, truth_pb2, vi_pb2)

MODULES = (c2_pb2, common_pb2, entity_pb2, fa_pb2, link_pb2, mp_pb2, ms_pb2, p2p_pb2, sim_pb2, truth_pb2, vi_pb2)


def proto_options() -> list[dict]:
    out = []
    for mod in MODULES:
        for desc in mod.DESCRIPTOR.message_types_by_name.values():
            o = desc.GetOptions()
            out.append({"full_name": desc.full_name, "short": desc.name, "file": mod.DESCRIPTOR.name,
                        "uci_name": o.Extensions[options_pb2.uci_name],
                        "uci_also": list(o.Extensions[options_pb2.uci_also]),
                        "mapping": options_pb2.MappingClass.Name(o.Extensions[options_pb2.mapping]).removeprefix(
                            "MAPPING_CLASS_"),
                        "l1": options_pb2.L1Interface.Name(o.Extensions[options_pb2.l1]).removeprefix("L1_INTERFACE_")})
    return out


def main() -> None:
    from swarm_gateway.converters import load_also_converters, load_converters
    from swarm_gateway.converters import c2 as c2conv
    from swarm_gateway.gateway import Gateway, GatewayConfig
    convs = load_converters()
    also = load_also_converters()
    gw = Gateway(None, GatewayConfig(gcs="gcs-01"))  # type: ignore[arg-type]  버스는 쓰지 않는다
    d = {
        "proto": proto_options(),
        "converters": [{"proto": name, "cls": type(c).__name__, "module": inspect.getmodule(c).__name__,
                        "export": c.supports_export(), "import": c.supports_import()} for name, c in convs.items()],
        "also_converters": [{"uci": u, "cls": type(c).__name__, "module": inspect.getmodule(c).__name__,
                             "protos": list(c.protos), "export": c.supports_export()} for u, c in also.items()],
        "effective_export": sorted({f"{e.full_name}->{u}" for e, u in gw.export_targets()}),
        "effective_import": gw.import_names(),
        "importable_tasks": list(c2conv.IMPORTABLE_TASKS),
    }
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

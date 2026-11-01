"""proto/ 의 스키마로 Python 코드를 생성한다.

출력: api/python/src/swarm/v1/*_pb2.py (버전 관리하지 않음)
실행: uv run python scripts/gen_proto.py
"""

from pathlib import Path
import sys

import grpc_tools
from grpc_tools import protoc

ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "proto"
OUT_DIR = ROOT / "api" / "python" / "src"


def main() -> int:
    # protoc는 파일 인자를 현재 디렉터리 기준으로 찾으므로 절대 경로로 넘긴다.
    # -I(PROTO_DIR) 기준 상대 경로가 import 이름(swarm/v1/...)이 된다.
    protos = sorted(p.as_posix() for p in (PROTO_DIR / "swarm" / "v1").glob("*.proto"))
    well_known = Path(grpc_tools.__file__).parent / "_proto"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rc = protoc.main([
        "protoc",
        f"-I{PROTO_DIR.as_posix()}",
        f"-I{well_known.as_posix()}",
        f"--python_out={OUT_DIR.as_posix()}",
        f"--pyi_out={OUT_DIR.as_posix()}",
        *protos,
    ])
    if rc != 0:
        return rc
    for pkg in (OUT_DIR / "swarm", OUT_DIR / "swarm" / "v1"):
        (pkg / "__init__.py").touch()
    print(f"generated {len(protos)} protos into {OUT_DIR / 'swarm' / 'v1'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

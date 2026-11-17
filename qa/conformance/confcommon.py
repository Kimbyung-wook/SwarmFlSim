"""표준 적합성 점검 도구 공용 (DEC-092, docs/44_standards_conformance.md).

결과 파일 쓰기·읽기는 Windows에서 다른 프로세스가 같은 파일을 여는 중이면 os.replace가 PermissionError로 실패한다
(PM 보고: 데모에서 ext.json 2회 재현). 그래서 쓰는 쪽은 짧게 재시도하고, 끝내 실패하면 예외를 올리지 않고
False를 돌려준다(다음 주기에 다시 쓴다). 읽는 쪽도 재시도한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parent
GW_PY = ROOT / "gateway" / ".venv" / "Scripts" / "python.exe"
LACAL = ROOT / "third_party" / "agra_lacal"
XSD = LACAL / "schema" / "A-GRA_MessageDefinitions_v6_0_a.xsd"
LACAL_CFG = ROOT / "gateway" / "config" / "lacal_server.yaml"
CONFORMANCE_DOC = ROOT / "docs" / "44_standards_conformance.md"
REPORT_DOC = ROOT / "docs" / "45_standards_report.md"

PASS, FAIL, INFO = "통과", "실패", "정보"


def write_json(path: Path, data, retries: int = 20, delay: float = 0.05) -> bool:
    """임시 파일에 쓰고 바꿔 넣는다. 읽는 프로세스 때문에 바꾸지 못하면 재시도하고, 끝내 못 하면 False"""
    path = Path(path)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    for _ in range(retries):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(delay)
    try:
        tmp.unlink()
    except OSError:
        pass
    return False


def read_json(path: Path, default=None, retries: int = 20, delay: float = 0.05):
    path = Path(path)
    for _ in range(retries):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except (PermissionError, json.JSONDecodeError):
            time.sleep(delay)
    return default


def git(*args: str, cwd: Path = ROOT) -> str:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                              encoding="utf-8").stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def versions() -> dict:
    import re
    init = (ROOT / "api" / "python" / "src" / "swarm_api" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'CONTRACT_VERSION\s*=\s*"([^"]+)"', init)
    return {"commit": git("rev-parse", "--short", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "contract": m.group(1) if m else "",
            "agra_lacal": git("rev-parse", "--short", "HEAD", cwd=LACAL)}


def md_cell(v) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")

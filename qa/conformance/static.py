"""정적 입력 수집: C1(proto·변환기·XSD·등록부·추적표), C4 소스, C7 소스 점검."""
from __future__ import annotations

import ast
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from confcommon import GW_PY, HERE, ROOT, XSD, read_json

XS = "{http://www.w3.org/2001/XMLSchema}"


def xsd_top_elements(path: Path = XSD) -> set[str]:
    """공개 XSD의 최상위(전역) 요소 이름. Gateway 코덱과 별개로 표준 라이브러리로 읽는다"""
    root = ET.parse(path).getroot()
    return {el.get("name") for el in root.findall(f"{XS}element") if el.get("name")}


def gateway_dump(out: Path) -> dict:
    subprocess.run([str(GW_PY), str(HERE / "gw_dump.py"), str(out)], cwd=ROOT, check=True,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    return read_json(out)


def registry_rows(md: str) -> list[dict]:
    """등록부 §5 표 → [{l1, interaction, candidates, cls}]"""
    sec = md.split("## 5. A-GRA 메시지 매핑", 1)[1]
    rows = []
    for ln in sec.splitlines():
        if not ln.startswith("| ") or ln.startswith("| L1") or ln.startswith("|---"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 4:
            continue
        rows.append({"l1": c[0], "interaction": c[1], "candidates": re.findall(r"`([A-Za-z_]+)`", c[2]),
                     "cls": c[3].split()[0] if c[3] else ""})
    return rows


def trace_ids(md: str, names: list[str]) -> dict[str, dict]:
    """gateway/TRACE.md 구현 표: 행 내용에 메시지 이름이 나오면 그 IMP와, 그 행의 시험 결과에 적힌 TC를 붙인다"""
    out: dict[str, dict] = {n: {"imp": [], "tc": []} for n in names}
    for ln in md.splitlines():
        m = re.match(r"\| (IMP-GW-\d+) \| (.*)", ln)
        if not m:
            continue
        imp, rest = m.group(1), m.group(2)
        cells = [x.strip() for x in rest.split("|")]
        body, result = cells[0], cells[-2] if len(cells) >= 2 else ""
        tcs = []
        for a, b in re.findall(r"TC-GW-(\d+)(?:~(?:TC-GW-)?(\d+))?", result):
            tcs += [f"TC-GW-{i:03d}" for i in range(int(a), int(b or a) + 1)]
        for n in names:
            if re.search(rf"(?<![A-Za-z_]){re.escape(n)}(?![A-Za-z_])", body):
                out[n]["imp"].append(imp)
                out[n]["tc"] += tcs
    return {k: {"imp": sorted(set(v["imp"])), "tc": sorted(set(v["tc"]))} for k, v in out.items()}


def ma_imports(src: Path = ROOT / "algorithms" / "src" / "swarm_algorithms") -> list[dict]:
    rows = []
    for f in sorted(src.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        rel = f.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    rows.append({"file": rel, "line": node.lineno, "module": a.name, "names": []})
            elif isinstance(node, ast.ImportFrom):
                if node.level:          # 패키지 안 상대 import
                    rows.append({"file": rel, "line": node.lineno, "module": "." + (node.module or ""),
                                 "names": [a.name for a in node.names]})
                else:
                    rows.append({"file": rel, "line": node.lineno, "module": node.module or "",
                                 "names": [a.name for a in node.names]})
    return rows


def ma_key_literals(src: Path = ROOT / "algorithms" / "src" / "swarm_algorithms") -> list[str]:
    """MA 소스의 문자열에 버스 키 접두어가 있는지 (truth/, sim/ctrl/, link/, swarm/, onboard/)"""
    hits = []
    for f in sorted(src.glob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.match(
                    r"^(truth|sim/ctrl|link|swarm|onboard)/", node.value):
                hits.append(f"{f.relative_to(ROOT).as_posix()}:{node.lineno} {node.value!r}")
    return hits


SKIP_DIRS = ("third_party", ".venv", "node_modules", "build", "out", ".git", "vcpkg_installed", "__pycache__")
BUS_IMPL = ("api/python/src/swarm_api/bus.py", "bus/")
ENTRY_POINTS = {
    "Sim Core": "core/src/main.cpp", "Datalink": "datalink/src/main.cpp", "Logger": "logger/src/main.cpp",
    "Agent": "agent/src/swarm_agent/cli.py", "Bridge": "bridge/src/swarm_bridge/cli.py",
    "Gateway": "gateway/src/swarm_gateway/__main__.py",
}
PY_DIRECT = re.compile(r"^\s*(import zenoh|from zenoh\b)|zenoh\.open\(", re.M)
CPP_DIRECT = re.compile(r"zenoh::Session::open|\bz_open\s*\(|zenoh::Session\s*\(")


def bus_open_scan() -> tuple[list[str], dict[str, bool]]:
    """제품 소스(시험 제외)에서 open_bus 밖의 Zenoh 세션 열기, 프로세스 진입점의 open_bus 사용"""
    direct = []
    for f in ROOT.rglob("*"):
        if not f.is_file() or f.suffix not in (".py", ".cpp", ".hpp", ".h"):
            continue
        rel = f.relative_to(ROOT).as_posix()
        parts = rel.split("/")
        if any(p in SKIP_DIRS for p in parts) or "tests" in parts or parts[0] in ("qa", "scripts", "reference",
                                                                                   "examples"):
            continue
        if any(rel.startswith(b) for b in BUS_IMPL):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        rx = PY_DIRECT if f.suffix == ".py" else CPP_DIRECT
        for m in rx.finditer(text):
            direct.append(f"{rel}:{text[:m.start()].count(chr(10)) + 1} {m.group(0).strip()}")
    entries = {k: "open_bus" in (ROOT / v).read_text(encoding="utf-8", errors="replace")
               for k, v in ENTRY_POINTS.items()}
    return direct, entries


# ---------------------------------------------------------------------------- C7 적용성 표 (docs/46, DEC-093)
AMSGRA_DOC = ROOT / "docs" / "46_amsgra_applicability.md"
FILE_EXT = r"(?:py|md|yaml|yml|json|lock|toml|txt|cmake|proto|xsd|ts|tsx|cpp|hpp|h)"
PATH_TOKEN = re.compile(rf"`([\w./-]+\.{FILE_EXT})`")
DEC_TOKEN = re.compile(r"\bDEC-\d{3}\b")


def _cells(ln: str) -> list[str]:
    return [x.strip() for x in ln.strip().strip("|").split("|")]


def amsgra_applicability(md: str) -> dict:
    """docs/46 → {summary: §3 요약표 행, rows: §4 상세 행 [{id, verdict, gist, basis}]}"""
    s3 = md.split("## 3. 요약", 1)[1].split("\n## ", 1)[0]
    head, summary = None, []
    for ln in s3.splitlines():
        if not ln.startswith("|") or ln.startswith("|---"):
            continue
        if head is None:
            head = _cells(ln)
            continue
        summary.append(_cells(ln))
    s4 = md.split("## 4. 상세", 1)[1].split("\n## ", 1)[0]
    rows = []
    for ln in s4.splitlines():
        if not ln.startswith("| GRA-"):
            continue
        c = _cells(ln)
        if len(c) < 7:
            continue
        rows.append({"id": c[0], "tier": c[1], "verdict": c[4], "gist": c[5], "basis": c[6]})
    return {"head": head or [], "summary": summary, "rows": rows}


def repo_files() -> set[str]:
    """저장소에 추적되는 파일 경로(작업 트리 기준, posix)"""
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True)
    return {x.strip() for x in out.stdout.splitlines() if x.strip()}


def basis_refs(basis: str) -> dict[str, list[str]]:
    """근거 칸에서 확인할 참조: 백틱 파일 경로(확장자가 있는 것)와 DEC ID. 코드 식별자·키·WP·계약 절은 보지 않는다"""
    return {"paths": PATH_TOKEN.findall(basis), "decs": sorted(set(DEC_TOKEN.findall(basis)))}


def registry_decs(md: str) -> set[str]:
    return set(re.findall(r"^\| (DEC-\d{3}) \|", md, re.M))


def conformance_limits(md: str) -> list[str]:
    """docs/44 §4 한계 → 항목 문구(앞의 '- ' 제외). 보고서 한계 절에 그대로 싣는다"""
    sec = md.split("## 4. 한계", 1)[1].split("\n## ", 1)[0]
    return [ln[2:].strip() for ln in sec.splitlines() if ln.startswith("- ")]

"""표준 점검 이력 (DEC-095, docs/44 §6).

- 실행마다 `qa/conformance/history.jsonl`에 한 줄을 덧붙인다. 이미 있는 줄은 고치거나 지우지 않는다.
- `history.jsonl`과 git 기록으로 `docs/47_conformance_history.md`를 만든다(손으로 고치지 않는다).

uv run python qa/conformance/history.py backfill --out qa/out/conformance/2026-11-17   # 과거 실행 소급 기록
uv run python qa/conformance/history.py build                                        # docs/47만 다시 만든다
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from confcommon import CONFORMANCE_DOC, ROOT, git, read_json  # noqa: E402

HISTORY = HERE / "history.jsonl"
HISTORY_DOC = ROOT / "docs" / "47_conformance_history.md"
ITEMS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")
UNKNOWN = "미확인"
CRITERIA_PATH = CONFORMANCE_DOC.relative_to(ROOT).as_posix()      # docs/44_standards_conformance.md
TOOL_PATH = HERE.relative_to(ROOT).as_posix()                       # qa/conformance
# 도구 커밋에서 뺀다: 이력 파일은 실행마다 늘어나 도구 변경이 아니다
TOOL_EXCLUDE = f":!{TOOL_PATH}/history.jsonl"
DEC_RE = re.compile(r"DEC-\d{3}")


# ------------------------------------------------------------------------------------------------ 실행 기록

def last_commit(path_args: list[str], rev: str = "HEAD") -> str:
    """rev 시점에서 path를 마지막으로 바꾼 커밋(짧은 해시). 없으면 미확인"""
    return git("log", "-1", "--format=%h", rev, "--", *path_args) or UNKNOWN


def make_entry(R: dict, *, repeat: int, mode: str = "run", rev: str = "HEAD", derived: list[str] | None = None) -> dict:
    """run.py의 결과 dict R(result.json과 같은 모양) → 이력 한 줄"""
    v, meta = R.get("versions", {}), R.get("meta", {})
    res = R.get("results", {})
    key = R.get("key", {})
    items = {}
    for k in ITEMS:
        r = res.get(k)
        items[k] = ({"verdict": r.get("verdict", UNKNOWN), "n_fail": len(r.get("fail", [])), "key": key.get(k, UNKNOWN)}
                    if r else {"verdict": UNKNOWN, "n_fail": UNKNOWN, "key": UNKNOWN})
    fnd = R.get("findings")
    return {
        "schema": 1,
        "mode": mode,
        "date": meta.get("date", UNKNOWN),
        "out": meta.get("out", UNKNOWN),
        "commit": v.get("commit") or UNKNOWN,
        "dirty": v.get("dirty", UNKNOWN),
        "contract": v.get("contract") or UNKNOWN,
        "agra_lacal": v.get("agra_lacal") or UNKNOWN,
        "criteria_commit": last_commit([CRITERIA_PATH], rev),
        "tool_commit": last_commit([TOOL_PATH, TOOL_EXCLUDE], rev),
        "seed": (R.get("run") or {}).get("seed", UNKNOWN),
        "repeat": repeat,
        "items": items,
        "findings": sorted(f["id"] for f in fnd if f.get("hits")) if fnd is not None else UNKNOWN,
        "derived": derived or [],
    }


def append(entry: dict, path: Path = HISTORY) -> None:
    """한 줄 덧붙이기. 파일을 다시 쓰지 않는다(DEC-095)"""
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def load(path: Path = HISTORY) -> list[dict]:
    """이력 줄 목록. mode "correction" 줄은 행으로 세지 않고, 결과 폴더(out)가 같은 앞선 실행의 발견을 바꾸고 메모를 단다
    (38차: 파일은 덧붙이기만 하므로 분류 정정도 새 줄로 남긴다, DEC-095)"""
    if not path.exists():
        return []
    out: list[dict] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        e = json.loads(ln)
        if e.get("mode") == "correction":
            for t in reversed(out):
                if t.get("out") == e.get("out"):
                    if "findings" in e:
                        t["findings_tool"] = t.get("findings")
                        t["findings"] = e["findings"]
                    t.setdefault("notes", []).append(e.get("note", ""))
                    break
            continue
        out.append(e)
    return out


def correction(out: str, note: str, findings: list[str] | None = None) -> dict:
    """앞선 실행(결과 폴더 out)의 발견 분류 정정 한 줄"""
    e: dict = {"schema": 1, "mode": "correction", "out": out, "note": note}
    if findings is not None:
        e["findings"] = sorted(findings)
    return e


def backfill(out_dir: Path) -> dict:
    """이전 실행 결과 폴더(result.json)에서 이력 한 줄을 만든다. 기준·도구 커밋은 대상 커밋 시점의 git 기록에서 얻는다"""
    R = read_json(out_dir / "result.json")
    if R is None:
        raise SystemExit(f"{out_dir}/result.json이 없다")
    rep = (R.get("repeat") or {}).get("runs") or (1 if R.get("results") else UNKNOWN)
    rev = (R.get("versions") or {}).get("commit") or "HEAD"
    return make_entry(R, repeat=rep, mode="backfill", rev=rev,
                      derived=["criteria_commit", "tool_commit"] + ([] if R.get("repeat") else ["repeat"]))


# ------------------------------------------------------------------------------------------------ git 기록

def condition_changes() -> list[dict]:
    """docs/44와 qa/conformance(이력 파일 제외)를 바꾼 커밋. 병합 커밋은 뺀다(같은 변경이 두 번 나오지 않게)"""
    fmt = "%h%x1f%ad%x1f%s%x1f%b%x1e"
    raw = git("log", "--no-merges", "--date=short", f"--format={fmt}", "--", CRITERIA_PATH, TOOL_PATH, TOOL_EXCLUDE)
    out = []
    for rec in raw.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        h, d, subj, body = (rec.split("\x1f") + ["", "", "", ""])[:4]
        files = git("show", "--name-only", "--format=", h).splitlines()
        what = []
        if any(f == CRITERIA_PATH for f in files):
            what.append("기준(docs/44)")
        if any(f.startswith(TOOL_PATH + "/") and not f.endswith("history.jsonl") for f in files):
            what.append("도구(qa/conformance)")
        out.append({"commit": h, "date": d, "subject": subj, "what": what,
                    "decs": sorted(set(DEC_RE.findall(subj + "\n" + body)))})
    return out


def changes_between(a: str, b: str) -> list[str] | str:
    """두 실행 대상 커밋 사이(a..b)에 점검 조건(docs/44·qa/conformance, 이력 파일 제외)을 바꾼 커밋.
    '`<해시>` 기준|도구', 기준 커밋에는 제목·본문의 DEC를 괄호에 붙인다(해소 원인 판단용)"""
    if UNKNOWN in (a, b) or not a or not b:
        return UNKNOWN
    out = []
    for h in git("log", "--no-merges", "--format=%h", f"{a}..{b}", "--", CRITERIA_PATH, TOOL_PATH, TOOL_EXCLUDE).split():
        files = git("show", "--name-only", "--format=", h).splitlines()
        what = (["기준"] if CRITERIA_PATH in files else []) + (
            ["도구"] if any(f.startswith(TOOL_PATH + "/") and not f.endswith("history.jsonl") for f in files) else [])
        decs = sorted(set(DEC_RE.findall(git("show", "-s", "--format=%s%n%b", h)))) if "기준" in what else []
        out.append(f"`{h}` {'·'.join(what)}" + (f"({', '.join(decs)})" if decs else ""))
    return out


# ------------------------------------------------------------------------------------------------ docs/47

def _cell(x) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def _table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return out


def _target(e: dict) -> str:
    c = e.get("commit", UNKNOWN)
    d = e.get("dirty")
    if d is True:
        return f"`{c}` (dirty)"
    if d == UNKNOWN:
        return f"`{c}` (dirty {UNKNOWN})"
    return f"`{c}`"


def run_rows(entries: list[dict]) -> list[list]:
    """실행 이력 표. 이전 실행과 판정이 다르면 '← 이전'을 붙이고 굵게 쓴다"""
    rows = []
    prev = None
    for i, e in enumerate(entries, 1):
        cells = []
        for k in ITEMS:
            it = e.get("items", {}).get(k, {})
            vd = it.get("verdict", UNKNOWN)
            pv = prev.get("items", {}).get(k, {}).get("verdict") if prev else None
            cells.append(f"**{vd}** (← {pv})" if pv is not None and pv != vd else vd)
        fl = e.get("findings")
        rows.append([i, e.get("date", UNKNOWN), f"`{e.get('out', UNKNOWN)}`", _target(e), e.get("contract", UNKNOWN),
                     f"`{e.get('criteria_commit', UNKNOWN)}`", f"`{e.get('tool_commit', UNKNOWN)}`",
                     e.get("seed", UNKNOWN), e.get("repeat", UNKNOWN), *cells,
                     ", ".join(fl) if isinstance(fl, list) and fl else ("없음" if fl == [] else UNKNOWN)])
        prev = e
    return rows


def gone_cause(changes: list[str] | str, resolution: str) -> str:
    """해소 원인: 발견의 조치 문구(findings.py resolution)에 적힌 DEC가 사이의 기준 커밋 DEC와 겹치면 기준 변경, 아니면 제품 변경"""
    if isinstance(changes, str):
        return UNKNOWN
    want = set(DEC_RE.findall(resolution or ""))
    hit = []
    for c in changes:
        if "기준" in c:
            h = c.split("`")[1]
            hit += [f"{d} `{h}`" for d in DEC_RE.findall(c) if d in want]
    return f"기준 변경({', '.join(hit)})" if hit else "제품 변경"


def finding_rows(entries: list[dict], known: list[str] | None = None, between=None,  # noqa: ANN001
                 resolutions: dict[str, str] | None = None) -> list[list]:
    """발견 추적 표: 처음 나온 실행·커밋, 마지막 재현, 사라진 실행·커밋, 상태, 사라질 때 바뀐 점검 조건.
    between(a, b): 두 대상 커밋 사이의 조건 변경 커밋 목록(기본 changes_between). 비어 있으면 제품 변경으로 사라진 것이다"""
    between = between or changes_between
    ids: list[str] = []
    for i in known or []:
        if i not in ids:
            ids.append(i)
    for e in entries:
        fl = e.get("findings")
        for i in fl if isinstance(fl, list) else []:
            if i not in ids:
                ids.append(i)
    rows = []
    for fid in ids:
        seen = [n for n, e in enumerate(entries, 1) if isinstance(e.get("findings"), list) and fid in e["findings"]]
        if not seen:
            continue           # 도구 발견 목록에는 있지만 어느 실행에서도 재현되지 않음(문서·기존 항목)
        first, last = seen[0], seen[-1]
        gone = next((n for n in range(last + 1, len(entries) + 1)
                     if isinstance(entries[n - 1].get("findings"), list)), None)
        e1, el = entries[first - 1], entries[last - 1]
        status = "재현" if last == len(entries) else ("해소" if gone else UNKNOWN)
        cond = cause = "—"
        if gone:
            ch = between(el.get("commit", UNKNOWN), entries[gone - 1].get("commit", UNKNOWN))
            cond = ch if isinstance(ch, str) else (", ".join(ch) or "없음(제품 변경)")
            cause = gone_cause(ch, (resolutions or {}).get(fid, ""))
        rows.append([fid, f"{first} (`{e1.get('commit', UNKNOWN)}`)",
                     f"{last} (`{el.get('commit', UNKNOWN)}`)",
                     f"{gone} (`{entries[gone - 1].get('commit', UNKNOWN)}`)" if gone else "—", status, cond, cause])
    return rows


def build_md(entries: list[dict], changes: list[dict], known: list[str] | None = None, between=None,  # noqa: ANN001
             resolutions: dict[str, str] | None = None) -> str:
    L = ["# 표준 점검 이력 (DEC-095)", "",
         "이 문서는 `qa/conformance/history.py`가 `qa/conformance/history.jsonl`과 git 기록으로 만든다(손으로 고치지 않는다). "
         "기준은 [44_standards_conformance.md](44_standards_conformance.md) §6이고, 마지막 실행의 상세 결과는 "
         "[45_standards_report.md](45_standards_report.md)에 있다.", ""]
    L += ["## 1. 실행 이력", "",
          "실행마다 한 행. 판정이 이전 실행과 다르면 굵게 쓰고 이전 판정을 괄호에 적는다. 기준 커밋은 그 실행 시점에 "
          "`docs/44`를 마지막으로 바꾼 커밋, 도구 커밋은 `qa/conformance/`(이력 파일 제외)를 마지막으로 바꾼 커밋이다. "
          f"원자료에 없는 값은 '{UNKNOWN}'이다.", ""]
    L += _table(["#", "날짜", "결과 폴더", "대상 커밋", "계약", "기준 커밋", "도구 커밋", "시드", "반복", *ITEMS, "발견"],
                run_rows(entries))
    L.append("")
    notes = [(n, e) for n, e in enumerate(entries, 1) if e.get("mode") == "backfill"]
    for n, e in notes:
        L.append(f"- 실행 {n}은 결과 폴더의 `result.json`에서 소급 기록했다. "
                 + (f"git에서 얻은 값: {', '.join(e['derived'])}." if e.get("derived") else ""))
    corr = [(n, e) for n, e in enumerate(entries, 1) if e.get("notes")]
    for n, e in corr:
        tool = e.get("findings_tool")
        L += [f"- 실행 {n}: {t}" + (f" (도구 자동 분류: {', '.join(tool) or '없음'})" if isinstance(tool, list) else "")
              for t in e["notes"]]
    if notes or corr:
        L.append("")
    L.append("핵심 수치:")
    L.append("")
    L += _table(["#", *ITEMS], [[n, *[e.get("items", {}).get(k, {}).get("key", UNKNOWN) for k in ITEMS]]
                                for n, e in enumerate(entries, 1)])
    L.append("")
    L += ["## 2. 점검 조건 변경 이력", "",
          "`docs/44`와 `qa/conformance/`(이력 파일 제외)를 바꾼 커밋. 병합 커밋은 뺀다. 판정이 바뀐 실행 사이에 이 표의 커밋이 "
          "있으면 조건 변경 때문일 수 있고, 없으면 제품 변경 때문이다.", ""]
    L += _table(["커밋", "날짜", "바뀐 것", "제목", "관련 DEC"],
                [[f"`{c['commit']}`", c["date"], ", ".join(c["what"]) or "—", c["subject"], ", ".join(c["decs"]) or "—"]
                 for c in changes])
    L.append("")
    L += ["## 3. 발견 추적", "",
          "발견 ID는 `qa/conformance/findings.py`의 match 규칙으로 실행마다 같은 현상에 같은 ID가 붙는다. "
          "상태: 재현 = 마지막 실행에서도 나왔다, 해소 = 나온 뒤 이후 실행에서 사라졌다. "
          "'사이 조건 변경'은 마지막 재현 실행과 사라진 실행의 대상 커밋 사이에 점검 조건(2절)을 바꾼 커밋이다. "
          "'해소 원인'은 발견의 조치 문구(`findings.py` resolution)에 적힌 DEC가 그 사이 기준 커밋의 DEC와 겹치면 "
          "'기준 변경', 아니면 '제품 변경'이다.", ""]
    frows = finding_rows(entries, known, between, resolutions)
    L += _table(["발견", "처음 나온 실행 (커밋)", "마지막 재현 (커밋)", "사라진 실행 (커밋)", "상태", "사이 조건 변경",
                 "해소 원인"], frows)
    L.append("")
    never = [i for i in (known or []) if i not in {r[0] for r in frows}]
    if never:
        L += [f"도구 발견 목록에는 있지만 기록된 실행에서 나온 적 없는 발견: {', '.join(never)}. "
              "기록 전 실행에서 나왔거나, 원자료 재판정에서만 나왔거나, 문서 항목이다(docs/21).", ""]
    return "\n".join(L) + "\n"


def write_doc(entries: list[dict] | None = None, path: Path = HISTORY_DOC) -> str:
    import findings as F
    entries = load() if entries is None else entries
    md = build_md(entries, condition_changes(), [f["id"] for f in F.FINDINGS],
                  resolutions={f["id"]: f.get("resolution", "") for f in F.FINDINGS})
    path.write_text(md, encoding="utf-8", newline="\n")
    return md


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill", help="이전 실행 결과 폴더로 이력 한 줄을 덧붙인다")
    b.add_argument("--out", required=True)
    sub.add_parser("build", help="docs/47을 다시 만든다")
    a = ap.parse_args()
    if a.cmd == "backfill":
        d = Path(a.out)
        d = d if d.is_absolute() else ROOT / d
        rel = d.relative_to(ROOT).as_posix()
        if any(e.get("out") == rel for e in load()):
            raise SystemExit(f"{rel}은 이미 이력에 있다(덧붙이기만 하므로 다시 넣지 않는다)")
        append(backfill(d))
    write_doc()
    print(f"[history] {len(load())}줄 → {HISTORY_DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

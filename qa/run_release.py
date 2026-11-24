"""qa/ 도구를 msvc-release 빌드로 돌린다 (QA 37차). harness.BUILD만 바꾸고 대상 스크립트를 __main__으로 실행한다.

uv run --with psutil python qa/run_release.py qa/p5_e2e.py --mode realtime ...
"""
import runpy
import sys
from pathlib import Path

QA = Path(__file__).resolve().parent
sys.path.insert(0, str(QA))
import harness as h  # noqa: E402

h.BUILD = QA.parent / "build" / "msvc-release"
target = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(target, run_name="__main__")

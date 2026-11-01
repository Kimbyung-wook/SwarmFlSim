import copy
import json
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture(scope="session")
def _example_doc() -> dict:
    return json.loads((EXAMPLES / "korea_east_strike_20.json").read_text(encoding="utf-8"))


@pytest.fixture
def doc(_example_doc) -> dict:
    """예제 시나리오의 사본. 시험마다 고쳐 쓴다"""
    return copy.deepcopy(_example_doc)

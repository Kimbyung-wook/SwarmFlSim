"""플러그인 로딩 (IMP-AGT-005, PRP-BHV-001, REQ-BHV-004).

entry point 그룹 swarm.ma / swarm.fa에서 등록명으로 클래스를 찾는다.
시험이나 내장 실행은 extra_ma / extra_fa로 같은 이름을 덮어쓸 수 있다.
"""

from collections.abc import Mapping
from importlib.metadata import entry_points

from swarm_api import FA_ENTRY_POINT_GROUP, MA_ENTRY_POINT_GROUP

DEFAULT_FA = "default"
DEFAULT_MA = "hold"


class PluginRegistry:
    def __init__(self, extra_ma: Mapping[str, type] | None = None, extra_fa: Mapping[str, type] | None = None,
                 use_entry_points: bool = True) -> None:
        self._extra = {MA_ENTRY_POINT_GROUP: dict(extra_ma or {}), FA_ENTRY_POINT_GROUP: dict(extra_fa or {})}
        self._use_eps = use_entry_points
        self._cache: dict[tuple[str, str], type | None] = {}

    def _find(self, group: str, name: str) -> type | None:
        if name in self._extra[group]:
            return self._extra[group][name]
        if (group, name) in self._cache:
            return self._cache[(group, name)]
        cls = None
        if self._use_eps:
            for ep in entry_points(group=group, name=name):
                cls = ep.load()
                break
        self._cache[(group, name)] = cls
        return cls

    def ma_class(self, name: str) -> type | None:
        return self._find(MA_ENTRY_POINT_GROUP, name or DEFAULT_MA)

    def fa_class(self, name: str) -> type | None:
        return self._find(FA_ENTRY_POINT_GROUP, name or DEFAULT_FA)

    def names(self, group: str) -> list[str]:
        found = set(self._extra[group])
        if self._use_eps:
            found.update(ep.name for ep in entry_points(group=group))
        return sorted(found)

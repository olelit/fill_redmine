from configs.project_config import ProjectConfig
from trackers.base import BaseTracker

_REGISTRY: dict[str, type[BaseTracker]] = {}


def register_tracker(cls: type[BaseTracker]) -> type[BaseTracker]:
    if not issubclass(cls, BaseTracker):
        raise TypeError("register_tracker ожидает класс BaseTracker")
    if not cls.kind:
        raise ValueError("У трекера не задан kind")
    if cls.kind in _REGISTRY:
        raise ValueError(f"Трекер {cls.kind} уже зарегистрирован")
    _REGISTRY[cls.kind] = cls
    return cls


def all_trackers() -> list[type[BaseTracker]]:
    return list(_REGISTRY.values())


def get_tracker_class(kind: str) -> type[BaseTracker] | None:
    return _REGISTRY.get(kind)


def build_tracker(kind: str, config: dict) -> BaseTracker | None:
    cls = get_tracker_class(kind)
    return cls(config) if cls is not None else None


def configured_trackers(project: ProjectConfig) -> list[BaseTracker]:
    result: list[BaseTracker] = []
    for cls in all_trackers():
        tracker = cls(project.trackers.get(cls.kind, {}))
        if tracker.is_configured():
            result.append(tracker)
    return result

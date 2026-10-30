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


def get_tracker_class(kind: str) -> type[BaseTracker] | None:
    return _REGISTRY.get(kind)

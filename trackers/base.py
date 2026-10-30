from abc import ABC, abstractmethod
from datetime import date

from dto.worklog_dto import WorklogDTO


class BaseTracker(ABC):
    kind: str = ""
    label: str = ""
    can_write: bool = False

    def __init__(self, config: dict) -> None:
        self.config = config or {}

    @abstractmethod
    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
        raise NotImplementedError

    def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
        raise NotImplementedError(
            f"Трекер {self.label} не поддерживает запись часов"
        )
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from dto.worklog_dto import WorklogDTO


@dataclass(frozen=True)
class TrackerField:
    key: str
    label: str
    kind: str = "text"
    required: bool = True
    placeholder: str = ""


class BaseTracker(ABC):
    kind: str = ""
    label: str = ""
    fields: tuple[TrackerField, ...] = ()
    can_read: bool = True
    can_write: bool = False

    def __init__(self, config: dict) -> None:
        self.config = config or {}

    def is_configured(self) -> bool:
        required = [field for field in self.fields if field.required]
        return bool(required) and all(
            self.config.get(field.key) not in (None, "")
            for field in required
        )

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        required = [field for field in cls.fields if field.required]
        filled = [
            field
            for field in required
            if config.get(field.key) not in (None, "")
        ]
        if not filled:
            return []

        errors: list[str] = []
        missing = [field.label for field in required if field not in filled]
        if missing:
            errors.append(f"{cls.label}: заполните {', '.join(missing)}")
            return errors

        for field in required:
            if field.kind == "int":
                try:
                    value = int(config[field.key])
                except (TypeError, ValueError):
                    errors.append(f"{cls.label}: {field.label} должно быть целым числом")
                    continue
                if value <= 0:
                    errors.append(f"{cls.label}: {field.label} должно быть больше нуля")
        return errors

    @abstractmethod
    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
        raise NotImplementedError

    def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
        raise NotImplementedError(
            f"Трекер {self.label} не поддерживает запись часов"
        )

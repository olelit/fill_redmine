from collections.abc import Callable
from dataclasses import dataclass, field

from configs.user_config import UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from dto.preview_dto import PreviewDTO
from imports.base_importer import BaseImporter
from imports.import_factory import create_importer
from services.preview_service import PreviewService


@dataclass
class PreparedImport:
    user: UserConfig
    importer: BaseImporter
    records: list[DateHoursDTO]
    preview: PreviewDTO


@dataclass
class ImportSummary:
    total: int
    errors: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class PrepareResult:
    items: list[PreparedImport] = field(default_factory=list)
    errors: list[PreviewDTO] = field(default_factory=list)


class ImportService:
    def __init__(self, log: Callable[[str], None] = print):
        self.log = log

    def prepare(self, users: list[UserConfig]) -> PrepareResult:
        result = PrepareResult()
        issue_info_cache: dict[int, IssueInfoDTO | None] = {}

        for user in users:
            importer = create_importer(user)
            if importer is None:
                message = f"неизвестный driver «{user.driver}»"
                self.log(f"{user.name}: {message}, пропуск")
                result.errors.append(self._error_preview(user, message))
                continue

            try:
                records = importer.create_record_list()
            except Exception as exc:
                message = f"ошибка получения записей: {exc}"
                self.log(f"{user.name}: {message}")
                result.errors.append(self._error_preview(user, message))
                continue

            if not records:
                self.log(f"{user.name}: нет записей")
                continue

            issue_info = PreviewService.get_issue_info(
                issue_info_cache=issue_info_cache,
                user=user,
            )
            preview = PreviewService.build_user_preview(
                user=user,
                records=records,
                issue_info=issue_info,
            )
            result.items.append(
                PreparedImport(
                    user=user,
                    importer=importer,
                    records=records,
                    preview=preview,
                )
            )

        return result

    @staticmethod
    def _error_preview(user: UserConfig, message: str) -> PreviewDTO:
        return PreviewService.build_user_preview(
            user=user,
            records=[],
            issue_info=None,
            error=message,
        )

    async def run(
        self,
        items: list[PreparedImport],
        progress_cb: Callable[[int, int, str], None] | None = None,
    ) -> ImportSummary:
        total = sum(len(item.records) for item in items)
        errors: list[tuple[str, str, str]] = []
        completed_base = 0

        for item in items:
            def on_progress(
                completed: int,
                item_total: int,
                base: int = completed_base,
                name: str = item.user.name,
            ) -> None:
                if progress_cb is not None:
                    progress_cb(base + completed, total, name)

            item_errors = await item.importer.handle(
                records=item.records,
                on_progress=on_progress if progress_cb is not None else None,
            )
            for spent_on, message in item_errors or []:
                errors.append((item.user.name, spent_on, message))
            completed_base += len(item.records)

        return ImportSummary(total=total, errors=errors)

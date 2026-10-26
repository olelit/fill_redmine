from collections.abc import Callable
from dataclasses import dataclass, field

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.import_action import ImportAction
from dto.issue_info_dto import IssueInfoDTO
from dto.preview_dto import PreviewDTO
from imports.base_importer import BaseImporter
from imports.import_factory import create_importer
from services.preview_service import PreviewService


@dataclass
class PreparedImport:
    project: ProjectConfig
    action: ImportAction
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

    def prepare(
        self, project: ProjectConfig, action: ImportAction
    ) -> PrepareResult:
        result = PrepareResult()
        try:
            importer = create_importer(project, action)
            records = importer.create_record_list()
        except Exception as exc:
            message = f"ошибка получения записей: {exc}"
            self.log(f"{project.name}: {message}")
            result.errors.append(self._error_preview(project, action, message))
            return result

        if not records:
            self.log(f"{project.name}: нет записей")
            return result

        issue_info_cache: dict[int, IssueInfoDTO | None] = {}
        issue_info = PreviewService.get_issue_info(issue_info_cache, project)
        preview = PreviewService.build_preview(
            project,
            action.value,
            records,
            issue_info,
        )
        result.items.append(
            PreparedImport(
                project=project,
                action=action,
                importer=importer,
                records=records,
                preview=preview,
            )
        )
        return result

    def prepare_many(
        self, projects: list[ProjectConfig], action: ImportAction
    ) -> PrepareResult:
        merged = PrepareResult()
        for project in projects:
            result = self.prepare(project, action)
            merged.items.extend(result.items)
            merged.errors.extend(result.errors)
        return merged

    @staticmethod
    def _error_preview(
        project: ProjectConfig, action: ImportAction, message: str
    ) -> PreviewDTO:
        return PreviewService.build_preview(
            project,
            action.value,
            [],
            None,
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
                name: str = item.project.name,
            ) -> None:
                if progress_cb is not None:
                    progress_cb(base + completed, total, name)

            item_errors = await item.importer.handle(
                records=item.records,
                on_progress=on_progress if progress_cb is not None else None,
            )
            for spent_on, message in item_errors or []:
                errors.append((item.project.name, spent_on, message))
            completed_base += len(item.records)

        return ImportSummary(total=total, errors=errors)

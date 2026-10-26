from unittest.mock import patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.import_action import ImportAction
from dto.issue_info_dto import IssueInfoDTO
from services.import_service import (
    ImportService,
    ImportSummary,
    PrepareResult,
    PreparedImport,
)
from services.preview_service import PreviewService


def make_project(name="Олег") -> ProjectConfig:
    return ProjectConfig(
        name=name,
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
                "comment": "development",
            }
        },
    )


def make_issue_info() -> IssueInfoDTO:
    return IssueInfoDTO(
        subject="Тема",
        url="http://redmine/issues/2682",
        author="Oleg",
        created_on="2026-10-01 10:00:00 UTC",
    )


class FakeImporter:
    def __init__(self, records=None, errors=None):
        self.records = records or []
        self.errors = errors or []
        self.create_calls = 0
        self.handle_calls = []
        self.progress_callbacks = []

    def create_record_list(self):
        self.create_calls += 1
        return self.records

    async def handle(self, records=None, on_progress=None):
        self.handle_calls.append(records)
        self.progress_callbacks.append(on_progress)
        if on_progress is not None:
            for completed in range(1, len(records) + 1):
                on_progress(completed, len(records))
        return list(self.errors)


def test_prepare_builds_preview(monkeypatch):
    importer = FakeImporter(records=[DateHoursDTO(date="2026-10-01", hours=8)])
    monkeypatch.setattr(
        "services.import_service.create_importer",
        lambda project, action: importer,
    )
    monkeypatch.setattr(
        "services.import_service.PreviewService.get_issue_info",
        lambda cache, project: make_issue_info(),
    )

    result = ImportService(log=lambda message: None).prepare(
        make_project(), ImportAction.REDMINE_FILL
    )

    assert len(result.items) == 1
    assert result.errors == []
    assert result.items[0].project.name == "Олег"
    assert result.items[0].action is ImportAction.REDMINE_FILL
    assert result.items[0].preview.project_name == "Олег"


def test_prepare_reports_importer_error(monkeypatch):
    class BrokenImporter:
        def create_record_list(self):
            raise RuntimeError("network down")

    monkeypatch.setattr(
        "services.import_service.create_importer",
        lambda project, action: BrokenImporter(),
    )

    result = ImportService(log=lambda message: None).prepare(
        make_project(), ImportAction.REDMINE_FILL
    )

    assert result.items == []
    assert len(result.errors) == 1
    assert "network down" in result.errors[0].error


def test_prepare_skips_empty_records(monkeypatch):
    importer = FakeImporter(records=[])
    monkeypatch.setattr(
        "services.import_service.create_importer",
        lambda project, action: importer,
    )

    result = ImportService(log=lambda message: None).prepare(
        make_project(), ImportAction.REDMINE_FILL
    )

    assert result.items == []
    assert result.errors == []


def test_prepare_many_merges(monkeypatch):
    importer = FakeImporter(records=[DateHoursDTO(date="2026-10-01", hours=8)])
    monkeypatch.setattr(
        "services.import_service.create_importer",
        lambda project, action: importer,
    )
    monkeypatch.setattr(
        "services.import_service.PreviewService.get_issue_info",
        lambda cache, project: None,
    )

    result = ImportService(log=lambda message: None).prepare_many(
        [make_project("A"), make_project("B")], ImportAction.REDMINE_FILL
    )

    assert [item.project.name for item in result.items] == ["A", "B"]


@pytest.mark.asyncio
async def test_run_reports_progress_and_errors():
    project = make_project()
    importer = FakeImporter(
        records=[
            DateHoursDTO(date="2026-10-01", hours=8),
            DateHoursDTO(date="2026-10-02", hours=8),
        ],
        errors=[("2026-10-01", "500 error")],
    )
    items = [
        PreparedImport(
            project=project,
            action=ImportAction.REDMINE_FILL,
            importer=importer,
            records=importer.records,
            preview=PreviewService.build_preview(
                project, "redmine_fill", importer.records, None
            ),
        )
    ]
    progress = []

    summary = await ImportService(log=lambda message: None).run(
        items,
        progress_cb=lambda completed, total, name: progress.append(
            (completed, total, name)
        ),
    )

    assert progress == [(1, 2, "Олег"), (2, 2, "Олег")]
    assert summary == ImportSummary(
        total=2, errors=[("Олег", "2026-10-01", "500 error")]
    )


@pytest.mark.asyncio
async def test_run_without_items_returns_empty_summary():
    summary = await ImportService(log=lambda message: None).run([])

    assert summary.total == 0
    assert summary.errors == []

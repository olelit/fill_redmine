import pytest

from configs.user_config import MANUAL, UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from services.import_service import ImportService, PreparedImport
from services.preview_service import PreviewService


def make_user(name="Олег") -> UserConfig:
    return UserConfig(
        is_enable=True,
        name=name,
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver=MANUAL,
        youtrack_access_token="",
        exclude_dates=[],
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
        self.records = records if records is not None else []
        self.errors = errors if errors is not None else []
        self.create_calls = 0
        self.handle_calls = []

    def create_record_list(self):
        self.create_calls += 1
        return self.records

    async def handle(self, records=None, on_progress=None):
        self.handle_calls.append(records)
        if on_progress is not None:
            for completed in range(1, len(records) + 1):
                on_progress(completed, len(records))
        return list(self.errors)


class TestImportServicePrepare:
    def test_prepare_builds_preview_without_refetching_records(self, monkeypatch):
        service = ImportService(log=lambda message: None)
        records = [DateHoursDTO(date="2026-10-01", hours=8)]
        importer = FakeImporter(records=records)
        monkeypatch.setattr("services.import_service.create_importer", lambda user: importer)
        monkeypatch.setattr(
            "services.import_service.PreviewService.get_issue_info",
            lambda issue_info_cache, user: make_issue_info(),
        )

        items = service.prepare([make_user()])

        assert len(items) == 1
        assert importer.create_calls == 1
        assert items[0].preview.user_name == "Олег"
        assert items[0].preview.issue_subject == "Тема"
        assert items[0].records == records

    def test_prepare_skips_user_when_importer_missing(self, monkeypatch):
        logs = []
        service = ImportService(log=logs.append)
        monkeypatch.setattr("services.import_service.create_importer", lambda user: None)

        items = service.prepare([make_user()])

        assert items == []
        assert any("driver" in message for message in logs)

    def test_prepare_skips_user_without_records(self, monkeypatch):
        service = ImportService(log=lambda message: None)
        importer = FakeImporter(records=[])
        monkeypatch.setattr("services.import_service.create_importer", lambda user: importer)

        assert service.prepare([make_user()]) == []
        assert importer.create_calls == 1

    def test_prepare_logs_and_skips_fetch_errors(self, monkeypatch):
        logs = []

        class BrokenImporter:
            def create_record_list(self):
                raise RuntimeError("network down")

        monkeypatch.setattr(
            "services.import_service.create_importer", lambda user: BrokenImporter()
        )

        items = ImportService(log=logs.append).prepare([make_user()])

        assert items == []
        assert any("network down" in message for message in logs)


class TestImportServiceRun:
    @pytest.mark.asyncio
    async def test_run_reports_global_progress_and_collects_errors(self):
        user_one = make_user(name="Первый")
        user_two = make_user(name="Второй")
        importer_one = FakeImporter(
            records=[
                DateHoursDTO(date="2026-10-01", hours=8),
                DateHoursDTO(date="2026-10-02", hours=8),
            ]
        )
        importer_two = FakeImporter(
            records=[DateHoursDTO(date="2026-10-01", hours=4)],
            errors=[("2026-10-01", "500 error")],
        )
        service = ImportService(log=lambda message: None)
        progress = []

        items = [
            PreparedImport(
                user=user_one,
                importer=importer_one,
                records=importer_one.records,
                preview=PreviewService.build_user_preview(user_one, importer_one.records, None),
            ),
            PreparedImport(
                user=user_two,
                importer=importer_two,
                records=importer_two.records,
                preview=PreviewService.build_user_preview(user_two, importer_two.records, None),
            ),
        ]

        summary = await service.run(
            items,
            progress_cb=lambda completed, total, name: progress.append(
                (completed, total, name)
            ),
        )

        assert progress == [(1, 3, "Первый"), (2, 3, "Первый"), (3, 3, "Второй")]
        assert summary.total == 3
        assert summary.errors == [("Второй", "2026-10-01", "500 error")]
        assert importer_one.handle_calls == [importer_one.records]
        assert importer_two.handle_calls == [importer_two.records]

    @pytest.mark.asyncio
    async def test_run_without_items_returns_empty_summary(self):
        summary = await ImportService(log=lambda message: None).run([])

        assert summary.total == 0
        assert summary.errors == []

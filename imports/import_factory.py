from configs.project_config import ProjectConfig
from dto.import_action import ImportAction
from imports.base_importer import BaseImporter
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter


def create_importer(
    project: ProjectConfig, action: ImportAction
) -> BaseImporter:
    if action is ImportAction.REDMINE_FILL:
        return ManualImporter(project)
    if action is ImportAction.YOUTRACK_TRANSFER:
        return YoutrackImporter(project)
    raise ValueError(f"Неизвестное действие: {action}")

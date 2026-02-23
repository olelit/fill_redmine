from configs.user_config import UserConfig
from imports.base_importer import BaseImporter
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter


def create_importer(user: UserConfig) -> BaseImporter | None:
    if user.is_manual():
        return ManualImporter(user)
    elif user.is_youtrack():
        return YoutrackImporter(user)
    return None
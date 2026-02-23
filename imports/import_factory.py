from configs.users import UserConfig
from imports.base_importer import BaseImporter
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter

MANUAL = 'manual'
YOUTRACK = 'youtrack'


def create_importer(user: UserConfig) -> BaseImporter | None:
    if user.driver == MANUAL:
        return ManualImporter(user)
    elif user.driver == YOUTRACK:
        return YoutrackImporter(user)
    return None
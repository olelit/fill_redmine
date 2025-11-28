import os

from dotenv import load_dotenv

from imports.base_importer import BaseImporter
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter

MANUAL = 'manual'
YOUTRACK = 'youtrack'

def create_importer(postfix : int) -> BaseImporter | None:
    source = os.getenv(f"SOURCE_{postfix}")

    if source == MANUAL:
        return ManualImporter(postfix)
    elif source == YOUTRACK:
        return YoutrackImporter(postfix)
    return None
import os

from dotenv import load_dotenv

from imports.base_importer import BaseImporter
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter

load_dotenv()

MANUAL = 'manual'
YOUTRACK = 'youtrack'

def create_importer(postfix : int) -> BaseImporter | None:
    source = os.getenv('SOURCE')

    if source == MANUAL:
        return ManualImporter(postfix)
    elif source == YOUTRACK:
        return YoutrackImporter(postfix)
    return None
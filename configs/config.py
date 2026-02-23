import os

from dotenv import load_dotenv

load_dotenv()


class Config:

    @staticmethod
    def get_redmine_base_url() -> str:
        return os.getenv("REDMINE_BASE_URL")

    @staticmethod
    def get_youtrack_base_url() -> str:
        return os.getenv("YOUTRACK_BASE_URL")

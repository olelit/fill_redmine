import os

from dotenv import load_dotenv

from configs.iterable_config_dto import IterableConfigDTO

load_dotenv()


class Config:

    @staticmethod
    def get_redmine_base_url() -> str:
        return os.getenv("REDMINE_BASE_URL")

    @staticmethod
    def get_youtrack_base_url() -> str:
        return os.getenv("YOUTRACK_BASE_URL")

    @staticmethod
    def get_iterable_source_env(postfix: int) -> str:
        return os.getenv(f"SOURCE_{postfix}")

    @staticmethod
    def get_iterable_import_env(postfix: int) -> "IterableConfigDTO":
        suffix = str(postfix)

        return IterableConfigDTO(
            os.getenv(f"REDMINE_API_KEY_{suffix}"),
            int(os.getenv(f"USER_ID_{suffix}")),
            int(os.getenv(f"ACTIVITY_ID_{suffix}")),
            os.getenv(f"COMMENT_{suffix}"),
            int(os.getenv(f"ISSUE_ID_{suffix}")),
            os.getenv(f"SOURCE_{suffix}"),
            os.getenv(f"YOUTRACK_ACCESS_TOKEN_{suffix}"),
            os.getenv(f"EXCLUDE_DATES_{suffix}"),
        )

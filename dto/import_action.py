from enum import Enum


class ImportAction(str, Enum):
    REDMINE_FILL = "redmine_fill"
    YOUTRACK_TRANSFER = "youtrack_transfer"

    @property
    def label(self) -> str:
        labels = {
            self.REDMINE_FILL: "Redmine",
            self.YOUTRACK_TRANSFER: "YouTrack → Redmine",
        }
        return labels[self]

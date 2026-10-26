from dataclasses import dataclass


@dataclass
class WorklogDTO:
    date: str
    hours: float
    description: str = ""
    issue: str = ""
    source: str = ""

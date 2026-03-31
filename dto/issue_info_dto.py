from dataclasses import dataclass


@dataclass
class IssueInfoDTO:
    subject: str
    url: str
    author: str
    created_on: str

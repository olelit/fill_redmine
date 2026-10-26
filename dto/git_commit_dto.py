from dataclasses import dataclass


@dataclass
class GitCommitDTO:
    hash: str
    author_name: str
    author_email: str
    date: str
    subject: str
    body: str = ""

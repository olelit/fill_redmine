import subprocess
from datetime import date
from pathlib import Path

from dto.git_commit_dto import GitCommitDTO

FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"


class GitError(RuntimeError):
    pass


class GitClient:
    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).expanduser()

    def _run(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise GitError(message or "git command failed")
        return result.stdout

    def validate(self) -> None:
        if not self.repo_path.exists():
            raise GitError(f"Путь к репозиторию не найден: {self.repo_path}")
        try:
            inside = self._run("rev-parse", "--is-inside-work-tree").strip()
        except GitError as exc:
            raise GitError("Это не git-репозиторий") from exc
        if inside != "true":
            raise GitError("Это не git-репозиторий")

    def get_config_email(self) -> str:
        self.validate()
        return self._run("config", "user.email").strip()

    def list_commits(
        self, email: str, start: date, end: date
    ) -> list[GitCommitDTO]:
        email = email.strip()
        if not email:
            raise GitError("Не задан email автора коммитов")
        self.validate()

        output = self._run(
            "log",
            "--all",
            f"--author={email}",
            f"--since={start.isoformat()}T00:00:00",
            f"--until={end.isoformat()}T23:59:59",
            "--date=iso-strict",
            "--pretty=format:"
            f"%H{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%ae{FIELD_SEPARATOR}"
            f"%ad{FIELD_SEPARATOR}%s{FIELD_SEPARATOR}%b{RECORD_SEPARATOR}",
        )

        commits: dict[str, GitCommitDTO] = {}
        for raw_record in output.split(RECORD_SEPARATOR):
            record = raw_record.strip("\n")
            if not record:
                continue
            parts = record.split(FIELD_SEPARATOR, maxsplit=5)
            if len(parts) != 6:
                continue
            commit_hash, author_name, author_email, authored_at, subject, body = parts
            if author_email.strip().lower() != email.lower():
                continue
            commits[commit_hash] = GitCommitDTO(
                hash=commit_hash,
                author_name=author_name,
                author_email=author_email,
                date=authored_at,
                subject=subject,
                body=body.strip(),
            )

        return sorted(commits.values(), key=lambda item: item.date, reverse=True)

import re
import subprocess
from datetime import date, datetime
from pathlib import Path

from dto.git_commit_dto import GitCommitDTO

FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"


class GitError(RuntimeError):
    pass


class GitClient:
    def __init__(self, repo_path: str | Path):
        self.raw_path = str(repo_path)
        self.repo_path = Path(self.raw_path).expanduser()

    def _run(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), *args],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitError("Команда git превысила таймаут") from exc
        except OSError as exc:
            raise GitError(f"Не удалось выполнить git: {exc}") from exc
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise GitError(message or "git command failed")
        return result.stdout

    def validate(self) -> None:
        if not self.raw_path.strip():
            raise GitError("Не задан путь к git-репозиторию")
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

        # Git treats --author as a regex, so the email must be escaped. Extended
        # regex syntax is required: in the default basic syntax "\+" means
        # "one or more g", which would silently drop addresses like
        # "name+tag@example.com".
        author_pattern = re.escape(email)
        output = self._run(
            "log",
            "--all",
            "--extended-regexp",
            f"--author={author_pattern}",
            "--date=iso-strict",
            "--pretty=format:"
            f"%H{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%ae{FIELD_SEPARATOR}"
            f"%ad{FIELD_SEPARATOR}%s{FIELD_SEPARATOR}%b{RECORD_SEPARATOR}",
        )

        commits: dict[str, tuple[datetime, GitCommitDTO]] = {}
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
            try:
                authored_dt = datetime.fromisoformat(authored_at)
            except ValueError:
                continue
            # Period filtering uses the author date (what the report shows), not
            # the committer date that --since/--until would apply.
            if not start <= authored_dt.date() <= end:
                continue
            commits[commit_hash] = (
                authored_dt,
                GitCommitDTO(
                    hash=commit_hash,
                    author_name=author_name,
                    author_email=author_email,
                    date=authored_at,
                    subject=subject,
                    body=body.strip(),
                ),
            )

        return [
            commit
            for _, commit in sorted(
                commits.values(), key=lambda item: item[0], reverse=True
            )
        ]

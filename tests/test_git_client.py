import os
import subprocess
from datetime import date

import pytest

from clients.git_client import GitClient, GitError


def run_git(repo, *args, env=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.name", "Oleg")
    run_git(path, "config", "user.email", "oleg@example.com")
    return path


def commit_with_dates(
    repo,
    message,
    author_date,
    committer_date,
    email="oleg@example.com",
):
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = author_date
    env["GIT_COMMITTER_DATE"] = committer_date
    env["GIT_AUTHOR_EMAIL"] = email
    env["GIT_COMMITTER_EMAIL"] = email
    (repo / "file.txt").write_text(message)
    run_git(repo, "add", "file.txt")
    run_git(repo, "commit", "-m", message, env=env)


def commit(repo, message, author_date, email="oleg@example.com"):
    commit_with_dates(repo, message, author_date, author_date, email)


def test_lists_commits_from_all_branches(repo):
    commit(repo, "main commit", "2026-10-01T10:00:00+00:00")
    run_git(repo, "checkout", "-b", "feature")
    commit(repo, "feature commit", "2026-10-02T10:00:00+00:00")
    run_git(repo, "checkout", "main")

    commits = GitClient(repo).list_commits(
        "oleg@example.com", date(2026, 10, 1), date(2026, 10, 5)
    )

    assert {commit.subject for commit in commits} == {
        "main commit",
        "feature commit",
    }


def test_filters_by_author_email(repo):
    commit(repo, "mine", "2026-10-01T10:00:00+00:00")
    commit(
        repo,
        "theirs",
        "2026-10-02T10:00:00+00:00",
        email="other@example.com",
    )

    commits = GitClient(repo).list_commits(
        "oleg@example.com", date(2026, 10, 1), date(2026, 10, 5)
    )

    assert [commit.subject for commit in commits] == ["mine"]


def test_filters_by_period(repo):
    commit(repo, "old", "2026-09-01T10:00:00+00:00")
    commit(repo, "inside", "2026-10-02T10:00:00+00:00")

    commits = GitClient(repo).list_commits(
        "oleg@example.com", date(2026, 10, 1), date(2026, 10, 5)
    )

    assert [commit.subject for commit in commits] == ["inside"]


def test_email_with_plus_is_matched_exactly(repo):
    commit(
        repo,
        "plus alias",
        "2026-10-02T10:00:00+00:00",
        email="oleg+work@example.com",
    )

    commits = GitClient(repo).list_commits(
        "oleg+work@example.com", date(2026, 10, 1), date(2026, 10, 5)
    )

    assert [commit.subject for commit in commits] == ["plus alias"]


def test_filters_by_author_date_not_committer_date(repo):
    commit_with_dates(
        repo,
        "rebased",
        author_date="2026-10-02T10:00:00+00:00",
        committer_date="2026-09-01T10:00:00+00:00",
    )

    commits = GitClient(repo).list_commits(
        "oleg@example.com", date(2026, 10, 1), date(2026, 10, 5)
    )

    assert [commit.subject for commit in commits] == ["rebased"]


def test_get_config_email(repo):
    assert GitClient(repo).get_config_email() == "oleg@example.com"


def test_empty_email_raises(repo):
    with pytest.raises(GitError, match="email"):
        GitClient(repo).list_commits("", date(2026, 10, 1), date(2026, 10, 2))


def test_not_a_repository_raises(tmp_path):
    with pytest.raises(GitError, match="git"):
        GitClient(tmp_path).validate()


def test_empty_repo_path_raises():
    with pytest.raises(GitError, match="Не задан путь"):
        GitClient("").validate()
    with pytest.raises(GitError, match="Не задан путь"):
        GitClient("   ").validate()

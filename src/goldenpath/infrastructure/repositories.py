"""Create a new service's Git repository and publish it to a local bare remote (standing in for `gh repo create`)."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

AUTHOR = ("platform-bot", "platform-bot@example.test")


def _git(directory: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["git", "-c", f"user.name={AUTHOR[0]}", "-c", f"user.email={AUTHOR[1]}", *args],  # noqa: S607
        cwd=directory,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


class GitRepositories:
    """`create` runs `git init`, commits everything, creates `<remotes>/<name>.git` and pushes `main` to it."""

    def __init__(self, remotes: Path) -> None:
        """`remotes` is the folder that holds the bare repositories."""
        self._remotes = remotes

    def create(self, directory: Path, name: str, message: str) -> str:
        """Publish the repository; return the commit id."""
        remote = self._remotes / f"{name}.git"
        remote.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)  # noqa: S603, S607
        _git(directory, "init", "-q", "-b", "main")
        _git(directory, "add", "-A")
        _git(directory, "commit", "-q", "-m", message)
        _git(directory, "remote", "add", "origin", str(remote))
        _git(directory, "push", "-q", "origin", "main")
        return _git(directory, "rev-parse", "HEAD")


def commits_since(directory: Path, base: str | None) -> Sequence[str]:
    """Short ids of the commits after `base` (all of them when `base` is None), oldest first."""
    spec = f"{base}..HEAD" if base else "HEAD"
    return _git(directory, "rev-list", "--reverse", "--abbrev-commit", spec).split()

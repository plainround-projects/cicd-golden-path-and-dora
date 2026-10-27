"""The template, generated for three imaginary teams, with real git and real make: the repositories it creates work."""

import subprocess
from pathlib import Path

import pytest

from goldenpath.application.generate_service import ServiceGenerator
from goldenpath.infrastructure.auditor import RepositoryAuditor
from goldenpath.infrastructure.catalog_files import FileCatalog
from goldenpath.infrastructure.repositories import GitRepositories, commits_since
from goldenpath.infrastructure.template_renderer import FileTemplateRenderer

ROOT = Path(__file__).resolve().parents[2]
TEAMS = [("orders", "team-orders"), ("billing", "team-billing"), ("search", "team-search")]


def make_generator(workdir: Path) -> tuple[ServiceGenerator, FileCatalog]:
    catalog = FileCatalog(ROOT / "catalog" / "teams.yaml", workdir / "catalog")
    generator = ServiceGenerator(
        FileTemplateRenderer(ROOT / "template"),
        catalog,
        GitRepositories(workdir / "remotes"),
        RepositoryAuditor(catalog),
        "a" * 40,
    )
    return generator, catalog


@pytest.mark.parametrize(("name", "owner"), TEAMS)
def test_a_service_for_each_team_is_generated_and_its_own_ci_passes(tmp_path, name, owner):
    generator, catalog = make_generator(tmp_path)
    service = generator.generate(name, owner, tmp_path / "services" / name, "https://wiki.example.com/runbooks")
    done = subprocess.run(["make", "--no-print-directory", "ci"], cwd=service.directory, capture_output=True, text=True, check=False)  # noqa: S603, S607
    assert done.returncode == 0, done.stdout + done.stderr
    assert "OK" in done.stderr
    assert [entry.name for entry in catalog.entries()] == [name]


def test_the_generated_repository_is_published_and_its_commit_is_on_the_remote(tmp_path):
    generator, _ = make_generator(tmp_path)
    service = generator.generate("orders", "team-orders", tmp_path / "services" / "orders", "https://wiki.example.com/runbooks")
    remote = tmp_path / "remotes" / "orders.git"
    head = subprocess.run(["git", "rev-parse", "main"], cwd=remote, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603, S607
    assert head == service.commit
    assert len(commits_since(service.directory, None)) == 1


def test_no_generated_file_holds_a_long_lived_credential_or_a_placeholder(tmp_path):
    generator, catalog = make_generator(tmp_path)
    service = generator.generate("search", "team-search", tmp_path / "services" / "search", "https://wiki.example.com/runbooks")
    assert RepositoryAuditor(catalog).audit(service.directory) == []
    assert "team-search" in (service.directory / "README.md").read_text()

from pathlib import Path

import pytest

from goldenpath.infrastructure.catalog_files import FileCatalog
from goldenpath.infrastructure.template_renderer import FileTemplateRenderer
from goldenpath.interfaces import cli

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = str(ROOT / "data" / "events-sample.csv")


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOLDENPATH_WORKDIR", str(tmp_path / "local"))
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)


def test_the_metrics_table_for_the_sample_has_the_lessons_numbers(capsys):
    assert cli.main(["metrics", "--csv", SAMPLE]) == cli.EXIT_OK
    rows = {line.split()[0]: line.split() for line in capsys.readouterr().out.splitlines()[1:]}
    assert rows["orders"][1:7] == ["4", "4.0", "h", "25%", "30", "min"]
    assert rows["billing"][1:7] == ["1", "62.0", "h", "100%", "240", "min"]


def test_the_weekly_table_prints_one_block_per_week(capsys):
    assert cli.main(["metrics", "--csv", SAMPLE, "--weekly"]) == cli.EXIT_OK
    assert "week 1" in capsys.readouterr().out


def test_a_lead_time_is_traced_to_its_two_events(capsys):
    assert cli.main(["trace", "orders", "a5", "--csv", SAMPLE]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "commit event:  2026-09-04 16:00  orders  commit  a5" in out
    assert "deploy event:  2026-09-07 10:00  orders  deploy  d4:a5" in out
    assert "lead time:     66.0 h" in out


def test_tracing_an_unknown_commit_exits_with_the_usage_code(capsys):
    assert cli.main(["trace", "orders", "zzz", "--csv", SAMPLE]) == cli.EXIT_USAGE
    assert "no commit" in capsys.readouterr().err


def test_every_deployment_is_listed_with_its_commits(capsys):
    assert cli.main(["deployments", "billing", "--csv", SAMPLE]) == cli.EXIT_OK
    assert "e1  commits: b1, b2, b3, b4" in capsys.readouterr().out


def test_a_person_as_owner_is_refused_with_the_usage_code(capsys):
    assert cli.main(["new-service", "orders", "alice"]) == cli.EXIT_USAGE
    assert "not a person" in capsys.readouterr().err


def test_a_service_is_generated_audited_and_listed(capsys):
    assert cli.main(["new-service", "orders", "team-orders"]) == cli.EXIT_OK
    assert "conforms to the golden path contract" in capsys.readouterr().out
    assert cli.main(["catalog"]) == cli.EXIT_OK
    assert "orders" in capsys.readouterr().out


def test_the_audit_command_passes_a_generated_repository_and_fails_a_tampered_one(tmp_path, capsys):
    repo = tmp_path / "repo"
    FileTemplateRenderer(ROOT / "template").render(
        repo,
        {"__NAME__": "orders", "__OWNER__": "team-orders", "__RUNBOOK__": "https://x/r", "__PLATFORM_REF__": "f" * 40},
    )
    assert cli.main(["audit", str(repo)]) == cli.EXIT_OK
    workflow = repo / ".github" / "workflows" / "ci.yml"
    workflow.write_text(workflow.read_text().replace("      - run: make verify\n", ""))
    assert cli.main(["audit", str(repo)]) == cli.EXIT_FAILED
    assert "GP-VERIFY" in capsys.readouterr().out


def test_emitting_to_a_collector_that_is_not_running_exits_with_the_failure_code(monkeypatch, capsys):
    monkeypatch.setenv("COLLECTOR_URL", "http://127.0.0.1:1")
    assert cli.main(["emit", "commit", "orders", "a1"]) == cli.EXIT_FAILED
    assert "could not be reached" in capsys.readouterr().err


def test_a_bad_environment_value_exits_with_the_usage_code(monkeypatch, capsys):
    monkeypatch.setenv("COLLECTOR_PORT", "abc")
    assert cli.main(["catalog"]) == cli.EXIT_USAGE
    assert "COLLECTOR_PORT" in capsys.readouterr().err


def test_the_collector_refuses_to_start_without_a_token(monkeypatch, capsys):
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
    monkeypatch.delenv("COLLECTOR_TOKEN", raising=False)
    assert cli.main(["collector"]) == cli.EXIT_USAGE
    assert "COLLECTOR_TOKEN" in capsys.readouterr().err


def test_the_parser_requires_a_command():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_the_file_catalog_is_empty_before_any_service_exists(tmp_path):
    assert FileCatalog(ROOT / "catalog" / "teams.yaml", tmp_path / "none").entries() == []

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from goldenpath.domain import metrics, rules, simulation
from goldenpath.domain.catalog import CatalogEntry, from_mapping, validate
from goldenpath.domain.errors import InvalidCatalogEntryError
from goldenpath.infrastructure.auditor import load_workflow

ROOT = Path(__file__).resolve().parents[3]
TEAMS = frozenset({"team-orders", "team-platform"})


def entry(**changes: str) -> CatalogEntry:
    base = {
        "name": "orders",
        "owner": "team-orders",
        "lifecycle": "production",
        "runbook": "https://wiki.example.com/r/orders",
        "slo": "99.9%",
    }
    return CatalogEntry(**{**base, **changes})


def test_a_valid_entry_is_returned_unchanged():
    assert validate(entry(), TEAMS) == entry()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"owner": "alice"}, "not a person"),
        ({"owner": "team-ghost"}, "not a registered team"),
        ({"name": "Orders!"}, "name must be"),
        ({"lifecycle": "forever"}, "lifecycle"),
        ({"runbook": "http://insecure"}, "https"),
        ({"slo": " "}, "slo"),
    ],
)
def test_an_entry_that_breaks_the_contract_names_the_broken_rule(changes, message):
    with pytest.raises(InvalidCatalogEntryError, match=message):
        validate(entry(**changes), TEAMS)


def test_a_mapping_with_a_missing_key_names_it():
    with pytest.raises(InvalidCatalogEntryError, match="'slo'"):
        from_mapping({"name": "a1", "owner": "team-orders", "lifecycle": "production", "runbook": "https://x"})


def template_workflow() -> dict[str, Any]:
    return load_workflow((ROOT / "template" / ".github" / "workflows" / "ci.yml").read_text())


def codes(findings: list[rules.Finding]) -> set[str]:
    return {finding.code for finding in findings}


def test_the_templates_workflow_keeps_every_rule():
    assert rules.check_workflow(template_workflow()) == []


def test_removing_the_signing_step_is_found():
    document = template_workflow()
    document["jobs"]["release"]["steps"] = [
        s for s in document["jobs"]["release"]["steps"] if s.get("run") != "make sign"
    ]
    assert "GP-SIGN" in codes(rules.check_workflow(document))


def test_removing_verification_is_found():
    document = template_workflow()
    document["jobs"]["release"]["steps"] = [
        s for s in document["jobs"]["release"]["steps"] if s.get("run") != "make verify"
    ]
    assert "GP-VERIFY" in codes(rules.check_workflow(document))


def test_dropping_the_identity_token_permission_is_found():
    document = template_workflow()
    del document["jobs"]["release"]["permissions"]["id-token"]
    assert "GP-OIDC" in codes(rules.check_workflow(document))


def test_granting_the_identity_token_to_the_whole_workflow_is_found():
    document = template_workflow()
    document["permissions"]["id-token"] = "write"
    assert "GP-PERMS" in codes(rules.check_workflow(document))


@pytest.mark.parametrize("reference", ["actions/checkout@v4", "actions/checkout@main", "actions/checkout@" + "a" * 39])
def test_an_action_not_pinned_to_a_full_commit_is_found(reference):
    document = template_workflow()
    document["jobs"]["lint"]["steps"][0]["uses"] = reference
    assert "GP-PIN" in codes(rules.check_workflow(document))


def test_a_moving_image_tag_is_found():
    document = template_workflow()
    document["jobs"]["lint"]["steps"].append({"run": "docker run python:latest"})
    assert "GP-MOVING" in codes(rules.check_workflow(document))


def protection() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((ROOT / "template" / "protection.json").read_text())
    return payload


def test_the_templates_protection_keeps_every_rule():
    assert rules.check_protection(protection()) == []


def test_protection_that_weakens_a_rule_is_found():
    weak = protection()
    weak["required_status_checks"]["contexts"] = ["lint"]
    weak["required_status_checks"]["strict"] = False
    weak["enforce_admins"] = False
    weak["required_pull_request_reviews"] = None
    assert codes(rules.check_protection(weak)) == {"GP-CHECKS", "GP-STRICT", "GP-ADMINS", "GP-PR"}


@pytest.mark.parametrize(
    "text",
    [
        "key = AKIAABCDEFGHIJKLMNOP",
        "aws_secret_access_key = abc123",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----",
        "token: ghp_" + "a" * 36,
        "password: ${{ secrets.DEPLOY_PASSWORD }}",
        "aws: ${{ secrets.AWS_ACCESS_KEY_ID }}",
    ],
)
def test_what_a_long_lived_credential_looks_like_is_found(text):
    assert codes(rules.scan_for_credentials({"deploy.yml": text})) == {"GP-SECRET"}


def test_a_clean_file_has_no_credential_finding():
    assert rules.scan_for_credentials({"a.py": "print('hello')", "ci.yml": "id-token: write"}) == []


def test_a_leftover_placeholder_is_found():
    assert codes(rules.unreplaced_placeholders({"README.md": "# __NAME__"})) == {"GP-PLACEHOLDER"}
    assert rules.unreplaced_placeholders({"a.py": "__init__ and __main__"}) == []


def test_the_summary_says_conforms_or_lists_codes():
    assert rules.summarize([]) == "conforms to the golden path contract"
    assert "GP-SIGN" in rules.summarize([rules.Finding("GP-SIGN", "signed artifacts", "no step signs")])


def test_the_catalog_file_of_teams_lists_a_team_for_each_demo_service():
    teams = set(yaml.safe_load((ROOT / "catalog" / "teams.yaml").read_text())["teams"])
    assert {"team-orders", "team-billing", "team-search"} <= teams


def test_the_same_seed_gives_the_same_month():
    assert simulation.simulate(7) == simulation.simulate(7)
    assert simulation.simulate(7) != simulation.simulate(8)


def test_the_simulation_covers_the_four_event_types_for_three_teams():
    events = simulation.simulate(7)
    assert {event.service for event in events} == {"orders", "search", "billing"}
    assert {event.type.value for event in events} == {"commit", "deploy", "failed", "recovered"}


def monthly(seed: int) -> dict[str, metrics.ServiceMetrics]:
    events = simulation.simulate(seed)
    start, end = metrics.window_of(events)
    return {name: metrics.compute(events, name, start, end) for name in metrics.services(events)}


def known(value: float | None) -> float:
    assert value is not None
    return value


def test_small_changes_beat_the_weekly_batch_on_all_four_metrics_for_the_default_seed():
    table = monthly(7)
    small, batch = table["orders"], table["billing"]
    assert small.deploys_per_week > batch.deploys_per_week * 3
    assert known(small.median_lead_time_hours) < known(batch.median_lead_time_hours) / 5
    assert known(small.change_fail_rate) < known(batch.change_fail_rate)
    assert known(small.median_recovery_minutes) < known(batch.median_recovery_minutes) / 2


def test_the_pattern_holds_across_seeds_not_just_for_one():
    compared = 0
    for seed in range(20):
        small, batch = monthly(seed)["orders"], monthly(seed)["billing"]
        assert known(small.median_lead_time_hours) < known(batch.median_lead_time_hours)
        assert small.deploys_per_week > batch.deploys_per_week
        # a team that deploys once a week may see no failure in a month: then there is no recovery time to compare
        if small.median_recovery_minutes is not None and batch.median_recovery_minutes is not None:
            compared += 1
            assert small.median_recovery_minutes < batch.median_recovery_minutes
    assert compared >= 10


def test_the_weekly_batch_team_deploys_only_on_fridays():
    events = simulation.simulate(7)
    assert {e.ts.weekday() for e in events if e.service == "billing" and e.type.value == "deploy"} == {4}

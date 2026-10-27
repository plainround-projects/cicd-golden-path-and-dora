from datetime import UTC, datetime, timedelta

import pytest

from goldenpath.domain import metrics
from goldenpath.domain.errors import InvalidEventError, UnknownCommitError
from goldenpath.domain.events import Event, EventType, format_deploy_ref, parse_deploy_ref, parse_timestamp

SAMPLE = """
2026-09-01T09:00,orders,commit,a1
2026-09-01T10:30,orders,commit,a2
2026-09-01T14:00,orders,deploy,d1:a1+a2
2026-09-02T11:00,orders,commit,a3
2026-09-02T15:00,orders,deploy,d2:a3
2026-09-02T15:10,orders,failed,d2
2026-09-02T15:40,orders,recovered,d2
2026-09-03T09:30,orders,commit,a4
2026-09-03T10:00,orders,deploy,d3:a4
2026-09-04T16:00,orders,commit,a5
2026-09-07T10:00,orders,deploy,d4:a5
2026-09-01T10:00,billing,commit,b1
2026-09-02T10:00,billing,commit,b2
2026-09-03T10:00,billing,commit,b3
2026-09-04T10:00,billing,commit,b4
2026-09-05T12:00,billing,deploy,e1:b1+b2+b3+b4
2026-09-05T12:20,billing,failed,e1
2026-09-05T16:20,billing,recovered,e1
"""


def sample_events() -> list[Event]:
    rows = [line.split(",") for line in SAMPLE.strip().splitlines()]
    return [Event(parse_timestamp(ts), service, EventType(kind), ref) for ts, service, kind, ref in rows]


def by_service() -> dict[str, metrics.ServiceMetrics]:
    events = sample_events()
    start, end = metrics.window_of(events)
    return {name: metrics.compute(events, name, start, end) for name in metrics.services(events)}


def test_the_window_of_the_sample_is_one_week_from_midnight_of_the_first_day():
    start, end = metrics.window_of(sample_events())
    assert start == datetime(2026, 9, 1, tzinfo=UTC)
    assert end - start == timedelta(days=7)


def test_orders_matches_the_lessons_table():
    orders = by_service()["orders"]
    assert orders.deploys_per_week == 4
    assert orders.median_lead_time_hours == 4.0
    assert orders.change_fail_rate == 0.25
    assert orders.median_recovery_minutes == 30


def test_billing_matches_the_lessons_table():
    billing = by_service()["billing"]
    assert billing.deploys_per_week == 1
    assert billing.median_lead_time_hours == 62.0
    assert billing.change_fail_rate == 1.0
    assert billing.median_recovery_minutes == 240


def test_lead_time_is_per_commit_so_a_batch_has_one_value_per_commit():
    leads = metrics.lead_times(sample_events(), "billing")
    assert sorted(lead.hours for lead in leads) == [26, 50, 74, 98]


def test_the_orders_lead_times_are_the_five_the_lesson_lists():
    leads = metrics.lead_times(sample_events(), "orders")
    assert sorted(lead.hours for lead in leads) == [0.5, 3.5, 4.0, 5.0, 66.0]


def test_a_lead_time_is_traced_to_its_commit_event_and_its_deployment_event():
    lead = metrics.trace_lead_time(sample_events(), "orders", "a5")
    assert (lead.commit.ref, lead.commit.type) == ("a5", EventType.COMMIT)
    assert (lead.deploy.ref, lead.deploy.type) == ("d4:a5", EventType.DEPLOY)
    assert lead.hours == 66.0


def test_tracing_a_commit_that_never_deployed_is_an_error():
    with pytest.raises(UnknownCommitError):
        metrics.trace_lead_time(sample_events(), "orders", "zzz")


def test_a_deployment_with_no_commits_does_not_count_towards_frequency_but_is_reported():
    events = [*sample_events(), Event(parse_timestamp("2026-09-06T12:00"), "orders", EventType.DEPLOY, "d9:")]
    start, end = metrics.window_of(events)
    orders = metrics.compute(events, "orders", start, end)
    assert orders.deploys == 4
    assert orders.empty_deploys == 1


def test_a_failure_with_no_recovery_is_counted_as_open_not_as_a_zero_recovery_time():
    events = [e for e in sample_events() if not (e.service == "billing" and e.type is EventType.RECOVERED)]
    start, end = metrics.window_of(events)
    billing = metrics.compute(events, "billing", start, end)
    assert billing.open_failures == 1
    assert billing.median_recovery_minutes is None


def test_a_service_with_no_deployments_has_no_rates():
    events = [Event(parse_timestamp("2026-09-01T09:00"), "quiet", EventType.COMMIT, "q1")]
    start, end = metrics.window_of(events)
    quiet = metrics.compute(events, "quiet", start, end)
    assert (quiet.deploys, quiet.change_fail_rate, quiet.median_lead_time_hours) == (0, None, None)


def test_the_weekly_breakdown_has_one_row_per_service_for_every_week_of_the_data():
    events = [*sample_events(), Event(parse_timestamp("2026-09-10T10:00"), "orders", EventType.COMMIT, "a6")]
    start, end = metrics.window_of(events)
    weeks = metrics.weekly(events, start, end)
    assert [index for index, _ in weeks] == [1, 2]
    assert {row.service for row in weeks[0][1]} == {"orders", "billing"}


def test_the_median_batch_size_tells_a_weekly_batch_from_small_changes():
    table = by_service()
    assert table["orders"].median_batch_size == 1.0
    assert table["billing"].median_batch_size == 4.0


def test_deploy_refs_round_trip():
    assert parse_deploy_ref("d1:a1+a2").commits == ("a1", "a2")
    assert parse_deploy_ref("d9:").commits == ()
    assert format_deploy_ref("d1", ["a1", "a2"]) == "d1:a1+a2"


def test_a_naive_timestamp_is_taken_as_utc_and_an_offset_is_converted():
    assert parse_timestamp("2026-09-01T09:00") == datetime(2026, 9, 1, 9, tzinfo=UTC)
    assert parse_timestamp("2026-09-01T11:00+02:00") == datetime(2026, 9, 1, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    ("service", "kind", "ref", "detail"),
    [
        ("X", EventType.COMMIT, "a1", ""),
        ("orders", EventType.COMMIT, "bad ref!", ""),
        ("orders", EventType.DEPLOY, "no-colon", ""),
        ("orders", EventType.COMMIT, "a1", "why"),
    ],
)
def test_an_event_that_cannot_be_placed_on_a_timeline_is_refused(service, kind, ref, detail):
    with pytest.raises(InvalidEventError):
        Event(datetime(2026, 9, 1, tzinfo=UTC), service, kind, ref, detail)


def test_an_event_without_a_time_zone_is_refused():
    with pytest.raises(InvalidEventError, match="time zone"):
        Event(datetime(2026, 9, 1), "orders", EventType.COMMIT, "a1")


def test_a_refused_deployment_is_counted_as_refused_not_as_a_failed_deployment():
    events = sample_events() + [
        Event(parse_timestamp("2026-09-03T12:00"), "orders", EventType.FAILED, "d-unsigned", "signature")
    ]
    start, end = metrics.window_of(events)
    orders = metrics.compute(events, "orders", start, end)
    assert orders.refused == 1
    assert orders.change_fail_rate == 0.25

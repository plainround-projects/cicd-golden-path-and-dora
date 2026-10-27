"""A month of simulated work for three teams, as delivery events. Deterministic for a seed.

The simulation is a model with stated assumptions, not a measurement: it encodes that a bigger change fails more
often and takes longer to recover from (`fail_base + fail_per_commit * size`, `recovery_base + recovery_per_commit *
size`). What it shows is what the metrics make visible when teams batch differently, which is step 6 of the lesson.
The events go through the same `record` use case as the pipeline's own.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from goldenpath.domain.events import Event, EventType, format_deploy_ref

START: Final = datetime(2026, 9, 7, tzinfo=UTC)  # a Monday


@dataclass(frozen=True, slots=True)
class TeamProfile:
    """How a team works: how often it commits, when it deploys, and how risky and slow to fix its changes are."""

    service: str
    commits_per_day: tuple[int, int]
    deploy_days: tuple[int, ...] | None  # weekdays (Mon=0) the team deploys on; None means after every merge
    fail_base: float
    fail_per_commit: float
    recovery_base_minutes: float
    recovery_per_commit_minutes: float


SMALL_CHANGES: Final = TeamProfile("orders", (2, 4), None, 0.04, 0.02, 15.0, 4.0)
BI_WEEKLY: Final = TeamProfile("search", (1, 3), (1, 3), 0.04, 0.025, 20.0, 12.0)
WEEKLY_BATCH: Final = TeamProfile("billing", (1, 3), (4,), 0.04, 0.03, 30.0, 30.0)
TEAMS: Final = (SMALL_CHANGES, BI_WEEKLY, WEEKLY_BATCH)


def _at(day: datetime, hour: float) -> datetime:
    return day + timedelta(hours=hour)


def simulate_team(profile: TeamProfile, rng: random.Random, days: int = 28, start: datetime = START) -> list[Event]:
    """Events for one team over `days` days: working days only, commits during the day, deploys by the team's policy."""
    events: list[Event] = []
    pending: list[str] = []
    commit_count = 0
    deploy_count = 0
    for offset in range(days):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        todays: list[tuple[datetime, str]] = []
        for _ in range(rng.randint(*profile.commits_per_day)):
            commit_count += 1
            ref = f"{profile.service}-c{commit_count}"
            moment = _at(day, rng.uniform(9, 16))
            events.append(Event(moment, profile.service, EventType.COMMIT, ref))
            todays.append((moment, ref))
        deploy_times: list[tuple[datetime, list[str]]] = []
        if profile.deploy_days is None:
            for moment, ref in sorted(todays):
                deploy_times.append((moment + timedelta(hours=rng.uniform(0.5, 4)), [*pending, ref]))
                pending = []
        else:
            pending.extend(ref for _, ref in sorted(todays))
            if day.weekday() in profile.deploy_days and pending:
                deploy_times.append((_at(day, 12 + rng.uniform(0, 1)), pending))
                pending = []
        for moment, commits in deploy_times:
            deploy_count += 1
            deployment = f"{profile.service}-d{deploy_count}"
            events.append(Event(moment, profile.service, EventType.DEPLOY, format_deploy_ref(deployment, commits)))
            size = len(commits)
            if rng.random() < min(0.9, profile.fail_base + profile.fail_per_commit * size):
                failed_at = moment + timedelta(minutes=rng.uniform(2, 15))
                events.append(Event(failed_at, profile.service, EventType.FAILED, deployment, "health-check"))
                minutes = (profile.recovery_base_minutes + profile.recovery_per_commit_minutes * size) * rng.uniform(
                    0.7, 1.4
                )
                events.append(
                    Event(failed_at + timedelta(minutes=minutes), profile.service, EventType.RECOVERED, deployment)
                )
    return events


def simulate(seed: int, days: int = 28, teams: tuple[TeamProfile, ...] = TEAMS) -> list[Event]:
    """Every team's events, in time order. The same seed always gives the same month."""
    rng = random.Random(seed)  # noqa: S311 - a simulation, not a secret
    events = [event for team in teams for event in simulate_team(team, rng, days)]
    return sorted(events, key=lambda event: (event.ts, event.service, event.type.value))

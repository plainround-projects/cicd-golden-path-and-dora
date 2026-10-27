# DORA metrics (the four measures of delivery)

## What it is

Software teams argue about whether they are getting better at delivering. **DORA** (DevOps Research and Assessment) is a long-running research programme that studied thousands of teams and found four measures that move together with good delivery. This is not a library or a tool; it is the **idea** the second half of this repository computes.

| Measure | The question it answers |
|---|---|
| **Deployment frequency** | How often does the team put a change into production? |
| **Lead time for changes** | How long from a commit to that commit running in production? |
| **Change fail rate** | What share of deployments fail and need a fix, rollback or incident response? |
| **Recovery time** | How long to restore service after a failed deployment? |

The first two measure **speed**; the last two measure **stability**. A team that is fast but unstable, or stable but slow, is not doing well. The research found that the best teams are both.

Vocabulary: a **commit** is one saved change to the code ([git.md](git.md)). A **deployment** is a release of the code into production; it can contain several commits (a **batch**). A **median** is the middle value of a sorted list; one extreme value hardly moves it, unlike the average.

## Why this repository uses it

The lesson's argument: a golden path (a ready-made, safe way to build and ship a service) pays off only if you can *show* it. So every pipeline records four kinds of **event**; the platform stores them and turns them into these four numbers per service and per week. A simulation then shows what the numbers reveal when three teams work differently.

## Where it appears

| Path | Use |
|---|---|
| `src/goldenpath/domain/events.py` | `Event`, `EventType`: the facts. |
| `src/goldenpath/domain/metrics.py` | `compute`, `lead_times`, `trace_lead_time`, `window_of`, `weekly`. |
| `src/goldenpath/domain/simulation.py` | A deterministic month for three teams. |
| `sql/003_queries.sql` | The same metrics as SQL ([sql.md](sql.md)). |
| `data/events-sample.csv` | The lesson's sample events ([csv.md](csv.md)). |
| `docs/adr/0001...0002...0006` | Decisions: events come from the pipeline's clock; the metric definitions and the window; the simulation's assumptions. |

## How it works underneath

Everything is computed from four kinds of event per service, and from nothing else (not even Git history, which can be rewritten):

| Event | Its `ref` | Meaning |
|---|---|---|
| `commit` | `a1` | A commit entered the pipeline. |
| `deploy` | `d1:a1+a2` | Deployment `d1` reached production containing commits `a1` and `a2`. |
| `failed` | `d1` (detail: `health-check`, `rollback`, `incident` or `signature`) | Deployment `d1` failed. |
| `recovered` | `d1` | Service was restored after the failure of `d1`. |

The time of every event comes from the pipeline's or the collector's clock, never from a field a developer can edit. That is why a lead time can be trusted.

The **window** is the data's own: from midnight of the first day, in whole weeks, up to the week of the last event. Weeks are counted from the first midnight, not by calendar.

## Walkthrough of this repository's use

The Python code is explained line by line in [python.md](python.md) (`metrics.py`, `events.py`). Here is what it computes, worked through on the lesson's sample.

### The sample, `data/events-sample.csv`

```
ts,service,type,ref
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
```

Two services. For `orders`:

- Commit `a1` (Tuesday 1 September, 09:00) and `a2` (10:30) go out together in deployment `d1` at 14:00. Their lead times are 5 hours and 3.5 hours.
- `a3` (2 September 11:00) goes out in `d2` at 15:00: 4 hours. `d2` fails at 15:10 and is recovered at 15:40: **30 minutes** to recover.
- `a4` (3 September 09:30) goes out in `d3` at 10:00: 0.5 hours. `a5` (4 September 16:00, a Friday) waits until `d4` on Monday 7 September at 10:00: 66 hours.
- Four real deployments in a window of one week: **4 deployments per week**. One failed out of four: **25 percent** change fail rate. The median of the five lead times (5, 3.5, 4, 0.5, 66 hours) is **4.0 hours**.

For `billing`: four commits (1, 2, 3 and 4 September, 10:00 each) go out together in `e1` on 5 September at 12:00. Each lead time is the deployment time minus the commit time: 4 days 2 hours = 98 hours, 3 days 2 hours = 74, 2 days 2 hours = 50, 1 day 2 hours = 26. The sorted list 26, 50, 74, 98 has the median (50 + 74) / 2 = **62 hours**. `e1` fails at 12:20 and recovers at 16:20: **240 minutes**. One deployment in the week, a **100 percent** fail rate.

`make dora-sample` prints this, computed by the code:

```
service  deploys/week  median lead time  change fail rate  recovery time  batch  empty  open  refused
billing  1             62.0 h            100%              240 min        4.0    0      0     0
orders   4             4.0 h             25%               30 min         1.0    0      0     0
```

The extra columns keep the numbers honest: **batch** is the median number of commits per deployment; **empty** counts deployments with no commit (they are not real deployments and do not count); **open** counts failures with no recovery yet; **refused** counts deployments blocked before they ran because the image was unsigned.

### Lead time, in code

<!-- fmt:off -->
```python
def lead_times(events: Iterable[Event], service: str) -> list[LeadTime]:
    """Every commit of `service` that reached a deployment, with its lead time."""
    commits = {event.ref: event for event in events if event.service == service and event.type is EventType.COMMIT}
    result = []
    for event in events:
        if event.service == service and event.type is EventType.DEPLOY:
            for commit_ref in parse_deploy_ref(event.ref).commits:
                commit = commits.get(commit_ref)
                if commit is not None:
                    result.append(LeadTime(commit, event, (event.ts - commit.ts).total_seconds() / 3600))
    return result
```
<!-- fmt:on -->

For every `deploy` event of the service and every commit named in its ref, find the commit's event and compute `(event.ts - commit.ts).total_seconds() / 3600`: hours between the two events. Batching matters: if four commits ship together on Friday, the Monday commit waited four days. The reported value is the **median** of these per-commit values over deployments inside the window.

### Change fail rate and recovery, in code

<!-- fmt:off -->
```python
def compute(events: Sequence[Event], service: str, start: datetime, end: datetime) -> ServiceMetrics:
    """The metrics of one service for deployments inside `[start, end)`."""
    own = [event for event in events if event.service == service]
    deploys = [event for event in own if event.type is EventType.DEPLOY and _in_window(event, start, end)]
    real = [event for event in deploys if parse_deploy_ref(event.ref).commits]
    ids = {parse_deploy_ref(event.ref).deployment: event for event in real}
    failures = [event for event in own if event.type is EventType.FAILED and event.ref in ids]
    recoveries = defaultdict(list)
    for event in own:
        if event.type is EventType.RECOVERED:
            recoveries[event.ref].append(event.ts)
    recovery_minutes: list[float] = []
    open_failures = 0
    for failure in failures:
        later = [ts for ts in recoveries[failure.ref] if ts >= failure.ts]
        if later:
            recovery_minutes.append((min(later) - failure.ts).total_seconds() / 60)
        else:
            open_failures += 1
    window_leads = [lead.hours for lead in lead_times(own, service) if _in_window(lead.deploy, start, end)]
    weeks = (end - start) / WEEK
    return ServiceMetrics(
        service=service,
        window_start=start,
        window_end=end,
        deploys=len(real),
        empty_deploys=len(deploys) - len(real),
        deploys_per_week=len(real) / weeks if weeks else 0.0,
        median_lead_time_hours=_median(window_leads),
        change_fail_rate=len({failure.ref for failure in failures}) / len(real) if real else None,
        median_recovery_minutes=_median(recovery_minutes),
        median_batch_size=_median([float(len(parse_deploy_ref(event.ref).commits)) for event in real]),
        open_failures=open_failures,
        refused=sum(
            1
            for event in own
            if event.type is EventType.FAILED and event.detail == "signature" and start <= event.ts < end
        ),
    )
```
<!-- fmt:on -->

A `failed` event counts only if its `ref` is one of the window's real deployments. The set `{failure.ref for failure in failures}` counts each failed deployment once even if it has several `failed` events. Each failure is paired with the earliest `recovered` event for the same deployment at or after it; the difference in minutes goes into the recovery list; a failure with no recovery is `open`. Details of every line are in [python.md](python.md).

### The simulation

`simulate(seed)` produces 28 days for three teams: `orders` (small changes, deploys after every merge), `search` (deploys Tuesday and Thursday) and `billing` (one weekly batch on Friday). A bigger batch fails more often and takes longer to fix, by stated assumptions (ADR 0006):

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

`rng.random() < min(0.9, profile.fail_base + profile.fail_per_commit * size)` is the chance of failure for a deployment of `size` commits (`min(0.9, ...)` caps it at 90 percent); the recovery time is `(recovery_base + recovery_per_commit * size) * rng.uniform(0.7, 1.4)` minutes. The result shows what the metrics make visible when teams batch differently; it is a model, not a measurement.

### The same numbers in SQL

`sql/003_queries.sql` computes the four metrics again in SQL and a test checks that SQL and Python agree on the sample ([sql.md](sql.md), [pytest.md](pytest.md)).

## Try it yourself

```bash
make dora-sample
```
Expect the table above.

```bash
.venv/bin/goldenpath trace orders a1 --csv data/events-sample.csv
```
Expect the commit event (2026-09-01 09:00), the deploy event (`d1:a1+a2` at 14:00) and `lead time: 5.0 h`.

```bash
make up && make simulate && make dora
```
Needs the database. Prints one row per team with different batch sizes; `orders` has the shortest lead time and `billing` the longest.

```bash
.venv/bin/python -c "from goldenpath.domain.simulation import simulate; print(len(simulate(1)), len(simulate(2)))"
```
Prints two different counts (220 and 232 on this machine): two seeds, two different months.

## Mistakes people make

- Measuring from Git history (rebased or edited) instead of from recorded events.
- Averaging lead times. One slow outlier ruins an average; the median does not move.
- Counting empty deployments as real ones.
- Optimising one measure alone (frequency without stability).
- Using the metrics to rank individuals. They describe a system.

## Check yourself

1. Why do all event times come from the pipeline's clock? *So nobody can change a lead time by editing a field.*
2. What is the lead time of a commit? *Time from its `commit` event to the `deploy` event containing it.*
3. What does a larger batch do to the metrics, in the simulation? *Longer lead time, more failures, slower recovery.*
4. What is the `refused` column? *Deployments blocked before they ran, because the image was unsigned.*
5. Why a median? *One outlier barely moves it.*

## Further reading

- DORA research and the four key metrics: https://dora.dev/guides/dora-metrics-four-keys/
- The State of DevOps reports: https://dora.dev/research/

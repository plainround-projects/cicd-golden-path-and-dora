# DORA metrics (the four measures of delivery)

## What it is

DORA (DevOps Research and Assessment) is a long-running research programme on what makes software teams deliver well. It found four measures that move together with good delivery. This is not a tool or a library; it is the **idea** the second half of this repository computes.

| Measure | Question it answers |
|---|---|
| **Deployment frequency** | How often does a team put a change into production? |
| **Lead time for changes** | How long from a commit to that commit running in production? |
| **Change fail rate** | What share of deployments need a fix, rollback or incident response? |
| **Recovery time** | How long to restore service after a failed deployment? |

The first two measure **speed**; the last two measure **stability**. A team that is fast and unstable, or stable and slow, is not doing well.

## Why this repository uses it

The lesson's argument: a golden path pays off only if you can show it. The platform records delivery events from every pipeline and turns them into these four numbers per service and per week. The simulation then shows what the numbers reveal when three teams work differently.

## Where it appears

| Path | Use |
|---|---|
| `src/goldenpath/domain/events.py` | `Event`, `EventType`: the facts. |
| `src/goldenpath/domain/metrics.py` | `compute`, `lead_times`, `trace_lead_time`, `window_of`, `weekly`. |
| `src/goldenpath/domain/simulation.py` | A deterministic month for three teams. |
| `sql/003_queries.sql` | The same metrics in SQL. |
| `data/events-sample.csv` | The lesson's sample events. |
| `docs/adr/0001...0002...0006` | Decisions: events come from the pipeline's clock; definitions and window; assumptions of the simulation. |

## How it works underneath

Everything is computed from four kinds of event, per service:

| Event | `ref` | Meaning |
|---|---|---|
| `commit` | `a1` | A commit entered the pipeline. |
| `deploy` | `d1:a1+a2` | Deployment `d1` reached production with commits `a1` and `a2`. |
| `failed` | `d1` (detail: `health-check`, `rollback`, `incident`, `signature`) | Deployment `d1` failed. |
| `recovered` | `d1` | Service was restored after the failure of `d1`. |

The time stamp of every event comes from the **pipeline's clock** (or the collector's), never from a field a developer can edit. That is why "lead time" can be trusted.

The **window** is the data's own: midnight of the first day, in whole weeks, up to the week of the last event. Weeks are counted from the first midnight, not by calendar.

## Walkthrough of this repository's use

### Lead time

```python
def lead_times(events, service):
    commits = {event.ref: event for event in events if event.service == service and event.type is EventType.COMMIT}
    ...
    for commit_ref in parse_deploy_ref(event.ref).commits:
        commit = commits.get(commit_ref)
        if commit is not None:
            result.append(LeadTime(commit, event, (event.ts - commit.ts).total_seconds() / 3600))
```
Every commit that appears in a deployment gets its own lead time: the deploy event's time minus the commit event's time, in hours. Batching matters: if four commits ship together on Friday, the Monday commit waits four days. The reported number is the **median** of these per-commit values.

### The sample, step by step

For `sample-orders` in `data/events-sample.csv`:

- Commit `a1` at 09:00 and `a2` at 10:30 deploy together as `d1` at 14:00. Lead times: 5 h and 3.5 h.
- Four real deployments in a week: deployment frequency 4 per week.
- `d2` fails ten minutes after it deploys and is recovered 30 minutes after the failure: one failed deployment of four is a **25%** change fail rate, and recovery time is **30 minutes**.

For `billing`, four commits deploy together once a week (`e1`), fail, and take 240 minutes to restore: 1 deployment per week, median lead time 62 hours, a 100% fail rate, 240 minutes to recover.

`make dora-sample` prints:

```
service  deploys/week  median lead time  change fail rate  recovery time  batch  empty  open  refused
billing  1             62.0 h            100%              240 min        4.0    0      0     0
orders   4             4.0 h             25%               30 min         1.0    0      0     0
```
The extra columns keep the numbers honest: **batch** is the median number of commits per deployment; **empty** counts deployments with no commit (they do not count as real deployments); **open** counts failures with no recovery yet; **refused** counts deployments blocked before anything ran because the image was unsigned.

### Change fail rate and recovery

```python
change_fail_rate=len({failure.ref for failure in failures}) / len(real) if real else None
```
A set of distinct failed deployment ids divided by real deployments. A failed event for the same deployment twice counts once. For recovery, each `failed` event is paired with the earliest `recovered` event for the same deployment at or after it.

### The simulation

`simulate(seed)` produces 28 days for three teams: `orders` (small changes, deploy after every merge), `search` (deploys Tuesday and Thursday) and `billing` (one weekly batch on Friday). A bigger batch fails more often and takes longer to fix:

```python
if rng.random() < min(0.9, profile.fail_base + profile.fail_per_commit * size):
```
These are **stated assumptions**, not measurements (see ADR 0006). The result shows what the metrics make visible when teams batch differently.

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

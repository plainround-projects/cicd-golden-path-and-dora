# 2. How the four metrics are defined, and over which window

Status: accepted, 2026-10-27

## Context

The lesson defines the metrics in one sentence each and gives a table for a sample week. Several choices hide inside those sentences.

## Decision

- **Window:** weeks are counted from midnight (UTC) of the first day of the data, in blocks of seven days, up to the week of the last event. The sample's single week is 2026-09-01 to 2026-09-07, which is why `orders` has four deployments per week (the fourth is on 2026-09-07).
- **Deployment frequency:** deployments in the window with at least one commit, divided by the window's length in weeks. A deployment with no commits is counted separately (`empty`), never in the frequency: the guard against inflating it with empty deployments.
- **Lead time:** one value per commit, from its `commit` event to the `deploy` event that contains it; reported as the median of the window's deployments. A batch of four commits has four lead times.
- **Change fail rate:** deployments with at least one `failed` event, divided by deployments. A rolled-back deployment is a failed deployment.
- **Recovery time:** for each failure, the time to the next `recovered` event of the same deployment; the median. A failure with no recovery yet is counted as `open`, not as a time.
- **Batch size:** the median number of commits per deployment, shown beside the four metrics, because they are read together.

## Alternatives considered

- **ISO weeks:** put the sample's fourth deployment in the next week, so the sample would not match the lesson's table.
- **Mean instead of median:** a single weekend-long lead time would dominate the number.

## Consequences

- The Python domain (`goldenpath/domain/metrics.py`) and the SQL in `sql/003_queries.sql` give the lesson's table for the sample; a test compares them on a real PostgreSQL.
- A service with no deployments has no rates (`n/a`), not zeros.

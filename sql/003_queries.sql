-- The queries the project's README and tests run. Each starts with a one-line comment on what it shows.
-- Run them with: docker compose exec -T db psql -U platform -d events -f /dev/stdin < sql/003_queries.sql

-- Step 4: every production deployment of a service with the commits it contained.
SELECT service, deploy_id, deployed_at, coalesce(string_agg(commit_ref, ', ' ORDER BY commit_ref), '(none)') AS commits
FROM deploy_commits
WHERE service = 'sample-orders'
GROUP BY service, deploy_id, deployed_at
ORDER BY deployed_at;

-- Step 5: trace one lead time to its two events: the commit event and the deployment event.
SELECT l.commit_ref, l.committed_at, l.deploy_id, l.deployed_at, round(l.hours::numeric, 1) AS hours
FROM lead_times l
WHERE l.service = 'sample-orders' AND l.commit_ref = 'a5';

-- Step 5: the four metrics per service, in SQL. The window is the data's own: midnight of the first day, whole weeks.
-- Remove the sample filter to measure every service. The numbers must equal `make dora-sample` (the Python domain).
WITH scope AS (
    SELECT * FROM events WHERE service LIKE 'sample-%'
), window_ AS (
    SELECT date_trunc('day', min(ts)) AS start_at,
           ceil(extract(epoch FROM max(ts) - date_trunc('day', min(ts))) / (7 * 86400.0)) AS weeks
    FROM scope
), real_deploys AS (
    SELECT DISTINCT d.service, d.deploy_id, d.deployed_at
    FROM deploy_commits d, window_ w
    WHERE d.commit_ref IS NOT NULL AND d.deployed_at >= w.start_at AND d.deployed_at < w.start_at + w.weeks * interval '7 days'
      AND d.service LIKE 'sample-%'
), failures AS (
    SELECT f.service, f.ref AS deploy_id, f.ts AS failed_at,
           (SELECT min(r.ts) FROM events r WHERE r.service = f.service AND r.type = 'recovered' AND r.ref = f.ref AND r.ts >= f.ts) AS recovered_at
    FROM events f WHERE f.type = 'failed' AND f.service LIKE 'sample-%'
)
SELECT d.service,
       round(count(*)::numeric / max(w.weeks), 1)                                             AS deploys_per_week,
       round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY l.hours)
              FROM lead_times l JOIN real_deploys x USING (service, deploy_id) WHERE l.service = d.service)::numeric, 1) AS median_lead_time_hours,
       round(100.0 * count(DISTINCT f.deploy_id) / count(*))                                  AS change_fail_rate_percent,
       round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM f2.recovered_at - f2.failed_at) / 60)
              FROM failures f2 WHERE f2.service = d.service AND f2.recovered_at IS NOT NULL)::numeric) AS median_recovery_minutes
FROM real_deploys d
CROSS JOIN window_ w
LEFT JOIN failures f ON f.service = d.service AND f.deploy_id = d.deploy_id
GROUP BY d.service
ORDER BY d.service;

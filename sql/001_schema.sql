-- DDL: the delivery event store. Applied by `make db`. One table, written only through the collector (or the simulation),
-- plus two views that turn deploy refs into rows so the metrics can be asked for in SQL as well as in Python.
CREATE TABLE IF NOT EXISTS events (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts      timestamptz NOT NULL,
    service text        NOT NULL,
    type    text        NOT NULL,
    ref     text        NOT NULL,
    detail  text        NOT NULL DEFAULT '',
    CONSTRAINT events_service_format CHECK (service ~ '^[a-z][a-z0-9-]{1,38}$'),
    CONSTRAINT events_type_known     CHECK (type IN ('commit', 'deploy', 'failed', 'recovered')),
    CONSTRAINT events_ref_format     CHECK (ref ~ '^[A-Za-z0-9._:+-]{1,200}$'),
    CONSTRAINT events_deploy_ref     CHECK (type <> 'deploy' OR ref LIKE '%:%'),
    CONSTRAINT events_detail_only_on_failed CHECK (detail = '' OR type = 'failed'),
    -- the same event sent twice (a retried pipeline step) is stored once
    CONSTRAINT events_unique UNIQUE (service, type, ref, ts)
);

COMMENT ON TABLE  events        IS 'Delivery events from pipelines: commit, deploy, failed, recovered. Every DORA metric is computed from this table only.';
COMMENT ON COLUMN events.ts     IS 'UTC, from the pipeline''s clock for every type, never from a developer-set field.';
COMMENT ON COLUMN events.ref    IS 'A commit id; for a deploy "<deployment id>:<commit>+<commit>"; for failed and recovered the deployment id.';
COMMENT ON COLUMN events.detail IS 'Why a deployment failed: rollback, incident, health-check or signature. Empty otherwise.';

CREATE INDEX IF NOT EXISTS events_service_type_ts_idx ON events (service, type, ts);

-- One row per commit of a deployment (an empty deployment has one row with a NULL commit_ref).
CREATE OR REPLACE VIEW deploy_commits AS
SELECT e.service,
       split_part(e.ref, ':', 1) AS deploy_id,
       e.ts                      AS deployed_at,
       nullif(c.commit_ref, '')  AS commit_ref
FROM events e
CROSS JOIN LATERAL unnest(string_to_array(split_part(e.ref, ':', 2), '+')) AS c(commit_ref)
WHERE e.type = 'deploy'
UNION ALL
SELECT e.service, split_part(e.ref, ':', 1), e.ts, NULL
FROM events e
WHERE e.type = 'deploy' AND split_part(e.ref, ':', 2) = '';

COMMENT ON VIEW deploy_commits IS 'Every production deployment with the commits it contained.';

-- Lead time per commit: from the commit event to the deployment that contains it, in hours.
CREATE OR REPLACE VIEW lead_times AS
SELECT d.service,
       d.commit_ref,
       c.ts        AS committed_at,
       d.deploy_id,
       d.deployed_at,
       extract(epoch FROM d.deployed_at - c.ts) / 3600.0 AS hours
FROM deploy_commits d
JOIN events c ON c.service = d.service AND c.type = 'commit' AND c.ref = d.commit_ref;

COMMENT ON VIEW lead_times IS 'One row per commit that reached production, with the two events it is the difference of.';

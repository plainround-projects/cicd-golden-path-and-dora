-- DML: the lesson's sample week, for two services, so the queries in 003_queries.sql have the numbers the lesson expects.
-- The services are named sample-orders and sample-billing so the sample never mixes with the services the demos create.
-- Re-running is safe: the sample rows are replaced.
DELETE FROM events WHERE service IN ('sample-orders', 'sample-billing');

INSERT INTO events (ts, service, type, ref, detail) VALUES
    ('2026-09-01 09:00+00', 'sample-orders', 'commit',    'a1', ''),
    ('2026-09-01 10:30+00', 'sample-orders', 'commit',    'a2', ''),
    ('2026-09-01 14:00+00', 'sample-orders', 'deploy',    'd1:a1+a2', ''),
    ('2026-09-02 11:00+00', 'sample-orders', 'commit',    'a3', ''),
    ('2026-09-02 15:00+00', 'sample-orders', 'deploy',    'd2:a3', ''),
    ('2026-09-02 15:10+00', 'sample-orders', 'failed',    'd2', 'health-check'),
    ('2026-09-02 15:40+00', 'sample-orders', 'recovered', 'd2', ''),
    ('2026-09-03 09:30+00', 'sample-orders', 'commit',    'a4', ''),
    ('2026-09-03 10:00+00', 'sample-orders', 'deploy',    'd3:a4', ''),
    ('2026-09-04 16:00+00', 'sample-orders', 'commit',    'a5', ''),
    ('2026-09-07 10:00+00', 'sample-orders', 'deploy',    'd4:a5', ''),
    ('2026-09-01 10:00+00', 'sample-billing', 'commit',    'b1', ''),
    ('2026-09-02 10:00+00', 'sample-billing', 'commit',    'b2', ''),
    ('2026-09-03 10:00+00', 'sample-billing', 'commit',    'b3', ''),
    ('2026-09-04 10:00+00', 'sample-billing', 'commit',    'b4', ''),
    ('2026-09-05 12:00+00', 'sample-billing', 'deploy',    'e1:b1+b2+b3+b4', ''),
    ('2026-09-05 12:20+00', 'sample-billing', 'failed',    'e1', 'health-check'),
    ('2026-09-05 16:20+00', 'sample-billing', 'recovered', 'e1', '');

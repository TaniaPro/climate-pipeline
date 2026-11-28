-- Records one summary row per nightly run into meta._run_history.
-- Runs as its own Airflow task with trigger_rule="all_done", so even a
-- crashed load gets recorded. Dates are computed in UTC, so the result
-- doesn't depend on the client's timezone.
-- One row per UTC date: a rerun on the same day updates that row.

WITH last_run AS (
    SELECT (MAX(updated_at) AT TIME ZONE 'UTC')::date AS run_date
    FROM meta._load_manifest
)
INSERT INTO meta._run_history
    (run_date, stations_updated, total_rows, zero_row_stations, failed_stations)
SELECT lr.run_date,
       count(*),
       COALESCE(SUM(m.row_count), 0),
       count(*) FILTER (WHERE m.row_count = 0),
       count(*) FILTER (WHERE m.status = 'failed')
FROM meta._load_manifest m
CROSS JOIN last_run lr
WHERE (m.updated_at AT TIME ZONE 'UTC')::date = lr.run_date
GROUP BY lr.run_date
ON CONFLICT (run_date) DO UPDATE SET
    stations_updated  = EXCLUDED.stations_updated,
    total_rows        = EXCLUDED.total_rows,
    zero_row_stations = EXCLUDED.zero_row_stations,
    failed_stations   = EXCLUDED.failed_stations,
    recorded_at       = now();
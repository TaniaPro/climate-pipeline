SELECT t.*,
    days_in_month - monthly_observations AS missing_days
FROM (
        SELECT date_trunc('month', obs_date)::date AS month,
            station_id,
            COUNT(*) AS monthly_observations,
            EXTRACT(
                day
                FROM date_trunc('month', obs_date) + interval '1 month - 1 day'
            ) AS days_in_month,
            ROUND(AVG(value), 2) AS tmax_avg
        FROM {{ ref('stg_observations') }}
        WHERE element = 'TMAX'
            AND obs_date >= '1990-01-01'
            AND obs_date < '2026-01-01'
        GROUP BY date_trunc('month', obs_date),
            station_id
    ) t
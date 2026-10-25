SELECT DATE_TRUNC('year', month)::date AS year,
    station_id,
    COUNT(*) FILTER (
        WHERE missing_days <= 5
    ) AS valid_months,
    ROUND(AVG(tmax_avg),2) AS tmax_avg
FROM {{ ref('int_station_monthly') }}
GROUP BY DATE_TRUNC('year', month)::date,
    station_id
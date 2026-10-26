SELECT station_id,
    ROUND(AVG(tmax_avg), 2) AS normal_temp,
    COUNT(*) AS baseline_years
FROM {{ ref('fct_station_yearly') }}
WHERE year BETWEEN '1991-01-01' AND '2020-01-01'
GROUP BY station_id
HAVING count(*)>=24
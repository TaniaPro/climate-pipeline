SELECT LEFT(station_id, 2)                     AS country,
           EXTRACT(year FROM year)::integer    AS year,
           AVG(anomaly)                        AS avg_anomaly,
           COUNT(*)                            AS station_count
    FROM {{ ref('fct_station_anomalies') }}
    GROUP BY LEFT(station_id, 2), EXTRACT(year FROM year)::integer
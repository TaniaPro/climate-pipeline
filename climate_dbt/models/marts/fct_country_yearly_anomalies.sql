SELECT LEFT(sa.station_id, 2)                AS country_code,
       c.country_name,
       EXTRACT(year FROM sa.year)::integer    AS year,
       AVG(sa.anomaly)                        AS avg_anomaly,
       COUNT(*)                               AS station_count
FROM {{ ref('fct_station_anomalies') }} sa
JOIN {{ ref('stg_countries') }} c
    ON LEFT(sa.station_id, 2) = c.fips_code
GROUP BY LEFT(sa.station_id, 2),
         c.country_name,
         EXTRACT(year FROM sa.year)::integer
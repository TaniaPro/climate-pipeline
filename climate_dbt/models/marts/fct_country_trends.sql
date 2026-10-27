WITH stations_per_country AS (
    SELECT LEFT(station_id, 2)        AS country,
           COUNT(DISTINCT station_id) AS station_dist_count
    FROM  {{ ref('fct_station_anomalies') }}
    GROUP BY LEFT(station_id, 2)
)
SELECT cy.country,
       ROUND((regr_slope(cy.avg_anomaly, cy.year) * 10)::numeric, 2) AS slope_c_per_decade,
       ROUND(AVG(cy.station_count), 0)                             AS avg_stations,
       COUNT(*)                                                    AS years,
       spc.station_dist_count,
       CASE 
            WHEN spc.station_dist_count>=10 THEN TRUE 
            ELSE FALSE
       END AS is_reportable
FROM {{ ref('fct_country_yearly_anomalies') }} cy
JOIN stations_per_country spc
ON cy.country=spc.country
GROUP BY cy.country, spc.station_dist_count

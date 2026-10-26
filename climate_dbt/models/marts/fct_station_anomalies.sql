SELECT fsy.station_id,
    fsy.year,
    fsy.tmax_avg,
    isn.normal_temp,
    fsy.tmax_avg - isn.normal_temp AS anomaly
FROM {{ ref('fct_station_yearly') }} AS fsy
    JOIN {{ ref('int_station_normals') }} AS isn ON fsy.station_id = isn.station_id
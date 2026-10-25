SELECT 
    year, 
    station_id,
    tmax_avg
FROM {{ ref('int_station_yearly_validity') }} 
WHERE valid_months = 12


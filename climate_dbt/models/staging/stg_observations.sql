SELECT
    station_id,
    to_date(obs_date, 'YYYYMMDD')  AS obs_date,
    element,
    value::integer                 AS value,
    NULLIF(m_flag, '')             AS m_flag,
    NULLIF(q_flag, '')             AS q_flag,
    NULLIF(s_flag, '')             AS s_flag,
    NULLIF(obs_time, '')           AS obs_time,
    source_file,
    loaded_at
FROM {{ source('raw', 'observations') }}
WHERE station_id IN (SELECT station_id FROM {{ ref('stg_stations') }})
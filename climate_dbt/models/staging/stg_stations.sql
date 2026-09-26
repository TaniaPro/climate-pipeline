SELECT station_id,
    latitude::numeric AS latitude,
    longitude::numeric AS longitude,
    elevation::numeric AS elevation,
    NULLIF(state, '') AS state,
    name,
    loaded_at
FROM {{ source('raw', 'stations') }}
SELECT fips_code,
    country_name
FROM {{ source('raw', 'countries') }}
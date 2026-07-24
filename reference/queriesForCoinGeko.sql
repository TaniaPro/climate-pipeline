/*SELECT
 --gen_random_uuid() as uuid,
 snapshot_ts,
 jsonb_array_elements(CASE jsonb_typeof(ms.payload)
 WHEN 'array' THEN ms.payload
 WHEN 'object' THEN jsonb_build_array(ms.payload)
 --ELSE NULL
 END) AS obj
 FROM
 raw.market_snapshots ms;
 
 CREATE VIEW analytics.market_prices_v1 AS 
 SELECT
 md5(ms.snapshot_ts::text || '|' || p.id) as snapshot_coin_key,
 ms.snapshot_ts,
 p.*
 FROM raw.market_snapshots ms
 CROSS JOIN LATERAL jsonb_to_recordset(ms.payload) AS p (
 id TEXT,
 name TEXT,
 symbol TEXT,
 image TEXT,
 
 ath NUMERIC,
 ath_date TIMESTAMPTZ,
 ath_change_percentage NUMERIC,
 
 atl NUMERIC,
 atl_date TIMESTAMPTZ,
 atl_change_percentage NUMERIC,
 
 current_price NUMERIC,
 low_24h NUMERIC,
 high_24h NUMERIC,
 
 price_change_24h NUMERIC,
 price_change_percentage_24h NUMERIC,
 
 market_cap NUMERIC,
 market_cap_rank NUMERIC,
 market_cap_change_24h NUMERIC,
 market_cap_change_percentage_24h NUMERIC,
 fully_diluted_valuation NUMERIC,
 
 total_volume NUMERIC,
 
 circulating_supply NUMERIC,
 total_supply NUMERIC,
 max_supply NUMERIC,
 
 roi JSONB,
 last_updated TIMESTAMPTZ   
 );


CREATE VIEW analytics.market_prices_latest AS 
SELECT a.*
FROM(
        SELECT mpv.*,
            row_number() OVER (
                PARTITION BY id
                ORDER BY mpv.snapshot_ts DESC,
                    snapshot_coin_key DESC
            ) as rnk
        FROM analytics.market_prices_v1 mpv
    ) a
WHERE a.rnk = 1;*/


select current_database() as db, current_schema() as schema;

select table_schema, table_name
from information_schema.views
where table_schema = 'analytics' and table_name = 'market_prices_v1'
union all
select table_schema, table_name
from information_schema.tables
where table_schema = 'analytics' and table_name = 'market_prices_v1';


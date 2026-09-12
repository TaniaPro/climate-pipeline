import psycopg2

def record_manifest(station_id, status, error, row_count):
    # Upserts one row into meta._load_manifest to track a station's load outcome.
    # ON CONFLICT (station_id): if the station already has a row (e.g. a prior
    # 'failed' attempt), update it in place instead of erroring — so a retry
    # overwrites the old outcome. EXCLUDED is the row we tried to insert (the new
    # values); updated_at = now() stamps the time of this attempt, not the first.
    conn = psycopg2.connect(dbname="climate")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO meta._load_manifest (station_id, status, error, row_count)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (station_id) DO UPDATE SET
            status     = EXCLUDED.status,
            error      = EXCLUDED.error,
            row_count  = EXCLUDED.row_count,
            updated_at = now()
    """, (station_id, status, error, row_count))

    conn.commit()
    cursor.close()
    conn.close()


def is_loaded(station_id):
    conn = psycopg2.connect(dbname="climate")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 1 FROM meta._load_manifest WHERE station_id = %s AND status = 'success'
    """, (station_id,))
    result = cursor.fetchone()

    conn.commit()
    cursor.close()
    conn.close()

    return result is not None
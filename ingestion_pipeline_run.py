from fetch_observations import select_stations, download_station, parse_station, load_observations
from fetch_stations import parse_stations_meta_data, load_station_metadata
from fetch_countries import parse_countries_meta_data, load_countries_metadata
from record_manifest import record_manifest, is_loaded, get_roster


def run_observations_pipeline(daily=False):
    # daily=False (backfill): load each station's full history once; stations
    #   already marked success in the manifest are skipped (resumable).
    # daily=True (scheduled run): re-download EVERY station and upsert only the
    #   last WINDOW_DAYS (see load_observations). Nothing is skipped — the
    #   manifest's "success" means "backfilled", not "up to date".
    station_ids_list = get_roster()

    for i, station_id in enumerate(station_ids_list, start=1):
        if not daily and is_loaded(station_id):
            continue

        station_info = download_station(station_id)
        if station_info is None:
            record_manifest(station_id, "failed", "download failed", None)
            continue

        station_info_parsed = parse_station(station_info, station_id)
        count = load_observations(station_info_parsed, daily=daily)
        # Backfill: a 0-row load means the download was empty (HTTP 200, no
        # content) — a whole history can't be empty. Record it as failed so
        # it's retried, not silently skipped forever.
        # Daily: 0 rows is legitimate — a station with no reports in the last
        # WINDOW_DAYS (e.g. a station whose record stopped years ago).
        if count == 0 and not daily:
            record_manifest(station_id, "failed", "loaded 0 rows", 0)
            continue

        record_manifest(station_id, "success", None, count)

        print(f"loaded {station_id}: {count} rows ({i}/{len(station_ids_list)})")

def run_stations_pipeline():
    rows = parse_stations_meta_data()
    load_station_metadata(rows)
    print(f"loaded {len(rows)} stations")

def run_countries_pipeline():
    rows = parse_countries_meta_data()
    load_countries_metadata(rows)
    print(f"loaded {len(rows)} countries")
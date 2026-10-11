from fetch_observations import select_stations, download_station, parse_station, load_observations
from fetch_stations import parse_stations_meta_data, load_station_metadata
from record_manifest import record_manifest, is_loaded, get_roster


def run_observations_pipeline():
    station_ids_list = get_roster()

    for i, station_id in enumerate(station_ids_list, start=1):
        if is_loaded(station_id):
            continue

        station_info = download_station(station_id)
        if station_info is None:
            record_manifest(station_id, "failed", "download failed", None)
            continue

        station_info_parsed = parse_station(station_info, station_id)
        count = load_observations(station_info_parsed)
        # A 0-row load means the download was empty (HTTP 200, no content).
        # Record it as failed so it's retried, not silently skipped forever.
        if count == 0:
            record_manifest(station_id, "failed", "loaded 0 rows", 0)
            continue

        record_manifest(station_id, "success", None, count)

        print(f"loaded {station_id} ({i}/{len(station_ids_list)})")

def run_stations_pipeline():
    rows = parse_stations_meta_data()
    load_station_metadata(rows)
    print(f"loaded {len(rows)} stations")
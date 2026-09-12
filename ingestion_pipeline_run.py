from fetch_observations import select_stations, download_station, parse_station, load_observations
from fetch_stations import parse_stations_meta_data, load_station_metadata
from record_manifest import record_manifest, is_loaded


def run_observations_pipeline():
    station_ids_list=select_stations()

    for i, station_id in enumerate(station_ids_list, start=1):
        if is_loaded(station_id):
            continue

        station_info = download_station(station_id)
        if station_info is None:
            record_manifest(station_id, "failed", "download failed", None)
            continue

        station_info_parsed = parse_station(station_info, station_id)
        count = load_observations(station_info_parsed)
        record_manifest(station_id, "success", None, count)

        print(f"loaded {station_id} ({i}/{len(station_ids_list)})")

def run_stations_pipeline():
    rows = parse_stations_meta_data()
    load_station_metadata(rows)
    print(f"loaded {len(rows)} stations")
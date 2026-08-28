from fetch_observations import select_stations, download_station, parse_station, load_station

def run_pipeline():
    station_ids_list=select_stations()

    for i, station_id in enumerate(station_ids_list, start=1):
        station_info = download_station(station_id)

        if station_info is None:   # download failed — skip this station
            continue

        station_info_parsed = parse_station(station_info, station_id)
        load_station(station_info_parsed)

        print(f"loaded {station_id} ({i}/{len(station_ids_list)})")
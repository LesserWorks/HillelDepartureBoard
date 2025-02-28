#!/usr/bin/env python3

from google.transit import gtfs_realtime_pb2
from pathlib import Path
from datetime import datetime
from threading import Event
import shutil
import signal
import subprocess
import webbrowser
import requests
import argparse
import csv
import time
import bisect

"""
static GTFS:
routes.txt - maps route_id to the 3 route names
stops.txt - maps stop_id to station name
trips.txt - maps trip_id to route_id, service_id, and trip name (like Train 440 is Camden line blah blah)
stop_times.txt - maps trip_id to arrival and departure times per stop_id (scheduled arr time per stop for Train 440)
calendar.txt - maps service_id to active days of week and start-end dates
calendar_dates.txt - maps service_id to dates where it is added or removed
Note that calendar_dates, stop_times, and shapes have repeat first entries

Parsing steps to get scheduled trip:
{
    nb_stop_id: [{07:50, Train 440, 101P}, {8:10, Train 670, 101C}],
    sb_stop_id: [{arrival time, trip_id, service_id}]
}

Upon screen update:
1. Make copy of master schedule
2. Get snippet of array that has arrival times in the next 99 mins
3. Filter array based on service_id into calendar_dates and calendar
4. Filter array to remove trip_ids that realtime has entries for
5. Append to realtime array

"""

college_park_nb_id = 12018
college_park_sb_id = 12015
new_carrollton_nb_id = 11989
new_carrollton_sb_id = 11988
penn_nd_id = 12002
penn_sb_id = 11980
marc_name_map = {11958: "Washington", 12006: "Baltimore Camden", 12008: "Dorsey", 12025: "Dorsey", 11980: "Baltimore Penn", 12002: "Baltimore Penn"}

schedule_relationship = ['scheduled', 'added', 'unscheduled', 'canceled', 'null', 'replacement', 'duplicated', 'deleted']

exit_event = Event()
def exit_handler(signal, frame):
    exit_event.set()

def get_marc_schedule(marc_info, marc_code):
    staton_pair = marc_code.split('-')
    marc_sched = {staton_pair[0]: [], staton_pair[1]: []}
    for trip_id, info_list in marc_info['stop_times'].items():
        service_id = marc_info['trips'][trip_id]['service_id']
        for info in info_list:
            if info['stop_id'] in staton_pair:
                bisect.insort_right(marc_sched[info['stop_id']], {'arrival_time': info['arrival_time'], 'trip_id': trip_id, 'service_id': service_id}, key=(lambda x: x['arrival_time']))
                break
    return marc_sched

def get_file_last_modifed(url):
    resp = requests.head(url, allow_redirects=True)
    last_modified = resp.headers['last-modified']
    return datetime.strptime(last_modified, '%a, %d %b %Y %H:%M:%S %Z').timestamp()

def download_unpack_zip(url):
    resp = requests.get(url, allow_redirects=True)
    temp_path = Path("./temp.zip")
    with open(temp_path, "wb") as out:
        out.write(resp.content)
    shutil.unpack_archive(temp_path, 'mdotmta_gtfs_marc')
    temp_path.unlink()

def decrypt_metro_api():
    subprocess.run(['openssl', 'enc', '-aes-256-cbc', '-d', '-pbkdf2', '-in', 'metro_api.enc', '-out', 'metro_api.key', '-pass', 'file:file_key.key'], check=True)
    with open('metro_api.key', 'r') as infile:
        key = infile.readline().rstrip()
    return key

def parse_marc_gtfs(folder_path):
    marc_info = {}
    for file in Path(folder_path).iterdir():
        marc_info[file.stem] = {}
        # key is unique in these files
        if file.stem in {'calendar', 'routes', 'stops', 'trips'}:
            with open(file) as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    marc_info[file.stem][list(row.values())[0]] = row
        # key is repeated in these files
        elif file.stem in {'calendar_dates', 'stop_times'}:
            with open(file) as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    key = list(row.values())[0]
                    if key in marc_info[file.stem]:
                        marc_info[file.stem][key].append(row)
                    else:
                        marc_info[file.stem][key] = []
    return marc_info

def get_marc_realtime(marc_code, rows, marc_info):
    station_pair = marc_code.split('-')
    feed = gtfs_realtime_pb2.FeedMessage()
    response = requests.get('https://mdotmta-gtfs-rt.s3.amazonaws.com/MARC+RT/marc-tu.pb')
    feed.ParseFromString(response.content)
    by_dest = {}
    for entity in feed.entity:
        if entity.HasField('trip_update'):
            trip_update = entity.trip_update
            trip_desc = trip_update.trip
            trip_dict = marc_info['trips'][trip_desc.trip_id]
            route_dict = marc_info['routes'][trip_desc.route_id]
            sched_relation = schedule_relationship[trip_desc.schedule_relationship]

            
            print(f"Trip update for {sched_relation} {route_dict['route_long_name'].split()[0]} line {trip_dict['trip_short_name']} to {trip_dict['trip_headsign']}:")
            curr_time = time.time()
            dest_id = int(list(trip_update.stop_time_update)[-1].stop_id)
            for stu in trip_update.stop_time_update:
                if stu.HasField('arrival'):
                    ts = stu.arrival.time
                    from_now = int((ts - curr_time) / 60)
                    if ts > curr_time and from_now > 0:
                        arr_time = datetime.fromtimestamp(ts)
                        print(f"Arriving {arr_time} at {marc_info['stops'][stu.stop_id]['stop_name']}")
                        if stu.stop_id in station_pair:
                            key = marc_name_map[dest_id] if dest_id in marc_name_map else trip_dict['trip_headsign']
                            if key in by_dest:
                                bisect.insort(by_dest[key], from_now)
                            else:
                                by_dest[key] = [from_now]

    allocated_rows = 2
    for key, val in by_dest.items():
        if allocated_rows <= 0:
            break
        rows.append(f'<div class="service-name"><div class="image-backer"><img src="images/MARC_train.svg.png" class="marc-logo"></div>{key}</div><div class="times">{str(val[:2])[1:-1]}</div>')
        allocated_rows -= 1
    for _ in range(allocated_rows, 0, -1):
        rows.append(f'<div class="service-name"></div>')

def get_metro_realtime(code, rows, key):
    url = f'http://api.wmata.com/StationPrediction.svc/json/GetPrediction/{code}?api_key={key}'
    resp = requests.get(url)
    data = resp.json()
    filtered = []
    for entry in data["Trains"]:
        if entry['DestinationName'] not in ['No Passenger', 'Train'] and entry['Min'] not in ['ARR', 'BRD', 'DLY']:
            filtered.append(entry)
    by_dest = {}
    for entry in filtered:
        key = entry['DestinationName']
        if key in by_dest:
            bisect.insort_right(by_dest[key], (int(entry['Min']), entry['Line']), key=(lambda x: x[0]))
        else:
            by_dest[key] = [(int(entry['Min']), entry['Line'])]

    allocated_rows = 2
    for key, val in by_dest.items():
        if allocated_rows <= 0:
            break
        times_str = [x[0] for x in val]
        rows.append(f'<div class="service-name"><img src="images/WMATA_Metro_Logo.svg" class="metro-logo"><div class="metro-bullet {val[0][1]}">{val[0][1]}</div>{key}</div><div class="times">{str(times_str[:2])[1:-1]}</div>')
        allocated_rows -= 1
    for _ in range(allocated_rows, 0, -1):
        rows.append(f'<div class="service-name"><img src="images/WMATA_Metro_Logo.svg" class="metro-logo"></div>')

def add_purple_line(rows):
    rows.append(f'<div class="service-name"></div>')
    rows.append(f'<div class="service-name"><div class="image-backer"><img src="images/MTA_Purple_Line_logo.svg.png" class="purple-line-logo"></div>Coming 2027</div>')

def write_rows(rows):
    with open('template.html', 'r') as infile:
        template = infile.read()
    for i, row in enumerate(rows):
        template = template.replace(f'Row {i}', row)
    with open('DepartureBoard.html', 'w') as outfile:
        outfile.write(template)

def main(args):
    marc_path = './mdotmta_gtfs_marc'
    try:
        if args.marc_code is not None:
            marc_static_gtfs_url  = 'https://feeds.mta.maryland.gov/gtfs/marc'
            marc_gtfs_modified = get_file_last_modifed(marc_static_gtfs_url)
            if not Path(marc_path).exists() or Path(marc_path).stat().st_mtime < marc_gtfs_modified:
                download_unpack_zip(marc_static_gtfs_url)
            marc_info = parse_marc_gtfs(marc_path)
            marc_sched = get_marc_schedule(marc_info, args.marc_code)
        if args.metro_code is not None:
            metro_key = decrypt_metro_api()
    except Exception as e:
        print(f"{type(e).__name__}: {e}")
        return

    while not exit_event.is_set():
        try:
            rows = []
            if args.metro_code is not None:
                get_metro_realtime(args.metro_code, rows, metro_key)
            if args.marc_code is not None:
                get_marc_realtime(args.marc_code, rows, marc_info)
            add_purple_line(rows)
            write_rows(rows)
            written_html = Path('DepartureBoard.html').absolute()
            webbrowser.open(f"file://{written_html}", new=0, autoraise=False)
            if args.refresh > 0:
                exit_event.wait(args.refresh)
            else:
                return
        except Exception as e:
            print(f"{type(e).__name__}: {e}")

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, exit_handler)
    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGHUP, exit_handler)
    parser = argparse.ArgumentParser()
    parser.add_argument('--marc_code', type=str, default=None, help="MARC station code pair, e.g. 11989-11988")
    parser.add_argument('--metro_code', type=str, default=None, help="Metro station code (CP is E09)")
    parser.add_argument('--refresh', type=int, default=0, help="Seconds between page refresh, 0 is no refresh")
    args = parser.parse_args()
    main(args)
    
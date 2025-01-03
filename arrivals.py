#!/usr/bin/env python3

from google.transit import gtfs_realtime_pb2
from pathlib import Path
from datetime import datetime
import requests
import argparse
import csv
import time

"""
static GTFS:
routes.txt - maps route_id to the 3 route names
stops.txt - maps stop_id to station name
trips.txt - maps trip_id to route_id, service_id, and trip name
stop_times.txt - maps trip_id to arrival and departure times per stop_id
calendar.txt - maps service_id to active days of week and start-end dates
calendar_dates.txt - maps service_id to dates where it is added or removed

Parsing steps to get scheduled trip:
1. Parse stop_times into a map from desired stop_id to arrival time and trip_id
2. Lookup in trips.txt to add service_id to map value

Upon screen update:
1. Make copy of master schedule
2. Filter to arrival times in the next 99 mins
3. Filter to service_ids that are active on that day or are added for that day
4. Remove entries that realtime has cancelled

"""

college_park_nb_id = 12018
college_park_sb_id = 12015
new_carrollton_nb_id = 11989
new_carrollton_sb_id = 11988
penn_nd_id = 12002
penn_sb_id = 11980
marc_name_map = {11958: "Washington", 12006: "Baltimore", 12008: "Dorsey"}

schedule_relationship = ['scheduled', 'added', 'unscheduled', 'canceled', 'null', 'replacement', 'duplicated', 'deleted']

def parse_marc_schedule(folder_path):
    north_stop_id = college_park_nb_id
    south_stop_id = college_park_sb_id
    master = {north_stop_id: {}, south_stop_id: {}}

def parse_marc(folder_path):
    marc_info = {}
    for file in Path(folder_path).iterdir():
        if file.stem in {'stops', 'trips', 'routes'}:
            marc_info[file.stem] = {}
            with open(file) as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    marc_info[file.stem][list(row.values())[0]] = row
    return marc_info

def get_marc(marc_code, rows):
    station_pair = marc_code.split('-')
    marc_info = parse_marc('./mdotmta_gtfs_marc') 
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
                    if ts > curr_time:
                        arr_time = datetime.fromtimestamp(ts)
                        print(f"Arriving {arr_time} at {marc_info['stops'][stu.stop_id]['stop_name']}")
                        if stu.stop_id in station_pair:
                            val = int((ts - curr_time) / 60)
                            key = trip_dict['trip_headsign'] if dest_id not in marc_name_map else marc_name_map[dest_id]
                            if key in by_dest:
                                by_dest[key].append(val)
                            else:
                                by_dest[key] = [val]

    allocated_rows = 2
    for key, val in by_dest.items():
        if allocated_rows <= 0:
            break
        rows.append(f'<div class="service-name"><img src="images/MARC_train.svg.png" class="marc-logo">{key}</div><div class="times">{str(val[:2])[1:-1]}</div>')
        allocated_rows -= 1
    for _ in range(allocated_rows, 0, -1):
        rows.append(f'<div class="service-name"><img src="images/MARC_train.svg.png" class="marc-logo"></div>')

def get_metro(code, rows):
    key = 'e13626d03d8e4c03ac07f95541b3091b'
    url = f'http://api.wmata.com/StationPrediction.svc/json/GetPrediction/{code}?api_key={key}'
    resp = requests.get(url)
    data = resp.json()
    filtered = []
    for entry in data["Trains"]:
        if entry['DestinationName'] not in ['No Passenger', 'Train'] and entry['Min'] not in ['ARR', 'BRD', 'DLY']:
            filtered.append(entry)
    by_dest = {}
    for entry in filtered:
        key = (entry['DestinationName'], entry['Line'])
        if key in by_dest:
            by_dest[key].append(int(entry['Min']))          
        else:
            by_dest[key] = [int(entry['Min'])]

    allocated_rows = 2
    for key, val in by_dest.items():
        if allocated_rows <= 0:
            break
        rows.append(f'<div class="service-name"><img src="images/WMATA_Metro_logo.svg.png" class="metro-logo"><div class="metro-bullet {key[1]}">{key[1]}</div>{key[0]}</div><div class="times">{str(val[:2])[1:-1]}</div>')
        allocated_rows -= 1
    for _ in range(allocated_rows, 0, -1):
        rows.append(f'<div class="service-name"><img src="images/WMATA_Metro_logo.svg.png" class="metro-logo"></div>')

def add_purple_line(rows):
    rows.append(f'<div class="service-name"><img src="images/MTA_Purple_Line_logo.svg.png" class="purple-line-logo">Coming 2027</div>')
    rows.append(f'<div class="service-name"><img src="images/MTA_Purple_Line_logo.svg.png" class="purple-line-logo"></div>')

def write_rows(rows):
    with open('template.html', 'r') as infile:
        template = infile.read()
    for i, row in enumerate(rows):
        template = template.replace(f'Row {i}', row)
    with open('DepartureBoard.html', 'w') as outfile:
        outfile.write(template)

def main(args):
    rows = []
    if args.metro_code is not None:
        get_metro(args.metro_code, rows)
    if args.marc_code is not None:
        get_marc(args.marc_code, rows)
    add_purple_line(rows)
    write_rows(rows)
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--marc_code', type=str, default=None, help="MARC station code pair, e.g. 11989-11988")
    parser.add_argument('--metro_code', type=str, default=None, help="Metro station code (CP is E09)")
    args = parser.parse_args()
    main(args)
    
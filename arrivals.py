#!/usr/bin/env python3

from google.transit import gtfs_realtime_pb2
from pathlib import Path
from datetime import datetime, time, timedelta
from threading import Event
import shutil
import signal
import subprocess
import webbrowser
import traceback
import requests
import argparse
import csv
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
4. Filter array to remove trip_ids that realtime has entries for and ones in past
5. Append to realtime array

"""

college_park_nb_id = 12018
college_park_sb_id = 12015
new_carrollton_nb_id = 11989
new_carrollton_sb_id = 11988
penn_nd_id = 12002
penn_sb_id = 11980
marc_name_map = {
    "11958": "Washington",
    "12006": "Baltimore Camden",
    "12008": "Dorsey",
    "12025": "Dorsey",
    "11980": "Baltimore Penn",
    "12002": "Baltimore Penn",
}

schedule_relationship = [
    "scheduled",
    "added",
    "unscheduled",
    "canceled",
    "null",
    "replacement",
    "duplicated",
    "deleted",
]

exit_event = Event()


def exit_handler(signal, frame):
    exit_event.set()


def get_marc_schedule(marc_info, marc_code):
    staton_pair = marc_code.split("-")
    marc_sched = {}
    for trip_id, info_list in marc_info["stop_times"].items():
        service_id = marc_info["trips"][trip_id]["service_id"]
        for info in info_list:
            if info["stop_id"] in staton_pair:
                last_stop = info_list[-1]["stop_id"]
                if last_stop in marc_sched:
                    bisect.insort_right(
                        marc_sched[last_stop],
                        {
                            "arrival_time": info["arrival_time"],
                            "trip_id": trip_id,
                            "service_id": service_id,
                            "realtime": False,
                        },
                        key=(lambda x: x["arrival_time"]),
                    )
                else:
                    marc_sched[last_stop] = [
                        {
                            "arrival_time": info["arrival_time"],
                            "trip_id": trip_id,
                            "service_id": service_id,
                            "realtime": False,
                        }
                    ]
                break  # to next trip_id
    return marc_sched


def service_is_running(marc_info, service_id, dt):
    str_dt = dt.strftime("%Y%m%d")
    if service_id in marc_info["calendar_dates"]:
        for entry in marc_info["calendar_dates"][service_id]:
            # if found in calendar_dates, overrides other info
            if entry["date"] == str_dt:
                return entry["exception_type"] == "1"
    # if date wasn't in this service_id's calendar dates, check regular calendar list
    return bool(int(marc_info["calendar"][service_id][dt.weekday()]))


def get_marcs_for_day(marc_info, marc_sched, dt):
    ret = {}
    for last_stop, sched in marc_sched.items():
        ret[last_stop] = [
            {
                "arrival_time": datetime.combine(
                    dt, time.fromisoformat(x["arrival_time"])
                ),
                "trip_id": x["trip_id"],
                "service_id": x["service_id"],
                "realtime": x["realtime"],
            }
            for x in sched
            if service_is_running(marc_info, x["service_id"], dt)
        ]
    return ret


def get_next_scheduled_marc(marc_info, marc_sched, dt):
    timeout = 7
    while timeout > 0:
        day_sched = get_marcs_for_day(marc_info, marc_sched, dt)
        next_for_day = None
        for times in day_sched.values():  # iterate destinations for day
            next_for_dest = None
            for time in times:  # iterate times for destination
                if time["arrival_time"] > dt:
                    next_for_dest = time["arrival_time"]
                    break
            if not next_for_day or (next_for_dest and next_for_dest < next_for_day):
                next_for_day = next_for_dest
        if next_for_day:
            return next_for_day
        else:
            dt = dt.replace(hour=0, minute=0, second=0)
            dt += timedelta(days=1)  # see if it's running tomorrow
        timeout -= 1
    return None


def get_file_last_modifed(url):
    resp = requests.head(url, allow_redirects=True)
    last_modified = resp.headers["last-modified"]
    return datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z").timestamp()


def download_unpack_zip(url):
    resp = requests.get(url, allow_redirects=True)
    temp_path = Path("./temp.zip")
    with open(temp_path, "wb") as out:
        out.write(resp.content)
    shutil.unpack_archive(temp_path, "mdotmta_gtfs_marc")
    temp_path.unlink()


def decrypt_metro_api():
    subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-d",
            "-pbkdf2",
            "-in",
            "metro_api.enc",
            "-out",
            "metro_api.key",
            "-pass",
            "file:file_key.key",
        ],
        check=True,
    )
    with open("metro_api.key", "r") as infile:
        key = infile.readline().rstrip()
    return key


def parse_marc_gtfs(folder_path):
    marc_info = {}
    for file in Path(folder_path).iterdir():
        marc_info[file.stem] = {}
        # key is unique in these files
        if file.stem in {"routes", "stops", "trips"}:
            with open(file) as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    marc_info[file.stem][list(row.values())[0]] = row
        # just get the list of days
        elif file.stem == "calendar":
            with open(file) as infile:
                reader = csv.reader(infile)
                for row in reader:
                    marc_info[file.stem][row[0]] = row[1:8]
        # key is repeated in these files
        elif file.stem in {"calendar_dates", "stop_times"}:
            with open(file) as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    key = list(row.values())[0]
                    if key in marc_info[file.stem]:
                        marc_info[file.stem][key].append(row)
                    else:
                        marc_info[file.stem][key] = []
    return marc_info


def get_marc_realtime(marc_code, marc_info, marc_sched):
    station_pair = marc_code.split("-")
    dt = datetime.today()
    sched = get_marcs_for_day(marc_info, marc_sched, dt)
    feed = gtfs_realtime_pb2.FeedMessage()
    response = requests.get(
        "https://mdotmta-gtfs-rt.s3.amazonaws.com/MARC+RT/marc-tu.pb"
    )
    feed.ParseFromString(response.content)
    for entity in feed.entity:
        if entity.HasField("trip_update"):
            trip_update = entity.trip_update
            trip_desc = trip_update.trip
            sched_relation = schedule_relationship[trip_desc.schedule_relationship]
            last_stop = list(trip_update.stop_time_update)[-1].stop_id
            if last_stop in sched:  # has realtime update for trip we care about
                if sched_relation == "canceled":
                    # remove from schedule
                    sched[last_stop] = [
                        x for x in sched[last_stop] if x["trip_id"] != trip_desc.trip_id
                    ]
                else:
                    for stu in trip_update.stop_time_update:
                        if stu.stop_id in station_pair and stu.HasField("arrival"):
                            arrival_time = datetime.fromtimestamp(stu.arrival.time)
                            if sched_relation == "scheduled":
                                # replace scheduled time with real time
                                sched[last_stop] = [
                                    (
                                        {
                                            "arrival_time": arrival_time,
                                            "trip_id": x["trip_id"],
                                            "service_id": x["service_id"],
                                            "realtime": True,
                                        }
                                        if x["trip_id"] == trip_desc.trip_id
                                        else x
                                    )
                                    for x in sched[last_stop]
                                ]
                            else:
                                # insert unscheduled time
                                bisect.insort_right(
                                    sched[last_stop],
                                    {
                                        "arrival_time": arrival_time,
                                        "trip_id": trip_desc.trip_id,
                                        "realtime": True,
                                    },
                                    key=(lambda x: x["arrival_time"]),
                                )
    ordered_arr = []
    for dest_id, times in sched.items():
        # remove times that are not within 1-99 minutes away
        filtered_times = [
            x
            for x in times
            if 0 < int((x["arrival_time"] - dt).total_seconds() / 60) < 100
        ]
        if filtered_times:  # not empty
            # sort destinations by which is arriving first
            bisect.insort_right(
                ordered_arr,
                {"dest_id": dest_id, "times": filtered_times},
                key=(lambda x: x["times"][0]["arrival_time"]),
            )
    rows = []
    for entry in ordered_arr:
        dest_name = (
            marc_name_map[entry["dest_id"]]
            if entry["dest_id"] in marc_name_map
            else marc_info["stops"][entry["dest_id"]]["stop_name"]
        )
        minutes_str = ""
        max_times = 2
        for time in entry["times"]:
            if max_times <= 0:
                break
            minutes = int((time["arrival_time"] - dt).total_seconds() / 60)
            if time["realtime"]:
                minutes_str += f"{minutes}, "
            else:
                minutes_str += f"<b><i>{minutes}</i></b>, "
            max_times -= 1
        rows.append(
            f'<div class="service-name"><div class="image-backer"><img src="images/MARC_train.svg.png" class="marc-logo"></div>{dest_name}</div><div class="times">{minutes_str[:-2]}</div>'
        )

    if not rows:  # no trains are coming within the next 99 minutes
        next_marc_time = get_next_scheduled_marc(marc_info, marc_sched, dt)
        if next_marc_time:
            time_str = next_marc_time.strftime("%B %-d at %H:%M")
            rows.append(
                f'<div class="service-name"><div class="image-backer"><img src="images/MARC_train.svg.png" class="marc-logo"></div>Service resumes {time_str}</div>'
            )
    return rows


def get_metro_realtime(code, key):
    url = f"http://api.wmata.com/StationPrediction.svc/json/GetPrediction/{code}?api_key={key}"
    resp = requests.get(url)
    data = resp.json()
    filtered = []
    if "Trains" not in data:
        return []
    for entry in data["Trains"]:
        if (
            "Min" in entry
            and "DestinationName" in entry
            and entry["DestinationName"] not in ["No Passenger", "Train"]
            and entry["Min"] not in ["ARR", "BRD", "DLY", ""]
        ):
            filtered.append(entry)
    by_dest = {}
    for entry in filtered:
        key = entry["DestinationName"]
        if key in by_dest:
            bisect.insort_right(
                by_dest[key], (int(entry["Min"]), entry["Line"]), key=(lambda x: x[0])
            )
        else:
            by_dest[key] = [(int(entry["Min"]), entry["Line"])]
    rows = []
    for key, val in by_dest.items():
        times_str = [x[0] for x in val]
        rows.append(
            f'<div class="service-name"><img src="images/WMATA_Metro_Logo.svg" class="metro-logo"><div class="metro-bullet {val[0][1]}">{val[0][1]}</div>{key}</div><div class="times">{str(times_str[:2])[1:-1]}</div>'
        )
    return rows


def write_rows(rows):
    with open("template.html", "r") as infile:
        template = infile.read()
    for i, row in enumerate(rows):
        template = template.replace(f"Row {i}", row)
    with open("DepartureBoard.html", "w") as outfile:
        outfile.write(template)


def main(args):
    marc_path = "./mdotmta_gtfs_marc"
    try:
        if args.marc_code is not None:
            marc_static_gtfs_url = "https://feeds.mta.maryland.gov/gtfs/marc"
            marc_gtfs_modified = get_file_last_modifed(marc_static_gtfs_url)
            if (
                not Path(marc_path).exists()
                or Path(marc_path).stat().st_mtime < marc_gtfs_modified
            ):
                download_unpack_zip(marc_static_gtfs_url)
            marc_info = parse_marc_gtfs(marc_path)
            marc_sched = get_marc_schedule(marc_info, args.marc_code)
        if args.metro_code is not None:
            metro_key = decrypt_metro_api()
    except Exception:
        print(traceback.format_exc())
        return

    while not exit_event.is_set():
        try:
            metro_rows = []
            marc_rows = []
            # Purple line always gets bottom row
            # MARC gets at most 3
            # Metro gets the rest
            # Blank lines for the rest
            if args.metro_code is not None:
                metro_rows = get_metro_realtime(args.metro_code, metro_key)
            if args.marc_code is not None:
                marc_rows = get_marc_realtime(args.marc_code, marc_info, marc_sched)
            rows = metro_rows[: (5 - len(marc_rows))] + marc_rows[:3]
            blank_row = '<div class="service-name"></div>'
            purple_row = '<div class="service-name"><div class="image-backer"><img src="images/MTA_Purple_Line_logo.svg.png" class="purple-line-logo"></div>Coming 2027</div>'
            rows += [blank_row] * (5 - len(rows))
            rows.append(purple_row)
            write_rows(rows)
            written_html = Path("DepartureBoard.html").absolute()
            if args.webbrowser:
                webbrowser.open(f"file://{written_html}", new=0, autoraise=False)
            if args.refresh > 0:
                exit_event.wait(args.refresh)
            else:
                return
        except Exception:
            print(traceback.format_exc())


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, exit_handler)
    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGHUP, exit_handler)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--marc_code",
        type=str,
        default=None,
        help="MARC station code pair, e.g. 11989-11988",
    )
    parser.add_argument(
        "--metro_code", type=str, default=None, help="Metro station code (CP is E09)"
    )
    parser.add_argument(
        "--refresh",
        type=int,
        default=0,
        help="Seconds between page refresh, 0 is no refresh",
    )
    parser.add_argument(
        "--webbrowser",
        action="store_true",
        default=False,
        help="If the Python Webbrowser library should be used to refresh the page",
    )
    args = parser.parse_args()
    main(args)

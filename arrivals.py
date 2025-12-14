#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime
from threading import Event
from gtfs_helpers import *
import shutil
import signal
import subprocess
import webbrowser
import traceback
import requests
import argparse
import bisect

"""
static GTFS:
routes.txt - maps route_id to route names
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
wmata_college_park_id = "PF_E09_C"
college_park_nb_id = 12018
college_park_sb_id = 12015
new_carrollton_nb_id = 11989
new_carrollton_sb_id = 11988
penn_nd_id = 12002
penn_sb_id = 11980
washington_marc = 11958
marc_name_map = {
    "11958": "Washington",
    "12006": "Baltimore Camden",
    "12008": "Dorsey",
    "12025": "Dorsey",
    "11980": "Baltimore Penn",
    "12002": "Baltimore Penn",
    "11972": "Frederick",
    "11944": "Frederick",
    "11973": "Brunswick",
    "11943": "Brunswick",
    "11940": "Martinsburg",
    "11979": "Martin Airport",
    "12003": "Martin Airport",
    "11976": "Perryville"
}


exit_event = Event()


def exit_handler(signal, frame):
    exit_event.set()


def requester(url, method):
    try:
        if method == "get":
            return requests.get(url, allow_redirects=True, timeout=3)
        elif method == "head":
            return requests.head(url, allow_redirects=True, timeout=3)
        else:
            return None
    except Exception:
        print(traceback.format_exc())
    return None


def download_unpack_zip(url, local_path):
    # default to only downloading the GTFS zip file between daily board startup time and 8 am
    gtfs_modified = datetime.today().replace(hour=8).timestamp()
    resp = requester(url, "head")
    if hasattr(resp, "headers") and "last-modified" in resp.headers:
        last_modified = resp.headers["last-modified"]
        # set to true last-modified time if available
        gtfs_modified = datetime.strptime(
            last_modified, "%a, %d %b %Y %H:%M:%S %Z"
        ).timestamp()
    if (
        not Path(local_path).exists()
        or Path(local_path).stat().st_mtime < gtfs_modified
    ):
        resp = requester(url, "get")
        if resp:
            temp_path = Path("./temp.zip")
            with open(temp_path, "wb") as out:
                out.write(resp.content)
            shutil.unpack_archive(temp_path, local_path)
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


def get_metro_rows(realtime):
    if realtime is None:
        return [
            '<div class="service-name"><img src="images/WMATA_Metro_Logo.svg" class="metro-logo">Network error</div>'
        ]
    data = realtime.json()
    filtered = []
    if "Trains" not in data:
        return []
    for entry in data.get("Trains", []):
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
    metro_path = "./metro_gtfs"
    if args.marc_code:
        marc_static_gtfs_url = "https://feeds.mta.maryland.gov/gtfs/marc"
        download_unpack_zip(marc_static_gtfs_url, marc_path)
        marc_info = read_gtfs_files(marc_path)
        marc_sched = get_gtfs_schedule(marc_info, args.marc_code)

    if args.metro_code:
        metro_key = decrypt_metro_api()
        # metro_static_gtfs_url = (
        #     f"https://api.wmata.com/gtfs/rail-gtfs-static.zip?api_key={metro_key}"
        # )
        # download_unpack_zip(metro_static_gtfs_url, metro_path)
        # metro_info = read_gtfs_files(metro_path)
        # metro_sched = get_gtfs_schedule(metro_info, args.marc_code)

    while not exit_event.is_set():
        metro_resp = None
        marc_resp = None
        if args.metro_code:
            url = f"http://api.wmata.com/StationPrediction.svc/json/GetPrediction/{args.metro_code}?api_key={metro_key}"
            metro_resp = requester(url, "get")
        if args.marc_code:
            url = "https://mdotmta-gtfs-rt.s3.amazonaws.com/MARC+RT/marc-tu.pb"
            marc_resp = requester(url, "get")

        try:
            metro_rows = get_metro_rows(metro_resp)
            marc_arr = combine_realtime_with_sched(
                marc_resp, args.marc_code, marc_info, marc_sched
            )
            marc_rows = []
            for entry in marc_arr:
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
                    minutes = time["arrival_time"]
                    if time["realtime"]:
                        minutes_str += f"{minutes}, "
                    else:
                        minutes_str += f"<b><i>{minutes}</i></b>, "
                    max_times -= 1
                marc_rows.append(
                    f'<div class="service-name"><div class="image-backer"><img src="images/MARC_train.svg.png" class="marc-logo"></div>{dest_name}</div><div class="times">{minutes_str[:-2]}</div>'
                )

            if not marc_rows:  # no trains are coming within the next 99 minutes
                next_marc_time = get_next_scheduled(
                    marc_info, marc_sched, datetime.today()
                )
                if next_marc_time:
                    # time_str = next_marc_time.strftime("%A, %b %-d at %-I:%M %p")
                    time_str = next_marc_time.strftime("%A at %-I:%M %p")
                    marc_rows.append(
                        f'<div class="service-name"><div class="image-backer"><img src="images/MARC_train.svg.png" class="marc-logo"></div></div><div class="times"><i>Resumes {time_str}</i></div>'
                    )

            # Purple line always gets bottom row
            # MARC gets at most 3
            # Metro gets the rest
            # Blank lines for the rest
            rows = metro_rows[: (5 - len(marc_rows))] + marc_rows[:3]
            blank_row = '<div class="service-name"></div>'
            purple_row = '<div class="service-name"><div class="image-backer"><img src="images/MTA_Purple_Line_logo.svg.png" class="purple-line-logo"></div></div><div class="times"><i>Coming 2028</i></div>'
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

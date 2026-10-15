#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime
from threading import Event
from difflib import get_close_matches
from gtfs_helpers import *
from station_names import *
from metro import get_metro_rows
import shutil
import signal
import subprocess
import webbrowser
import traceback
import requests
from requests import Response
import argparse
import bisect
import json
from typing import Optional

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


exit_event = Event()


def exit_handler(signal, frame):
    exit_event.set()


def requester(url: str, method: str, allow_restart: bool) -> Optional[Response]:
    try:
        if method == "get":
            return requests.get(url, allow_redirects=True, timeout=3)
        elif method == "head":
            return requests.head(url, allow_redirects=True, timeout=3)
        else:
            return None
    except Exception:
        if allow_restart:
            exit_event.wait(10)
            try:
                subprocess.run(["sudo", "systemctl", "restart", "NetworkManager"])
            except:
                pass
        else:
            print(traceback.format_exc())
    return None


def download_unpack_zip(url: str, local_path: Path) -> None:
    # default to only downloading the GTFS zip file between daily board startup time and 8 am
    gtfs_modified = datetime.today().replace(hour=8).timestamp()
    resp = requester(url, "head", False)
    if hasattr(resp, "headers") and "last-modified" in resp.headers:
        last_modified = resp.headers["last-modified"]
        # set to true last-modified time if available
        gtfs_modified = datetime.strptime(
            last_modified, "%a, %d %b %Y %H:%M:%S %Z"
        ).timestamp()
    if (
        not local_path.exists()
        or local_path.stat().st_mtime < gtfs_modified
    ):
        resp = requester(url, "get", False)
        if resp:
            temp_path = Path("./temp.zip")
            with open(temp_path, "wb") as out:
                out.write(resp.content)
            shutil.unpack_archive(temp_path, local_path)
            temp_path.unlink()


def decrypt_api_file() -> dict:
    # To encrypt the file, do openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 -in original_keys.json -out api_keys.enc -pass file:file_key.key
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-d", "-pbkdf2", "-in", "api_keys.enc", "-out", "apis_keys.json", "-pass", "file:file_key.key"], check=True)
    with open("api_keys.json", "r") as infile:
        key_file = json.load(infile)
    return key_file


def write_rows(rows):
    with open("template.html", "r") as infile:
        template = infile.read()
    for i, row in enumerate(rows):
        template = template.replace(f"Row {i}", row)
    with open("DepartureBoard.html", "w") as outfile:
        outfile.write(template)


def main(args):
    marc_path = Path("./mdotmta_gtfs_marc")
    marc_static_gtfs_url = "https://feeds.mta.maryland.gov/gtfs/marc"
    shuttle_um_path = Path("./shuttle_um_gtfs")
    shuttle_um_static_gtfs_url = "https://feed.actionfigure.ai/university-of-maryland-shuttle-um.zip"
    api_keys = decrypt_api_file()
    
    if args.shuttle_um:
        download_unpack_zip(shuttle_um_static_gtfs_url, shuttle_um_path)
    if args.marc:
        download_unpack_zip(marc_static_gtfs_url, marc_path)
        marc_gtfs = read_gtfs_files(marc_path)
        marc_sched = get_gtfs_schedule(marc_gtfs, args.marc)

    while not exit_event.is_set():
        metro_resp = None
        marc_resp = None
        if args.metro:
            url = f"http://api.wmata.com/StationPrediction.svc/json/GetPrediction/{args.metro}?api_key={api_keys['metro']}"
            metro_resp = requester(url, "get", args.deploy)
        if args.marc:
            url = "https://mdotmta-gtfs-rt.s3.amazonaws.com/MARC+RT/marc-tu.pb"
            marc_resp = requester(url, "get", args.deploy)

        try:
            metro_rows = get_metro_rows(metro_resp)
            marc_arr = combine_realtime_with_sched(
                marc_resp, args.marc, marc_info, marc_sched
            )
            marc_rows = []
            for entry in marc_arr:
                dest_name = (
                    marc_name_map[entry["dest_id"]]
                    if entry["dest_id"] in marc_name_map
                    else marc_info["stops"][entry["dest_id"]]["stop_name"]
                )
                minutes_str = ""
                max_times = 2  # how many trains to the same destination we'll include
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
                    f'<div class="service-name"><div class="white-backer"><img src="images/MARC_train.svg.png" class="marc-logo"></div>{dest_name}</div><div class="times">{minutes_str[:-2]}</div>'
                )

            if not marc_rows:  # no trains are coming within the next 99 minutes
                now = datetime.today()
                next_marc_time = get_next_scheduled(marc_info, marc_sched, now)
                if next_marc_time:
                    if next_marc_time.day != now.day:
                        time_str = next_marc_time.strftime("Resumes %A")
                    else:
                        time_str = next_marc_time.strftime("Resumes %-I:%M %p")
                    marc_rows.append(
                        f'<div class="service-name"><div class="white-backer"><img src="images/MARC_train.svg.png" class="marc-logo"></div></div><div class="times"><i>{time_str}</i></div>'
                    )

            # Purple line always gets bottom row
            # MARC gets at most 3
            # Metro gets the rest
            # Blank lines for the rest
            rows = metro_rows[: (5 - len(marc_rows[:3]))] + marc_rows[:3]
            blank_row = '<div class="service-name"></div>'
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
        "--marc",
        nargs='*',
        type=int,
        help="MARC station codes, e.g. --marc 11989 11988",
    )
    parser.add_argument(
        "--metro", type=str, default=None, help="Metro station code (CP is E09)"
    )
    parser.add_argument(
        "--shuttle-um",
        nargs='*',
        type=int,
        help="Shuttle-UM station codes, e.g. --shuttle-um 11989 11988",
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
    parser.add_argument(
        "--deploy",
        action="store_true",
        default=False,
        help="If systemctl commands should be allowed to run",
    )
    args = parser.parse_args()
    main(args)

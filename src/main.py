#!/usr/bin/env python3
"""Main file for departure board."""
from typing import Optional
from pathlib import Path
from datetime import datetime
from threading import Event
import shutil
import signal
import subprocess
import traceback
import argparse
import json
import webbrowser
import requests
from requests import Response


from .gtfs_helpers import read_gtfs_files, get_gtfs_schedule
from .metro import get_metro_rows
from .marc import get_marc_rows
from .purple_line import get_purple_line_rows
from .shuttle_um import get_shuttle_um_rows


exit_event = Event()


def exit_handler(_s, _f):
    """Used to break loop with ^C"""
    exit_event.set()


signal.signal(signal.SIGTERM, exit_handler)
signal.signal(signal.SIGINT, exit_handler)
signal.signal(signal.SIGHUP, exit_handler)


def requester(
    url: str, method: str, allow_restart: bool, headers: Optional[dict] = None
) -> Optional[Response]:
    """Fetch the given URL with method, and optionally try to restart the network if it fails"""
    try:
        if method == "get":
            return requests.get(url, allow_redirects=True, timeout=3, headers=headers)
        if method == "head":
            return requests.head(url, allow_redirects=True, timeout=3, headers=headers)
        return None
    except requests.exceptions.RequestException:
        if allow_restart:
            exit_event.wait(10)
            try:
                subprocess.run(
                    ["sudo", "systemctl", "restart", "NetworkManager"], check=False
                )
            except subprocess.SubprocessError:
                pass
        else:
            print(traceback.format_exc())
    return None


def download_unpack_zip(url: str, local_path: Path) -> None:
    """Check if static GTFS files are newer than stored copy, and if so download and unpack them"""
    # default to only downloading the GTFS zip file between daily board startup time and 8 am
    gtfs_modified = datetime.today().replace(hour=8).timestamp()
    resp = requester(url, "head", False)
    if resp and hasattr(resp, "headers") and "last-modified" in resp.headers:
        last_modified = resp.headers["last-modified"]
        # set to true last-modified time if available
        gtfs_modified = datetime.strptime(
            last_modified, "%a, %d %b %Y %H:%M:%S %Z"
        ).timestamp()
    if not local_path.exists() or local_path.stat().st_mtime < gtfs_modified:
        resp = requester(url, "get", False)
        if resp:
            temp_path = Path("./temp.zip")
            with open(temp_path, "wb") as out:
                out.write(resp.content)
            shutil.unpack_archive(temp_path, local_path)
            temp_path.unlink()


def decrypt_api_file() -> dict:
    """Decrypt and load the encrypted json file containing the API keys"""
    # To encrypt the file, do:
    # openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 -in original_keys.json
    # -out api_keys.enc -pass file:file_key.key
    subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-d",
            "-pbkdf2",
            "-iter",
            "100000",
            "-in",
            "api_keys.enc",
            "-out",
            "api_keys.json",
            "-pass",
            "file:file_key.key",
        ],
        check=True,
    )
    with open("api_keys.json", "r", encoding="utf-8") as infile:
        key_file = json.load(infile)
    return key_file


def write_rows(train: list[str], bus: list[str]) -> None:
    """Open the HTML template, fill in the rows, and write to new file"""
    with open("./web/template.html", "r", encoding="utf-8") as infile:
        template = infile.read()
    for i, row in enumerate(train):
        template = template.replace(f"Train {i}", row)
    for i, row in enumerate(bus):
        template = template.replace(f"Bus {i}", row)
    with open("./web/DepartureBoard.html", "w", encoding="utf-8") as outfile:
        outfile.write(template)


# pylint: disable=too-many-locals
def main():
    """Download and parse GTFS files, get and display realtime in a loop"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--marc",
        nargs="*",
        type=int,
        required=True,
        help="MARC station codes, e.g. --marc 11989 11988",
    )
    parser.add_argument(
        "--metro",
        type=str,
        default=None,
        required=True,
        help="Metro station code (CP is E09)",
    )
    parser.add_argument(
        "--shuttle-um",
        nargs="*",
        type=int,
        required=True,
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
    marc_path = Path("../mdotmta_gtfs_marc")
    marc_static_gtfs_url = "https://feeds.mta.maryland.gov/gtfs/marc"
    shuttle_um_path = Path("../shuttle_um_gtfs")
    shuttle_um_static_gtfs_url = (
        "https://feed.actionfigure.ai/university-of-maryland-shuttle-um.zip"
    )
    api_keys = decrypt_api_file()

    # Shuttle-UM
    download_unpack_zip(shuttle_um_static_gtfs_url, shuttle_um_path)
    shuttle_gtfs = read_gtfs_files(shuttle_um_path)
    shuttle_sched = get_gtfs_schedule(shuttle_gtfs, args.shuttle_um)
    # MARC
    download_unpack_zip(marc_static_gtfs_url, marc_path)
    marc_gtfs = read_gtfs_files(marc_path)
    marc_sched = get_gtfs_schedule(marc_gtfs, args.marc)

    while not exit_event.is_set():
        url = (
            f"http://api.wmata.com/StationPrediction.svc/json/GetPrediction/{args.metro}"
            f"?api_key={api_keys['metro']}"
        )
        metro_resp = requester(url, "get", args.deploy)
        url = "https://mdotmta-gtfs-rt.s3.amazonaws.com/MARC+RT/marc-tu.pb"
        marc_resp = requester(url, "get", args.deploy)
        url = "https://api.goswift.ly/real-time/umd-maryland/gtfs-rt-trip-updates"
        shuttle_um_resp = requester(
            url, "get", args.deploy, headers={"Authorization": api_keys["shuttle-um"]}
        )
        now = datetime.today()
        try:
            # Get rows for the train column
            metro_rows = get_metro_rows(metro_resp)
            marc_rows = get_marc_rows(marc_gtfs, marc_sched, args.marc, marc_resp, now)
            purple_row = get_purple_line_rows()[0]

            # Purple line always gets bottom row
            # MARC gets at most 3
            # Metro gets the rest
            # Blank lines for the rest
            train_rows = metro_rows[: (5 - len(marc_rows[:3]))] + marc_rows[:3]
            blank_row = '<div class="service-name"></div>'
            train_rows += [blank_row] * (5 - len(train_rows))
            train_rows.append(purple_row)

            # Get rows for the bus column
            shuttle_rows = get_shuttle_um_rows(
                shuttle_gtfs, shuttle_sched, args.shuttle_um, shuttle_um_resp, now
            )
            bus_rows = shuttle_rows[:6]
            bus_rows += [blank_row] * (6 - len(bus_rows))

            write_rows(train_rows, bus_rows)
            written_html = Path("DepartureBoard.html").absolute()
            if args.webbrowser:
                webbrowser.open(f"file://{written_html}", new=0, autoraise=False)
            if args.refresh > 0:
                exit_event.wait(args.refresh)
            else:
                return
        except Exception:  # pylint: disable=broad-exception-caught
            print(traceback.format_exc())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, time, timedelta
import csv
import bisect


def read_gtfs_files(folder_path):
    gtfs_info = {}
    for file in Path(folder_path).iterdir():
        gtfs_info[file.stem] = {}
        # key is unique in these files
        if file.stem in {"routes", "stops", "trips"}:
            with open(file) as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    # for 'routes', use 'route_id' as the key, etc
                    key = row[file.stem[:-1] + "_id"]
                    gtfs_info[file.stem][key] = row
        # service_id is unique in this file, get list of days of week it's active
        elif file.stem == "calendar":
            with open(file) as infile:
                reader = csv.reader(infile)
                for row in reader:
                    service_id = row[0]
                    gtfs_info[file.stem][service_id] = row[1:8]
        # key is repeated in these files
        elif file.stem in {"calendar_dates", "stop_times"}:
            with open(file) as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    key = (
                        row["trip_id"]
                        if file.stem == "stop_times"
                        else row["service_id"]
                    )
                    if key in gtfs_info[file.stem]:
                        gtfs_info[file.stem][key].append(row)
                    else:
                        gtfs_info[file.stem][key] = []
    return gtfs_info


def get_gtfs_schedule(gtfs_info, stop_ids):
    platform_pair = stop_ids.split("-")  # also works for a single center platform
    gtfs_sched = {}
    for trip_id, info_list in gtfs_info["stop_times"].items():
        service_id = gtfs_info["trips"][trip_id]["service_id"]
        for info in info_list:
            if info["stop_id"] in platform_pair:
                last_stop = info_list[-1]["stop_id"]
                if last_stop not in platform_pair and last_stop in gtfs_sched:
                    bisect.insort_right(
                        gtfs_sched[last_stop],
                        {
                            "arrival_time": info["arrival_time"],
                            "trip_id": trip_id,
                            "service_id": service_id,
                            "realtime": False,
                        },
                        key=(lambda x: x["arrival_time"]),
                    )
                elif last_stop not in platform_pair:
                    gtfs_sched[last_stop] = [
                        {
                            "arrival_time": info["arrival_time"],
                            "trip_id": trip_id,
                            "service_id": service_id,
                            "realtime": False,
                        }
                    ]
                break  # to next trip_id
    return gtfs_sched


def service_is_running(gtfs_info, service_id, dt: datetime.date):
    str_dt = dt.strftime("%Y%m%d")
    for entry in gtfs_info["calendar_dates"].get(service_id, []):
        # if found in calendar_dates, overrides other info
        if entry["date"] == str_dt:
            return entry["exception_type"] == "1"
    # if date wasn't in this service_id's calendar dates, check regular calendar list
    else:
        if service_id in gtfs_info.get("calendar", {}):
            return gtfs_info["calendar"][service_id][dt.weekday()] == "1"
        else:
            return True


def get_next_scheduled(gtfs_info, gtfs_sched, dt: datetime.datetime):
    timeout = 7
    while timeout > 0:
        day_sched = get_sched_for_day(gtfs_info, gtfs_sched, dt.date())
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
        else:  # see if it's running tomorrow
            dt = dt.replace(hour=0, minute=0, second=0) + timedelta(days=1)
        timeout -= 1
    return None


def get_sched_for_day(gtfs_info, gtfs_sched, dt: datetime.date):
    ret = {}
    for last_stop, sched in gtfs_sched.items():
        ret[last_stop] = [
            {
                "arrival_time": datetime.combine(dt, time())
                + timedelta(  # cannot use builtins for this since GTFS may have arrival time > 24 hours
                    hours=int(x["arrival_time"].split(":")[0]),
                    minutes=int(x["arrival_time"].split(":")[1]),
                    seconds=int(x["arrival_time"].split(":")[2]),
                ),
                "trip_id": x["trip_id"],
                "service_id": x["service_id"],
                "realtime": x["realtime"],
            }
            for x in sched
            if service_is_running(gtfs_info, x["service_id"], dt)
        ]
    return ret

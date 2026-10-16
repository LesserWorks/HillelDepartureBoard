#!/usr/bin/env python3
from google.transit import gtfs_realtime_pb2
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Optional
import csv
import copy
import bisect
from requests import Response

schedule_relationship = [
    "scheduled",
    "added",
    "unscheduled",
    "canceled",
    "null",
    "replacement",
    "duplicated",
    "deleted",
    "new"
]


def read_gtfs_files(folder_path: Path) -> dict[str, dict[str, dict]]:
    """Parse static GTFS files into a dict"""
    gtfs_info = {}
    for file in folder_path.iterdir():
        gtfs_info[file.stem] = {} # make a dict for each GTFS file
        # key is unique in these files
        if file.stem in {"routes", "stops", "trips"}:
            # for 'routes.txt', use 'route_id' as the key, etc
            id_name = file.stem[:-1] + "_id"
            with open(file) as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    key = row[id_name] # get the particular route_id, stop_id, etc
                    gtfs_info[file.stem][key] = row # save whole row
        # service_id is unique in this file, get list of days of week it's active and applicable dates
        elif file.stem == "calendar":
            with open(file) as infile:
                reader = csv.reader(infile)
                for row in reader:
                    service_id = row[0]
                    gtfs_info[file.stem][service_id] = row[1:10]
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
                        gtfs_info[file.stem][key] = [row]
    return gtfs_info


def get_gtfs_schedule(gtfs_info: dict, stop_ids: list[int]) -> dict[str, dict[str, str]]:
    """Get the GTFS schedule for the given stop IDs"""
    # Produces a dict mapping trip ID to its arrival time at the given stop and its last stop
    gtfs_sched = {}
    # Iterate every trip listed in stop_times
    for trip_id, stop_list in gtfs_info["stop_times"].items():
        last_stop = stop_list[-1]["stop_id"]
        # Don't care about trips that terminate at the given stop IDs
        if trip_id in gtfs_info["trips"] and int(last_stop) not in stop_ids:
            # get service_id for this trip
            service_id = gtfs_info["trips"][trip_id]["service_id"]
            for stop_info in stop_list:
                # See if this trip reaches a stop ID we care about
                if int(stop_info["stop_id"]) in stop_ids:
                    gtfs_sched[trip_id] = {
                        "departure_time": stop_info["departure_time"],
                        "service_id": service_id,
                        "last_stop": last_stop
                    }
                    break  # to next trip_id
    return gtfs_sched


def service_is_running(gtfs_info: dict, service_id: str, dt: datetime.date) -> bool:
    """Return True if the given service_id is running on the given date"""
    dates_for_service = gtfs_info.get("calendar_dates", {}).get(service_id, [])
    for date in dates_for_service:
        applies_date = datetime.date.strptime(date["date"], "%Y%m%d")
        # if found in calendar_dates, overrides other info
        if applies_date == dt:
            # 1 means service added, 2 is service removed
            return date["exception_type"] == "1"
    # if date wasn't in this service_id's calendar dates, check regular calendar list
    else:
        if service_id in gtfs_info.get("calendar", {}):
            start_date = datetime.date.strptime(gtfs_info["calendar"][service_id][8], "%Y%m%d")
            end_date = datetime.date.strptime(gtfs_info["calendar"][service_id][9], "%Y%m%d")
            return start_date <= dt <= end_date and gtfs_info["calendar"][service_id][dt.weekday()] == "1"
        else:
            return True

def get_sched_for_day(gtfs_info: dict, gtfs_sched: dict, dt: datetime.date) -> dict[str, dict]:
    """Produce a filtered GTFS schedule with only services running on the given day"""
    ret = {}
    for trip_id, trip_info in gtfs_sched.items():
        # only add trips whose service is running on the given day
        if service_is_running(gtfs_info, trip_info["service_id"], dt):
            hrs, mins, secs = trip_info["departure_time"].split(":")
            ret[trip_id] = {
                "departure_time": datetime.combine(dt, time())
                + timedelta(  # cannot use builtins for this since GTFS may have departure time > 24 hours
                    hours=int(hrs),
                    minutes=int(mins),
                    seconds=int(secs),
                ),
                "last_stop": trip_info["last_stop"],
                "realtime": False, # until realtime data updates it
            }
    return ret


# TODO break into combine_realtime and get_sorted_soon_arrivals
def combine_realtime_with_sched(realtime: Optional[Response], stop_ids: list[int], today_sched: dict) -> dict[str, dict]:
    sched = copy.deepcopy(today_sched) # copy cause we're going to modify it
    if realtime:
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(realtime.content)
        # iterate objects in protobuf
        for entity in feed.entity:
            if entity.HasField("trip_update"):
                trip_update = entity.trip_update
                stop_updates = list(trip_update.stop_time_update)
                trip_desc = trip_update.trip
                sched_relation = schedule_relationship[trip_desc.schedule_relationship]
                trip_id = trip_desc.trip_id
                
                if trip_id in sched:
                    if sched_relation in ["canceled", "deleted"]:
                        # remove from schedule
                        del sched[trip_id]
                    # TODO: doesn't cover case of new trip ID not on schedule for that day
                    else:
                        last_stop = stop_updates[-1].stop_id if len(stop_updates) >= 1 else sched[trip_id]["last_stop"]
                        for stu in trip_update.stop_time_update:
                            if int(stu.stop_id) in stop_ids and stu.HasField("departure"):
                                dept_time = datetime.fromtimestamp(stu.departure.time)
                                sched[trip_id] = {
                                    "departure_time": dept_time,
                                    "last_stop": last_stop,
                                    "realtime": True
                                }
    return sched


def filter_and_sort(sched: dict, now: datetime) -> list[tuple[str, list[dict]]]:
    """Convert schedule to 2D list sorting trains by destination and arriving soon enough"""
    
    # First filter and sort train per destination
    by_dest = {}
    for _, trip_info in sched.items():
        # Note that -(x // -60) does ceiling division,
        # so trains that are less than a minute away round up to 1
        minutes_away = int(-((trip_info["departure_time"] - now).total_seconds() // -60))
        if 0 < minutes_away < 100:
            if trip_info["last_stop"] in by_dest:
                bisect.insort_right(by_dest[trip_info["last_stop"]], {
                    "minutes_away": minutes_away,
                    "realtime": trip_info["realtime"]
                }, key=(lambda x: x["minutes_away"]))
            else:
                by_dest[trip_info["last_stop"]] = [{"minutes_away": minutes_away, "realtime": trip_info["realtime"]}]
    
    # Next sort the destinations by whose train is departing first
    ordered_arr = []
    for dest, departures in by_dest.items():
        bisect.insort_right(ordered_arr, (dest, departures), key=(lambda x: x[1][0]["minutes_away"]))
            
    return ordered_arr

def get_next_scheduled(gtfs_info, gtfs_sched, now: datetime):
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

#!/usr/bin/env python3
"""Many helper functions to parse static GTFS files,
and combine them with realtime GTFS feed info"""
from pathlib import Path
from datetime import datetime, time, timedelta, date
from typing import Optional
import csv
import copy
import bisect
from requests import Response
from google.transit import gtfs_realtime_pb2  # type: ignore[import-untyped]

schedule_relationship = [
    "scheduled",
    "added",
    "unscheduled",
    "canceled",
    "null",
    "replacement",
    "duplicated",
    "deleted",
    "new",
]


def read_gtfs_files(folder_path: Path) -> dict[str, dict]:
    """Parse static GTFS files into a dict"""
    gtfs_info: dict[str, dict] = {}
    for file in folder_path.iterdir():
        gtfs_info[file.stem] = {}  # make a dict for each GTFS file
        # key is unique in these files
        if file.stem in {"routes", "stops", "trips"}:
            # for 'routes.txt', use 'route_id' as the key, etc
            id_name = file.stem[:-1] + "_id"
            with open(file, encoding="utf-8") as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    key = row[id_name]  # get the particular route_id, stop_id, etc
                    gtfs_info[file.stem][key] = row  # save whole row
        # service_id is unique in this file,
        # so get list of days of week it's active and applicable dates
        elif file.stem == "calendar":
            with open(file, encoding="utf-8") as infile:
                line_reader = csv.reader(infile)
                for line in line_reader:
                    service_id = line[0]
                    gtfs_info[file.stem][service_id] = line[
                        1:
                    ]  # everything but service ID
        # key is repeated in these files
        elif file.stem in {"calendar_dates", "stop_times"}:
            with open(file, encoding="utf-8") as infile:
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


def get_gtfs_schedule(
    gtfs_info: dict, stop_ids: list[int]
) -> dict[str, dict[str, str]]:
    """Get the GTFS schedule for the given stop IDs"""
    # Produces a dict mapping trip ID to its arrival time at the given stop and its last stop
    gtfs_sched = {}
    # Iterate every trip listed in stop_times
    for trip_id, stop_list in gtfs_info["stop_times"].items():
        last_stop = stop_list[-1]["stop_id"]
        # Don't care about trips that terminate at the given stop IDs
        if trip_id in gtfs_info["trips"] and int(last_stop) not in stop_ids:
            for stop_info in stop_list:
                # See if this trip reaches a stop ID we care about
                if int(stop_info["stop_id"]) in stop_ids:
                    # get service_id and route_id for this trip
                    service_id = gtfs_info["trips"][trip_id]["service_id"]
                    route_id = gtfs_info["trips"][trip_id]["route_id"]
                    gtfs_sched[trip_id] = {
                        "departure_time": stop_info["departure_time"],
                        "service_id": service_id,
                        "route_id": route_id,
                        "last_stop": last_stop,
                    }
                    break  # to next trip_id
    return gtfs_sched


def service_is_running(gtfs_info: dict, service_id: str, dt: date) -> bool:
    """Return True if the given service_id is running on the given date"""
    dates_for_service = gtfs_info.get("calendar_dates", {}).get(service_id, [])
    for service_entry in dates_for_service:
        applies_date = datetime.strptime(service_entry["date"], "%Y%m%d")
        # if found in calendar_dates, overrides other info
        if applies_date == dt:
            # 1 means service added, 2 is service removed
            return service_entry["exception_type"] == "1"
    # if date wasn't in this service_id's calendar dates, check regular calendar list
    if service_id in gtfs_info.get("calendar", {}):
        start_date = datetime.strptime(gtfs_info["calendar"][service_id][7], "%Y%m%d")
        end_date = datetime.strptime(gtfs_info["calendar"][service_id][8], "%Y%m%d")
        return (
            start_date.date() <= dt <= end_date.date()
            and gtfs_info["calendar"][service_id][dt.weekday()] == "1"
        )
    return True


def get_sched_for_day(gtfs_info: dict, gtfs_sched: dict, dt: date) -> dict[str, dict]:
    """Produce a filtered GTFS schedule with only services running on the given day"""
    ret = {}
    for trip_id, trip_info in gtfs_sched.items():
        # only add trips whose service is running on the given day
        if service_is_running(gtfs_info, trip_info["service_id"], dt):
            hrs, mins, secs = trip_info["departure_time"].split(":")
            ret[trip_id] = {
                # cannot use builtins for this since GTFS may have departure time > 24 hours
                "departure_time": datetime.combine(dt, time())
                + timedelta(
                    hours=int(hrs),
                    minutes=int(mins),
                    seconds=int(secs),
                ),
                "last_stop": trip_info["last_stop"],
                "route_id": trip_info["route_id"],
                "realtime": False,  # until realtime data updates it
            }
    return ret


# pylint: disable=too-many-nested-blocks
def combine_realtime_with_sched(
    realtime: Optional[Response], stop_ids: list[int], today_sched: dict
) -> dict[str, dict]:
    """Update the static GTFS schedule copy with realtime information"""
    sched = copy.deepcopy(today_sched)  # copy cause we're going to modify it
    if realtime:
        feed = gtfs_realtime_pb2.FeedMessage()  # pylint: disable=no-member
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
                        last_stop = (
                            stop_updates[-1].stop_id
                            if len(stop_updates) >= 1
                            else sched[trip_id]["last_stop"]
                        )
                        for stu in trip_update.stop_time_update:
                            if int(stu.stop_id) in stop_ids and (
                                stu.HasField("departure") or stu.HasField("arrival")
                            ):
                                used_time = (
                                    datetime.fromtimestamp(stu.departure.time)
                                    if stu.HasField("departure")
                                    else datetime.fromtimestamp(stu.arrival.time)
                                )
                                sched[trip_id] = {
                                    "departure_time": used_time,
                                    "last_stop": last_stop,
                                    "route_id": sched[trip_id]["route_id"],
                                    "realtime": True,
                                }
                                break  # to next trip_id
    return sched


def filter_and_sort(
    sched: dict, first_index: str, now: datetime
) -> list[tuple[str, list[dict]]]:
    """Filter schedule for those arriving soon enough
    and transform into 2D array index by given field"""

    # First filter and sort arrivals within each top-level category
    by_dest: dict[str, list[dict]] = {}
    for _, trip_info in sched.items():
        # Note that -(x // -60) does ceiling division,
        # so trains that are less than a minute away round up to 1
        minutes_away = int(
            -((trip_info["departure_time"] - now).total_seconds() // -60)
        )
        if 0 < minutes_away < 100:
            if trip_info[first_index] in by_dest:
                bisect.insort_right(
                    by_dest[trip_info[first_index]],
                    {"minutes_away": minutes_away, "realtime": trip_info["realtime"]},
                    key=(lambda x: x["minutes_away"]),
                )
            else:
                by_dest[trip_info[first_index]] = [
                    {"minutes_away": minutes_away, "realtime": trip_info["realtime"]}
                ]

    # Next sort the destinations by whose train is departing first
    ordered_arr: list[tuple[str, list[dict]]] = []
    for top_level, departures in by_dest.items():
        bisect.insort_right(
            ordered_arr,
            (top_level, departures),
            key=(lambda x: x[1][0]["minutes_away"]),
        )

    return ordered_arr


def get_next_scheduled(gtfs_info: dict, gtfs_sched: dict, now: datetime):
    """Get the datetime of the next arrival within the next 7 days"""
    timeout = 7  # during the next 7 days
    while timeout > 0:
        day_sched = get_sched_for_day(gtfs_info, gtfs_sched, now.date())
        next_for_day = None
        for _, trip_info in day_sched.items():
            this_trip_dept = trip_info["departure_time"]
            if this_trip_dept > now and (
                not next_for_day or this_trip_dept < next_for_day
            ):
                next_for_day = this_trip_dept
        if next_for_day:
            return next_for_day
        # see if it's running tomorrow (does not modify copy held by caller)
        now = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
        timeout -= 1
    return None

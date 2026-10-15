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
                        gtfs_info[file.stem][key] = [row]
    return gtfs_info

# TODO change this to return schedule based on trip id, not destination
def get_gtfs_schedule(gtfs_info: dict, stop_ids: list[int]) -> dict[str, list[dict]]:
    """Get the GTFS schedule for the given stop IDs"""
    # Produces a dict mapping mapping the destination stop to a list of arrival times at the given stop IDs for trains heading to that destination stop
    gtfs_sched = {}
    # Iterate every trip listed in stop_times
    for trip_id, stop_list in gtfs_info["stop_times"].items():
        if trip_id in gtfs_info["trips"]:
            # get service_id for this trip
            service_id = gtfs_info["trips"][trip_id]["service_id"]
            for stop_info in stop_list:
                # See if this trip reaches a stop ID we care about
                if int(stop_info["stop_id"]) in stop_ids:
                    last_stop = stop_list[-1]["stop_id"]
                    # Don't care about trips that terminate at the given stop IDs
                    if int(last_stop) not in stop_ids:
                        if last_stop in gtfs_sched:
                            bisect.insort_right(
                                gtfs_sched[last_stop],
                                {
                                    "arrival_time": stop_info["arrival_time"], # string, not datetime
                                    "trip_id": trip_id,
                                    "service_id": service_id,
                                    "realtime": False,
                                },
                                key=(lambda x: x["arrival_time"]),
                            )
                        else:
                            gtfs_sched[last_stop] = [
                                {
                                    "arrival_time": stop_info["arrival_time"],
                                    "trip_id": trip_id,
                                    "service_id": service_id,
                                    "realtime": False,
                                }
                            ]
                    break  # to next trip_id
    return gtfs_sched


def service_is_running(gtfs_info: dict, service_id: str, dt: datetime.date) -> bool:
    """Return True if the given service_id is running on the given date"""
    str_dt = dt.strftime("%Y%m%d") # get date in format used by GTFS files
    dates_for_service = gtfs_info.get("calendar_dates", {}).get(service_id, [])
    for date in dates_for_service:
        # if found in calendar_dates, overrides other info
        if date["date"] == str_dt:
            # 1 means service added, 2 is service removed
            return date["exception_type"] == "1"
    # if date wasn't in this service_id's calendar dates, check regular calendar list
    else: # TODO take into account start and end dates of calendar.txt
        if service_id in gtfs_info.get("calendar", {}):
            return gtfs_info["calendar"][service_id][dt.weekday()] == "1"
        else:
            return True

def get_sched_for_day(gtfs_info: dict, gtfs_sched: dict, dt: datetime.date) -> dict[str, list[dict]]:
    """Produce a copy of the full GTFS schedule with only services running on the given day"""
    ret = {}
    for last_stop, arrivals in gtfs_sched.items():
        ret[last_stop] = [
            {
                # set arrival_time as datetime instead of string
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
            for x in arrivals
            # only include trips that are supposed to be running that day
            if service_is_running(gtfs_info, x["service_id"], dt)
        ]
    return ret


# TODO break into combine_realtime and get_sorted_soon_arrivals
def combine_realtime_with_sched(realtime: Optional[Response], stop_ids: list[int], gtfs_info: dict, today_sched: dict) -> list[dict]:
    if not stop_ids:
        return []
    dt = datetime.today()
    sched = copy.deepcopy(today_sched) # copy cause we're going to modify it
    
    if realtime:
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(realtime.content)
        # iterate objects in protobuf
        for entity in feed.entity:
            if entity.HasField("trip_update"):
                trip_update = entity.trip_update
                trip_desc = trip_update.trip
                sched_relation = schedule_relationship[trip_desc.schedule_relationship]
                stop_updates = list(trip_update.stop_time_update)
                last_stop = stop_updates[-1].stop_id if len(stop_updates) >= 1 else None
                if last_stop in sched:  # has realtime update for trip we care about
                    if sched_relation == "canceled":
                        # remove from schedule
                        sched[last_stop] = [
                            x
                            for x in sched[last_stop]
                            if x["trip_id"] != trip_desc.trip_id
                        ]
                    else: # normal or added trip update
                        # TODO doesn't handle case where added trip has different destination than sched
                        for stu in trip_update.stop_time_update:
                            if int(stu.stop_id) in stop_ids and (
                                stu.HasField("arrival") or stu.HasField("departure")
                            ):
                                # Use arrival time unless it's the origin station, in which case we use departure
                                if stu.HasField("arrival"):
                                    used_time = datetime.fromtimestamp(stu.arrival.time)
                                else:
                                    used_time = datetime.fromtimestamp(
                                        stu.departure.time
                                    )
                                if sched_relation == "scheduled":
                                    # replace scheduled time with real time
                                    sched[last_stop] = [
                                        ( # copy arrival time list except change time to realtime
                                            {
                                                "arrival_time": used_time,
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
                                            "arrival_time": used_time,
                                            "trip_id": trip_desc.trip_id,
                                            "realtime": True,
                                        },
                                        key=(lambda x: x["arrival_time"]),
                                    )
    # convert from schedule dict to list of dicts where the dicts are sorted by the soonest arrival time
    ordered_arr = []
    for dest_id, times in sched.items():
        # Remove times that are not within 1-99 minutes away
        # Note that -(x // -60) does ceiling division,
        # so trains that are less than a minute away round up to 1
        filtered_times = [
            {
                "arrival_time": int(-((x["arrival_time"] - dt).total_seconds() // -60)),
                "realtime": x["realtime"],
            }
            for x in times
            if 0 < int(-((x["arrival_time"] - dt).total_seconds() // -60)) < 100
        ]
        if filtered_times:  # not empty
            # sort destinations by which is arriving first
            bisect.insort_right(
                ordered_arr,
                {"dest_id": dest_id, "times": filtered_times},
                key=(lambda x: x["times"][0]["arrival_time"]),
            )
    return ordered_arr

def get_next_scheduled(gtfs_info, gtfs_sched, dt: datetime):
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

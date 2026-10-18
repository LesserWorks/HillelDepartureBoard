"""Calls standard GTFS functions to generate HTML rows for Shuttle-UM departures"""

from typing import Optional
from datetime import datetime
from requests import Response
from .gtfs_helpers import (
    get_sched_for_day,
    combine_realtime_with_sched,
    filter_and_sort,
    get_next_scheduled,
)


# pylint: disable=duplicate-code disable=too-many-locals
def get_shuttle_um_rows(
    gtfs_info: dict,
    gtfs_sched: dict,
    stop_ids: list[int],
    realtime: Optional[Response],
    now: datetime,
) -> list[str]:
    """Parse realtime data into HTML rows"""
    today_sched = get_sched_for_day(gtfs_info, gtfs_sched, now.date())
    with_realtime = combine_realtime_with_sched(realtime, stop_ids, today_sched)
    fully_sorted = filter_and_sort(with_realtime, "route_id", now)

    rows = []
    if fully_sorted:
        for route_id, departures in fully_sorted:
            max_depts = 2
            dept_str = ""
            for idx, dept in enumerate(departures[:max_depts]):
                style_str = "rt" if dept["realtime"] else "sc"
                comma_str = (
                    ", " if idx + 1 < max_depts and idx + 1 < len(departures) else ""
                )
                dept_str += f'<span class="{style_str}">{dept["minutes_away"]}{comma_str}</span>'
            rows.append(
                f'<div class="service-name">{route_id}</div><div>{dept_str}</div>'
            )
    else:  # No buses soon
        next_time = get_next_scheduled(gtfs_info, gtfs_sched, now)
        if next_time:
            if next_time.day == now.day:
                time_str = next_time.strftime("%-I:%M %p")  # Resumes 5:22 PM
            else:
                time_str = next_time.strftime("%A")  # Resumes Monday
            rows.append(
                '<div class="service-name"><span class="sc">Resumes</span></div>'
            )
            rows.append(
                f'<div class="service-name"><span class="sc">{time_str}</span></div>'
            )
    return rows

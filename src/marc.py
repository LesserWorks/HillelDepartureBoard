"""Calls standard GTFS functions to generate HTML rows for MARC departures"""

from typing import Optional
from datetime import datetime
from requests import Response
from .gtfs_helpers import (
    get_sched_for_day,
    combine_realtime_with_sched,
    filter_and_sort,
    get_next_scheduled,
)
from .station_names import marc_name_map


# pylint: disable=too-many-locals
def get_marc_rows(
    gtfs_info: dict,
    gtfs_sched: dict,
    stop_ids: list[int],
    realtime: Optional[Response],
    now: datetime,
) -> list[str]:
    """Parse realtime data into HTML rows"""
    today_sched = get_sched_for_day(gtfs_info, gtfs_sched, now.date())
    with_realtime = combine_realtime_with_sched(realtime, stop_ids, today_sched)
    fully_sorted = filter_and_sort(with_realtime, "last_stop", now)

    rows = []
    if fully_sorted:
        for dest_id, departures in fully_sorted:
            dest_name = marc_name_map.get(
                dest_id, gtfs_info["stops"][dest_id]["stop_name"]
            )

            max_depts = 2
            dept_str = ""
            for idx, dept in enumerate(departures[:max_depts]):
                style_str = "rt" if dept["realtime"] else "sc"
                comma_str = (
                    ", " if idx + 1 < max_depts and idx + 1 < len(departures) else ""
                )
                dept_str += f'<span class="{style_str}">{dept["minutes_away"]}{comma_str}</span>'
            rows.append(
                f'<div class="service-name"><div class="white-backer">'
                '<img src="../images/MARC_train.svg.png" class="marc-logo">'
                f"</div>{dest_name}</div>"
                f"<div>{dept_str}</div>"
            )
    else:  # No trains soon
        next_time = get_next_scheduled(gtfs_info, gtfs_sched, now)
        if next_time:
            if next_time.day == now.day:
                time_str = next_time.strftime("Resumes %-I:%M %p")  # Resumes 5:22 PM
            else:
                time_str = next_time.strftime("Resumes %A")  # Resumes Monday
            rows.append(
                f'<div class="service-name"><div class="white-backer">'
                '<img src="../images/MARC_train.svg.png" class="marc-logo"></div></div>'
                f'<div><span class="sc">{time_str}</span></div>'
            )
    return rows

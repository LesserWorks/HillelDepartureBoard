from typing import Optional
from datetime import datetime
from requests import Response
from gtfs_helpers import get_sched_for_day, combine_realtime_with_sched, filter_and_sort, get_next_scheduled
from station_names import marc_name_map

def get_marc_rows(gtfs_info: dict, gtfs_sched: dict, stop_ids: list[int], realtime: Optional[Response], now: datetime) -> list[str]:
    today_sched = get_sched_for_day(gtfs_info, gtfs_sched, now.date())
    with_realtime = combine_realtime_with_sched(realtime, stop_ids, today_sched)
    fully_sorted = filter_and_sort(with_realtime, now)

    rows = []
    if fully_sorted:
        for dest_id, departures in fully_sorted:
            if dest_id in marc_name_map:
                dest_name = marc_name_map[dest_id]
            else:
                dest_name = gtfs_info["stops"][dest_id]["stop_name"]

            max_depts = 2
            dept_str = ""
            for idx, dept in enumerate(departures[:max_depts]):
                style_str = "rt" if dept["realtime"] else "sc"
                comma_str = ", " if idx + 1 == max_depts or idx + 1 == len(departures) else ""
                dept_str += f'<span class="{style_str}">{dept["minutes_away"]}{comma_str}</span>'
            rows.append(
                f'<div class="service-name"><div class="white-backer"><img src="../images/MARC_train.svg.png" class="marc-logo"></div>{dest_name}</div>'
                f'<div>{dept_str}</div>'
            )
    else: # No trains soon
        # TODO get next scheduled
        pass
    return rows
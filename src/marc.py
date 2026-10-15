from gtfs_helpers import combine_realtime_with_sched

def get_marc_rows(gtfs_info: dict, gtfs_sched: dict, realtime: Optional[Response]) -> list[str]:
    with_realtime = combine_realtime_with_sched()
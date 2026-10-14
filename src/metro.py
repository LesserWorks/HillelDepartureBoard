import bisect
from typing import Optional
from requests import Response
from difflib import get_close_matches
from station_names import wmata_name_map

def translate_station_name(name: str) -> str:
    translated_name = get_close_matches(name, wmata_name_map.keys(), n=1, cutoff=0.6)
    if translated_name:
        return wmata_name_map[translated_name[0]]
    else:
        return name

def get_metro_rows(realtime: Optional[Response]) -> list[str]:
    if not realtime:
        return [
            '<div class="service-name"><img src="../images/WMATA_Metro_Logo.svg" class="metro-logo">Network error</div>'
        ]
    data = realtime.json() # The realtime data is already sorted by soonest to latest

    # Filter out entries that are too soon or not clear what line they are
    filtered = []
    for entry in data.get("Trains", []):
        if (
            "Min" in entry
            and "DestinationName" in entry
            and entry["DestinationName"] not in ["No Passenger", "Train"]
            and entry["Min"] not in ["ARR", "BRD", "DLY", ""]
        ):
            filtered.append(entry)
    
    # Make dict mapping destination to sorted list of arrivals for that destination
    # Each list element is tuple of (minutes, line_color)
    by_dest = {}
    for entry in filtered:
        dest = translate_station_name(entry["DestinationName"])
        if dest in by_dest: # destination already exists
            bisect.insort_right(
                by_dest[dest], (entry["Min"], entry["Line"]), key=(lambda x: int(x[0]))
            )
        else: # first entry for this destination
            by_dest[dest] = [(entry["Min"], entry["Line"])]
    
    # Write HTML rows for each destination
    # Python dicts are "sorted" by insertion order
    rows = []
    for dest, arrivals in by_dest.items():
        # Get just list of arrival minutes
        line_color = arrivals[0][1]
        next_two = [arrival[0] for arrival in arrivals[:2]]
        
        rows.append(
            f'<div class="service-name"><div class="clear-backer"><img src="../images/WMATA_Metro_Logo.svg" class="metro-logo">'
            f'<div class="metro-bullet {line_color}">{line_color}</div></div>{dest}</div>'
            f'<div><span class="rt">{", ".join(next_two)}</span></div>'
        )
    if not by_dest: # No trains
        rows.append(
            '<div class="service-name"><img src="../images/WMATA_Metro_Logo.svg" class="metro-logo">None found</div>'
        )
    return rows



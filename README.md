# HillelDepartureBoard
In the morning, crontab calls reboot, and kiosk.service will start automatically on reboot.
This service executes HillelDepartureBoard/start.sh, which in turn updates crontab and starts the script and browser.
The service unit file is at /lib/systemd/system/kiosk.service.

In the evening, crontab stops the service, turns off the screen, and does git pull.

Helpful station codes:
wmata_college_park_id = "PF_E09_C"
college_park_nb_id = 12018
college_park_sb_id = 12015
new_carrollton_nb_id = 11989
new_carrollton_sb_id = 11988
penn_nd_id = 12002
penn_sb_id = 11980
washington_marc = 11958



During track work but not shutdown on silver line, saw this
stop id PF_N12_C sched 0 time 1969-12-31 19:00:00
stop id PF_N11_C sched 0 time 2025-12-07 22:23:52
stop id PF_N10_C sched 0 time 2025-12-07 22:29:13
stop id PF_N09_C sched 0 time 2025-12-07 22:33:18
stop id PF_N08_C sched 0 time 2025-12-07 22:36:30
stop id PF_N07_C sched 0 time 2025-12-07 22:39:08
stop id PF_N06_C sched 0 time 2025-12-07 22:41:27
stop id PF_N04_C sched 0 time 2025-12-07 22:49:14
stop id PF_N03_C sched 0 time 2025-12-07 22:51:12
stop id PF_N02_C sched 0 time 2025-12-07 22:53:15
stop id PF_N01_C sched 0 time 2025-12-07 22:55:09
stop id PF_K05_C sched 1 time 1969-12-31 19:00:00
stop id PF_K04_1 sched 1 time 1969-12-31 19:00:00
stop id PF_K03_1 sched 1 time 1969-12-31 19:00:00
stop id PF_K02_1 sched 1 time 1969-12-31 19:00:00
stop id PF_K01_C sched 1 time 1969-12-31 19:00:00
stop id PF_C05_1 sched 1 time 1969-12-31 19:00:00
stop id PF_C04_C sched 1 time 1969-12-31 19:00:00
stop id PF_C03_1 sched 1 time 1969-12-31 19:00:00
stop id PF_C02_1 sched 1 time 1969-12-31 19:00:00

The text for sched 1 was SKIPPED. When I watched the train live, it continued to NewC as normal and later GTFS gets returned the full schedule

For Green line trains during the shutdown of CP and Greenbelt, the stop time updates simply didn't include CP and Greenbelt at all and all the sched relation was normal.
In the trips.txt, there were a bunch of trips with Hyatsville Crossing as the headsign
stop_times.txt also had the trip simply not going past hyattsville at all.
Seemingly because metro says their static GTFS is updated daily.
However stop_times.txt and trips.txt still had the trips with included the closed stations still there.

Seems that DestinationName for New Carrollton changes from N Carrollton to NewCrlton between K04 and K03 (Ballston, Virginia Sq)
Exit fullscreen with Alt-F4

Check if marc is correct for origin station cause I didn't see it switch to realtime after scheduled went to 1 min
- Yeah it appears the realtime marc doesn't include the origin station unit it's departed

trips.txt:      trip_id,            route_id,service_id,trip_headsign,trip_short_name
For MARC:       Train400,           11705,   101P,      BALTIMORE,    Train 400
For Shuttle-UM: 104_B1_express_2230,104,     FA26B1

routes.txt:     route_id,agency_id,route_short_name,route_long_name
For MARC:       11704,   30034,    MARC,            BRUNSWICK - WASHINGTON
For Shuttle-UM: 104,     1653,     104,             College Park Metro Station

# HillelDepartureBoard
In the morning, crontab calls reboot, and kiosk.service will start automatically on reboot.
This service executes HillelDepartureBoard/start.sh, which in turn updates crontab and starts the script and browser.
The service unit file is at /lib/systemd/system/kiosk.service.

In the evening, crontab stops the service, turns off the screen, and does git pull.

To do:

Replace metro feed with GTFS feed

Change background image on Pi

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
Seemingly becuase metro says their static GTFS is updated daily.
However stop_times.txt and trips.txt still had the trips with included the closed stations still there.

Exit fullscreen with Alt-F4

Todo:
Seems that requester() try catch doesn't always catch domain name resolution failures?
Try sudo systemctl restart NetworkManager
It worked in a test python scripts with subprocess sudo systemctl restart networkmamager
Worked when done manually
Change desktop image to a less different one
Purple Line row is cut off just a hair if there are 4 Metro rows and one marc
Check if marc is correct for origin station cause I didn't see it switch to realtime after scheduled went to 1 min
- Yead it appears the realtime marc doesn't include the origin station unit it's departed

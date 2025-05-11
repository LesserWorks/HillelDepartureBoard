#!/usr/bin/env bash
# Turn on screen
# kill script if already running
kill -9 $(<arrivals_pid.txt)
rm arrivals_pid.txt
# Close browser
# Open browser
# Start arrivals script storing PID
nohup ./arrivals.py --marc_code 12018-12015 --metro_code E09 --refresh 20 >/dev/null 2>&1 &
echo $! > arrivals_pid.txt

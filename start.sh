#!/usr/bin/env bash
# Turn on screen
# kill script if already running
if [ -f arrivals_pid.txt ]; then
    kill -9 $(<arrivals_pid.txt)
    rm arrivals_pid.txt
fi
# Close browser
if [ -f brave_pid.txt ]; then
    kill $(<brave_pid.txt)
    rm brave_pid.txt
fi
# Start browser storing PID
nohup brave-browser --suppress-message-center-popups --start-fullscreen file:///home/ubuntu/Documents/HillelDepartureBoard/DepartureBoard.html >/dev/null 2>&1 &
echo $! > brave_pid.txt
# Start arrivals script storing PID
nohup ./arrivals.py --marc_code 12018-12015 --metro_code E09 --refresh 20 >/dev/null 2>&1 &
echo $! > arrivals_pid.txt

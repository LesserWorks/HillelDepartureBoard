#!/usr/bin/env bash
# Turn on screen
xrandr --output HDMI-1 --auto
# kill script if already running
if [ -f arrivals_pid.txt ]; then
    kill -9 $(<arrivals_pid.txt)
    rm arrivals_pid.txt
fi
# Close browser in case it was running
pkill brave
# Start browser storing PID
export DISPLAY=:0 && nohup brave-browser --suppress-message-center-popups --disable-dialog --start-fullscreen file:///home/user/HillelDepartureBoard/DepartureBoard.html >/dev/null 2>&1
# Start arrivals script storing PID
source /home/user/.venv/bin/activate
nohup ./arrivals.py --marc_code 12018-12015 --metro_code E09 --refresh 20 >/dev/null 2>&1 &
echo $! > arrivals_pid.txt

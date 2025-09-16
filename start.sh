#!/usr/bin/env bash

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000
/usr/bin/wlr-randr --output HDMI-A-1 --on

unclutter -idle 1 -root &

rm -rf /home/$USER/.cache/chromium && rm -rf /home/$USER/.config/chromium

echo "$(</home/admin/Documents/HillelDepartureBoard/crontab.txt)" | crontab -
source /home/admin/Documents/HillelDepartureBoard/venv/bin/activate
cd /home/admin/Documents/HillelDepartureBoard/; ./arrivals.py --marc_code 12018-12015 --metro_code E09 --refresh 20 &
chromium-browser --noerrdialogs --disable-infobars --kiosk --no-crash-upload --disable-breakpad --disable-crash-reporter --incognito --disable-translate --no-first-run file:///home/admin/Documents/HillelDepartureBoard/DepartureBoard.html &

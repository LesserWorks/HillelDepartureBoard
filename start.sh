#!/usr/bin/env bash

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000
/usr/bin/wlr-randr --output HDMI-A-1 --on

unclutter -idle 1 -root &

rm -rf /home/$USER/.cache/chromium && rm -rf /home/$USER/.config/chromium
# disable wifi power management
sudo iwconfig wlan0 power off

echo "$(</home/admin/Documents/HillelDepartureBoard/crontab.txt)" | crontab -
source /home/admin/Documents/HillelDepartureBoard/venv/bin/activate
cp /home/admin/Documents/HillelDepartureBoard/blank.html /home/admin/Documents/HillelDepartureBoard/DepartureBoard.html
cd /home/admin/Documents/HillelDepartureBoard/; ./arrivals.py --marc_code 11958 --metro_code C04 --deploy --refresh 20 &
chromium-browser --noerrdialogs --disable-infobars --kiosk --no-crash-upload --disable-breakpad --disable-crash-reporter --incognito --disable-translate --no-first-run file:///home/admin/Documents/HillelDepartureBoard/DepartureBoard.html &

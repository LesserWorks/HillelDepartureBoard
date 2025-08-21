#!/usr/bin/env bash

xset s noblank
xset s off

unclutter -idle 1 -root &

sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' /home/$USER/.config/chromium/Default/Preferences
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' /home/$USER/.config/chromium/Default/Preferences

echo "$(</home/admin/Documents/HillelDepartureBoard/crontab.txt)" | crontab -
source /home/admin/Documents/HillelDepartureBoard/venv/bin/activate
cd /home/admin/Documents/HillelDepartureBoard/; ./arrivals.py --marc_code 12018-12015 --metro_code E09 --refresh 20 &
chromium-browser --noerrdialogs --disable-infobars --kiosk --no-first-run file:///home/admin/Documents/HillelDepartureBoard/DepartureBoard.html &

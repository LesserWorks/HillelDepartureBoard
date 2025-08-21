#!/usr/bin/env bash
# kill script
kill -9 $(<arrivals_pid.txt)
rm arrivals_pid.txt
# kill browser
kill $(<chrome_pid.txt)
rm chrome_pid.txt
# turn off screen
xrandr --output HDMI-1 --off
# sleep

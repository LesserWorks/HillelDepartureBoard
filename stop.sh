#!/usr/bin/env bash
# kill script
kill -9 $(<arrivals_pid.txt)
rm arrivals_pid.txt
# kill browser
kill $(<brave_pid.txt)
rm brave_pid.txt
# turn off screen
xrandr --output HDMI-I --off
# sleep
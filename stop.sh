#!/usr/bin/env bash
# kill script
kill -9 $(<arrivals_pid.txt)
rm arrivals_pid.txt
# kill browser
# turn off screen
# sleep
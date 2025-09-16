#!/usr/bin/env bash
sudo systemctl stop kiosk.service

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000
/usr/bin/wlr-randr --output HDMI-A-1 --off

cd /home/admin/Documents/HillelDepartureBoard; git pull

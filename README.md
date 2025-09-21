# HillelDepartureBoard
In the morning, crontab calls reboot, and kiosk.service will start automatically on reboot.
This service executes HillelDepartureBoard/start.sh, which in turn updates crontab and starts the script and browser.
The service unit file is at /lib/systemd/system/kiosk.service.

In the evening, crontab stops the service, turns off the screen, and does git pull.


# HillelDepartureBoard
In the morning, crontab calls reboot, and kiosk.service will start automatically on reboot.
This service executes HillelDepartureBoard/start.sh, which in turn updates crontab and starts the script and browser.

In the evening, crontab stops the service, turns off the screen, and does git pull.


#!/bin/bash

# WSL2
if [[ $(uname -r) == *microsoft-standard-WSL2* ]]; then
    lsusb | grep -q -P 'ST-?Link' || ./usbattach.sh
fi

openocd  -f interface/stlink.cfg   -f 'tcl/airsense.cfg'

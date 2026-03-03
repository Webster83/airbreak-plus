#!/bin/bash

# WSL2
if [[ $(uname -r) == *microsoft-standard-WSL2* ]]; then
    lsusb | grep -q -P 'ST-?Link' || ./usbattach.sh
fi

if [ -z "$1" ] ; then
    cfg="airsense.cfg"
else
    cfg="${1}.cfg"
fi

openocd -f interface/stlink.cfg -f "tcl/${cfg}"

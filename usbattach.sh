#!/bin/bash

rx='^([0-9]+-[0-9]+)[[:space:]]+([0-9a-f]{4}:[0-9a-f]{4})[[:space:]]+(.*)[[:space:]]+(Shared|Not shared)'

TIMEOUT=10
SECONDS=0

while IFS= read -r line; do
    if [[ $line =~ $rx ]]; then
        busid="${BASH_REMATCH[1]}"
        vidpid="${BASH_REMATCH[2]}"
        name="${BASH_REMATCH[3]}"
        state="${BASH_REMATCH[4]}"

        # attach only previously shared devices
        if [[ "$state" == "Shared" ]] ; then
            printf 'Attaching %s [%s] %s\n' "$busid" "$vidpid" "$name"
            usbipd.exe usbipd attach --wsl --busid $busid

            echo "Waiting for USB device ${vidpid}..."
            until lsusb | grep -qi "${vidpid}"; do
                sleep 1
                if (( SECONDS >= TIMEOUT )); then
                    echo "Timeout waiting for USB device"
                    exit 1
                fi
            done

        fi
    fi
done < <(usbipd.exe list)

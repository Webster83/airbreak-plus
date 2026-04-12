# airbreak-plus

Firmware modification toolkit for ResMed AirSense 10 / AirCurve 10, with partial support for Series 9 and AirSense 11.

## What it does

- Unlocks all therapy modes
- Unlocks clinical settings menu with full pressure range
- Removes motor runtime hours nag screen
- Full EDF signal recording in all therapy modes
- Maintains myAir cloud compatibility across therapy modes
- ILI9325/ILI9328 LCD driver (the most common replacement panel available for these devices)

Best support for SX567-0401 and SX567-0402 firmware. Other versions are handled with reduced feature coverage.

## Usage

Patching requires an original firmware image, either obtained separately or dumped from the device via OpenOCD/SWD.

Detailed usage documentation is a work in progress.

## Related

- [airbridge](https://github.com/m-kozlowski/airbridge) -- ESP32 WiFi bridge for AirSense 10 service port

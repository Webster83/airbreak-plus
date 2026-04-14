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

## Getting started

See the [quickstart guide](docs/guide/quickstart.md) for a full walkthrough.

| Guide | Content |
|-------|---------|
| [Quickstart](docs/guide/quickstart.md) | End-to-end overview |
| [Disassembly](docs/guide/disassembly.md) | Opening the device |
| [SWD wiring](docs/guide/wiring.md) | Programming header connections |
| [Serial connection](docs/guide/serial_connection.md) | UART accessory port (for flashing without SWD) |
| [OpenOCD](docs/guide/openocd.md) | Firmware dump |
| [Patching](docs/guide/patching.md) | Building, patch options, customization |
| [Flashing](docs/guide/flashing.md) | SWD and UART flashing |

## Reference

| Document | Content |
|----------|---------|
| [UART protocol](docs/uart_protocol.md) | Frame format and commands |
| [Config variables](docs/config_variables.md) | Firmware variable system and globals[] structures |
| [resmed_config](docs/resmed_config.md) | UART configuration tool |
| [resmed_flash](docs/resmed_flash.md) | UART flash tool |
| [eeprom_tool](docs/eeprom_tool.md) | SPI EEPROM access |
| [Variable reference](docs/var_reference.tsv) | All 744 variables with var_id, UART name, EDF signal |

## Related

- [airbridge](https://github.com/m-kozlowski/airbridge) -- ESP32 WiFi bridge for AirSense 10 service port

# eeprom_tool / eeprom_stub

Direct access to the SPI EEPROM (M95M02, 256KB) on Air 10.

## Overview

**eeprom_stub** is a minimal bare-metal firmware that replaces the CDX region. It provides a binary protocol over USART3 for raw EEPROM read/write, plus basic ResMed protocol compatibility (BID, BLS, SID, RES, BLL) so that `resmed_flash.py` can flash a different firmware back onto the device.

**eeprom_tool** is the host-side Python client.

## Flashing eeprom_stub

```
resmed_flash.py -p /dev/ttyACM0 -f eeprom_stub_full.bin --block cdx
```

Two build variants:
- `eeprom_stub_nocrc.bin` -- for patched bootloader (CRC bypass)
- `eeprom_stub_full.bin` -- 768KB padded with CRC, for stock bootloader

## Returning to normal firmware

eeprom_stub responds to the standard ResMed bootloader entry commands. Flash the original (or patched) firmware normally:

```
resmed_flash.py -p /dev/ttyACM0 -f stm32.bin
```

## Commands

### ping

```
eeprom_tool.py -p /dev/ttyACM0 ping
```

### read

Full dump or partial read.

```
eeprom_tool.py -p /dev/ttyACM0 read dump.bin
eeprom_tool.py -p /dev/ttyACM0 read part.bin 0x10 0x100
```

### write

Write a full EEPROM image.

```
eeprom_tool.py -p /dev/ttyACM0 write image.bin
```

### patch

Write raw bytes at a specific address.

```
eeprom_tool.py -p /dev/ttyACM0 patch 0x120 01ABFF
```

### erase

Erase entire EEPROM (fills with 0xFF).

```
eeprom_tool.py -p /dev/ttyACM0 erase
```

### fixcrc

Recalculate and write the EEPROM header CRC.

```
eeprom_tool.py -p /dev/ttyACM0 fixcrc
```

### FAT filesystem (requires pyfatfs)

The EEPROM contains a FAT12 filesystem at offset 0x200 with therapy data, settings, and session files.

```
eeprom_tool.py -p /dev/ttyACM0 fat-ls /
eeprom_tool.py -p /dev/ttyACM0 fat-get /SETTINGS/BGL.set out.bin
eeprom_tool.py -p /dev/ttyACM0 fat-getdir /SETTINGS ./backup/
eeprom_tool.py -p /dev/ttyACM0 fat-put in.bin /SETTINGS/BGL.set
```

## EEPROM layout

| Region | Offset | Content |
|--------|--------|---------|
| Header | 0x00-0x51 | eh... stuff. |
| FAT12 | 0x200+ | Filesystem with DATALOG, ERRORLOG, SESSION, SETTINGS |

## Binary protocol

Frame format:

```
[0x55] [CMD] [LEN:2 BE] [payload] [CRC16:2 BE]
```

CRC-16/CCITT-FALSE over CMD+LEN+payload.

| CMD | Name | Payload | Response |
|-----|------|---------|----------|
| 0x01 | Ping | -- | DATA: version string |
| 0x02 | Read | addr:3, len:3 | ACK + streaming data + CRC |
| 0x03 | Write | addr:3, data:N | ACK or NACK |
| 0x04 | Bulk write | addr:3, count:2 | ACK, then per-page streaming |
| 0x05 | Erase | -- | ACK |
| 0x06 | Fix CRC | -- | DATA: old_crc:2, new_crc:2 |
| 0x07 | Set baud | baud:4 BE | ACK |
| 0x08 | Reset | -- | ACK, then system reset |

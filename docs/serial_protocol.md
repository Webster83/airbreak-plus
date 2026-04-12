# UART Protocol

AirSense 10 external service port (USART3). 57600 8N1, 3.3V logic.

## Frame format

```
[0x55] [type] [len:3 hex-ASCII] [payload, 0x55-escaped] [crc:4 hex-ASCII]
```

| Field | Size | Encoding |
|-------|------|----------|
| Sync | 1 | `0x55` literal |
| Type | 1 | ASCII char: `E`, `F`, `f`, `K`, `L`, `O`, `P`, `Q`, `R`, `T` |
| Length | 3 | Hex-ASCII, total frame size in bytes (sync through CRC) |
| Payload | 0..502 | Binary. `0x55` in payload escaped as `0x55 0x55` |
| CRC-16 | 4 | Hex-ASCII, CRC-CCITT-FALSE over all preceding bytes |

CRC: poly 0x1021, init 0xFFFF, no output XOR, MSB-first.

Two frame types are immediate (no length/payload/CRC):

| Type | Wire bytes |
|------|-----------|
| O | `0x55 0x4F` |
| P | `0x55 0x50` |

## Frame types

| Type | Direction | Format | Purpose |
|------|-----------|--------|---------|
| Q | host -> device | full | Query or set command |
| R | device -> host | full | Success response |
| E | device -> host | full | Error response |
| L | host -> device | full | Oximetry data (SpO2 module feed, no response) |
| K | device -> host | full | Stream data record (output only) |
| F | host -> device | full | Flash data (S-records) |
| f | host -> device | full | Flash completion marker |
| O | host -> device | immediate | Session open (resets parser, sets ZRO if ZLB active) |
| P | host -> device | immediate | Parser reset |
| T | -- | -- | Reserved, rejected with E-frame 0x6011 |

CDX accepts 4 input types: Q, L, O, P. All others are rejected (E-frame 0x6011).

Bootloader accepts: Q, F, f, P.

## Q-frame commands

Payload is ASCII text. Two command families:

### Get variable

```
Q: G S #VAR
R: G S #VAR = VALUE
```

`VALUE` is hex-encoded, zero-padded to field width. Error returns E-frame.

### Set variable

```
Q: P S #VAR VALUE
R: P S #VAR = VALUE
```

### Stream query

```
Q: G F &STREAM           -> R: echo + K: descriptor
Q: G F &STREAM 0001      -> R: echo + K: record #1
Q: G F &STREAM 0002      -> R: echo + K: record #2
...                       -> R: echo + K: empty sentinel (00000FFFF00000)
```

Page index is 1-based. Pagination continues until empty sentinel.

## Error codes

| Code | Meaning |
|------|---------|
| 0x6006 | Unknown variable |
| 0x6009 | Variable not available in this context |
| 0x6011 | Rejected frame type |
| 0x6014 | CRC validation failed |
| 0x6034 | Stream not found or bad query argument |

## K-frame payload

```
NAME(3) date_start(9 hex) date_end(9 hex) time(3 hex) field(4 hex) data(variable)
```

| Field | Size | Description |
|-------|------|-------------|
| NAME | 3 | Stream identifier (DLL, ERR, TXE, etc.) |
| date_start | 9 hex | Day count from 1970-01-01 epoch, zero-padded |
| date_end | 9 hex | Same encoding |
| time | 3 hex | Minutes since midnight |
| field | 4 hex | Record type (observed: 0001) |
| data | variable | Stream-specific |

## Date encoding

16-bit day count from January 1, 1970 (Unix epoch).

| Hex | Date |
|-----|------|
| 0x5043 | 2026-04-04 |
| 0x5048 | 2026-04-09 |

## Bootloader commands

| Command | Response | Effect |
|---------|----------|--------|
| `G S #BID` | R: bootloader version | |
| `G S #BLS` | R: 0=CDX, 1=BL, 2=BL (invalid app) | |
| `G S #SID` | R: CDX version string | |
| `G S #CID` | R: CCX version string | |
| `P S #BLL 0001` | R: echo | Enter bootloader (reset) |
| `P S #RES 0001` | R: echo | System reset |
| `P S #RES 0003` | R: echo | Fast reset (BKP6R fast-boot) |
| `P S #BDD KEY` | R: echo | Set baud rate for flash transfer |
| `P F *CCX` | R: echo | Select flash block |
| `P S #PIP KEY` | R: echo | Enter UART bridge mode |

### BDD baud rates

| Key | Baud |
|-----|------|
| 0000 | 57600 |
| 0001 | 115200 |
| 0002 | 460800 |

## Flash data protocol

F-frames carry S-record data for firmware flashing:

- `P F *BLX` / `*CCX` / `*CDX` / `*CMX` selects target block
- F-frames contain S-records (type 0=header, 3=data, 7=end)
- Completion: F-frame with marker byte 'F', triggers write and reset

## L-frame (oximetry)

One-way push from SpO2 module. No response from device.

```
0x55 'L' len(3) O X H [seq:2] [OXS:2] [HRR:3] [SAS:2] [SAR:2] [NVS:2] crc(4)
```

Full format in [oximeter_protocol.md](oximeter_protocol.md).

## O-frame (session open)

Immediate 2-byte frame (`0x55 0x4F`). Resets UART parser. If ZLB (port active flag) is set, also sets ZRO (new session flag).

## 0x55 escaping

Any `0x55` byte within the payload region is doubled to `0x55 0x55`. The length field counts escaped bytes (total wire size). CRC is computed over the wire bytes (with escaping).

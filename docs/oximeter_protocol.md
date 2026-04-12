
## Frame Format

All communication uses ASCII hex-encoded frames:

```
U <type:1> <len:3> <payload:N> <crc:4>
```

| Field | Size | Description |
|-------|------|-------------|
| U | 1 char | Sync byte, always `U` (0x55) |
| type | 1 char | Frame type: `Q` = query/set, `L` = data stream, `R` = response (from device), `E` = echo |
| len | 3 hex chars | Total frame length in characters (sync + type + len + payload + crc) |
| payload | N chars | ASCII payload, content depends on frame type |
| crc | 4 hex chars | CRC-16/CCITT, uppercase hex |

### CRC Calculation

CRC-16/CCITT with polynomial 0x1021, init 0xFFFF. Computed over **all characters preceding the CRC field** (i.e., sync + type + len + payload). Input is raw ASCII bytes.

```python
def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc
```

Example: frame body `UQ016P S #LCA 0001` → CRC = `855C` → full frame = `UQ016P S #LCA 0001855C`

## Communication Sequence

The adapter runs three phases in order:

### Phase 1: Identification (Q-frames)

Send `P S #LCT` with the adapter identifier string, padded with underscores to exactly 31 characters. Repeat every ~500ms until the device responds with an R-frame echo, up to ~20 attempts.

```
UQ032P S #LCT ____Oximetry_______SX489-0200___BEA5
```

- len = `032` (0x32 = 50 decimal, the total character count of the frame)
- Payload: `P S #LCT ____Oximetry_______SX489-0200___`
- The identifier `SX489-0200` is the adapter firmware version
- The device responds with an R-frame containing the echoed value when it accepts the identification

### Phase 2: LCD Popup (Q-frames)

Show a brief popup notification on the device LCD, then hide it:

```
UQ016P S #LCA 0001855C      ← show popup
UQ016P S #LCA 0000957D      ← hide popup
```

- Send show, wait ~2 seconds, send hide
- `LCA` is the LCD Alert variable
- `0001` = show, `0000` = hide

### Phase 3: Data Streaming (L-frames)

Continuously stream oximetry data using L-frames. The device does **not** respond to L-frames.

```
UL019OXH<seq><data><crc>
```

- len = `019` (0x19 = 25 decimal, always fixed for OXH frames)
- Tag = `OXH` (oximeter header)
- Rate: **3 frames per second** (~333ms interval). The device expects continuous frames; if the rate drops too low, the display briefly shows dashes.

#### Sequence Counter

`<seq>` is a 2-character hex counter (00–FF). Increments by 1 each frame, wraps from FF → 00. Must be continuous.

#### Data Field

`<data>` is exactly **11 hex characters** (nibbles), encoding 5 fields:

```
Position:  [0:2]  [2:5]  [5:7]  [7:9]  [9:11]
Width:      2      3      2      2      2      = 11 nibbles
Field:     OXS    HRR    SAS    SAR    NVS
```

| Field | Width | Valid Range | Invalid | Description |
|-------|-------|-------------|---------|-------------|
| OXS | 2 nib | 0x81, 0x83 | 0x99, 0x9B | Oximetry status |
| HRR | 3 nib | 0x000–0x12C (0–300 bpm) | 0x1FF | Heart rate |
| SAS | 2 nib | 0x80, 0x82 | 0x98, 0x9A | SpO2 status |
| SAR | 2 nib | 0x00–0x64 (0–100%) | 0x7F | SpO2 percentage |
| NVS | 2 nib | 0x10 | - | Adapter version (constant) |

#### OXS - Oximetry Status (2 nibbles)

Bit layout of the 8-bit value:

| Bit | Meaning |
|-----|---------|
| 7 | Always 1 |
| 4 | 0 = finger detected, 1 = no finger |
| 3 | 1 = no finger |
| 1 | **Alive toggle** - alternates 0/1 every frame |
| 0 | Always 1 |

Common values:
- `0x81` / `0x83` - finger present (bit 1 toggles)
- `0x99` / `0x9B` - no finger (bit 1 toggles)
- `0x9D`, `0xBD` - also observed during no-finger periods (other status bits)

**The toggle bit must alternate every frame.** The device uses this to detect a stalled adapter.

#### HRR - Heart Rate (3 nibbles)

- 12-bit unsigned integer, range 0x000–0x12C (0–300 bpm)
- Values above 300 (0x12C) are rejected by the device (display shows dashes)
- No-finger value: `0x1FF` (511)
- Direct BPM encoding - no scaling. Value `0x048` = 72 bpm, `0x05F` = 95 bpm

#### SAS - SpO2 Status (2 nibbles)

Bit layout of the 8-bit value:

| Bit | Meaning |
|-----|---------|
| 7 | Always 1 |
| 4 | 1 = no signal |
| 3 | 1 = no signal |
| 1 | **Alive toggle** - alternates 0/1 every frame, synchronized with OXS bit 1 |
| 0 | Always 0 |

Common values:
- `0x80` / `0x82` - valid reading (bit 1 toggles)
- `0x98` / `0x9A` - no signal (bit 1 toggles)

#### SAR - SpO2 Percentage (2 nibbles)

- 8-bit unsigned integer, range 0x00–0x64 (0–100%)
- No-finger value: `0x7F` (127)
- Direct percentage - no scaling. Value `0x61` = 97%

#### NVS - Adapter Version (2 nibbles)

- Constant `0x10` in all observed frames
- Reported to the device as the adapter firmware/hardware version

### Toggle Bit Behavior

Both OXS bit 1 and SAS bit 1 must alternate every frame, synchronized:

| Frame | OXS | SAS |
|-------|-----|-----|
| N | 0x81 | 0x80 |
| N+1 | 0x83 | 0x82 |
| N+2 | 0x81 | 0x80 |
| N+3 | 0x83 | 0x82 |

This applies regardless of finger state. No-finger frames also toggle:

| Frame | OXS | SAS |
|-------|-----|-----|
| N | 0x99 | 0x98 |
| N+1 | 0x9B | 0x9A |

## Complete Frame Examples

### No finger

```
UL019OXH03991FF987F1066D6
         ││  │││  ││  ││└── CRC
         ││  │││  ││  │└─── NVS = 0x10
         ││  │││  ││  └──── SAR = 0x7F (invalid)
         ││  │││  │└──────── SAS = 0x98 (no signal, toggle=0)
         ││  │││  └───────── SAS cont.
         ││  ││└──────────── HRR = 0x1FF (invalid)
         ││  │└───────────── HRR cont.
         ││  └────────────── HRR cont.
         │└───────────────── OXS = 0x99 (no finger, toggle=0)
         └────────────────── OXS cont.
```

Data: `99` `1FF` `98` `7F` `10`

### Finger present, HR=72 SpO2=97, toggle=0

```
UL019OXHAB81048806110xxxx
```

Data: `81` `048` `80` `61` `10`

### Finger present, HR=72 SpO2=97, toggle=1

```
UL019OXHAC83048826110xxxx
```

Data: `83` `048` `82` `61` `10`

### Finger present, HR=107 SpO2=96, toggle=0

```
UL019OXH5981 06B 80 60 10 xxxx
```

Data: `81` `06B` `80` `60` `10`

## State Transitions

### Finger insertion

When a finger is first inserted into the sensor, the adapter transitions from no-finger to finger-present. During initial settling (first few frames), HRR may start high and converge to the actual heart rate over several seconds.

### Finger removal

On finger removal, OXS immediately changes to no-finger pattern (0x99/0x9B), HRR becomes 0x1FF, SAR becomes 0x7F.

### Adapter disconnect

If frames stop arriving, the device reverts to showing no oximeter data after a short timeout.

## Implementation Notes

1. **Frame rate is important.** The device expects ~3 frames/sec.
2. **Toggle bits must alternate every frame.** Frozen toggle = device treats adapter as stalled.
3. **Sequence counter must be continuous.** Gaps may trigger error handling.
4. **HRR values above 300 are silently discarded** by the device - the display shows dashes as if no data is present.

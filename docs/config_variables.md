# Config Variables

## Table of contents

- [globals[] array](#globals-array)
  - [Variable dispatch](#variable-dispatch)
  - [All identified globals](#all-identified-globals)
- [g[0] -- device identity](#g0----device-identity)
- [g[1] -- timer scale table](#g1----timer-scale-table)
- [g[2] -- localized string table](#g2----localized-string-table)
- [g[3] -- identity/metadata descriptors](#g3----identitymetadata-variable-descriptors)
- [g[4] -- numeric variable descriptors](#g4----numeric-variable-descriptors)
- [g[6] -- config/status variable descriptors](#g6----configstatus-variable-descriptors)
- [g[8] -- enum/option variable descriptors](#g8----enumoption-variable-descriptors)
- [g[11] -- signal headers (BRP, PLD, SAD)](#g11----signal-headers-brp-pld-sad)
- [g[12] -- STR field records](#g12----str-field-records)
- [g[13] -- PSTR (STR channel descriptor)](#g13----pstr-str-channel-descriptor)
- [g[14] -- NPD signal group](#g14----npd-signal-group)
- [g[16] -- variable groups](#g16----variable-groups)
- [g[19] -- EEPROM stream table](#g19----eeprom-stream-table)
- [g[20] -- PDL definition](#g20----pdl-definition)
- [g[21] -- PDL rule pointer](#g21----pdl-rule-pointer)
- [g[22] -- UART name table (flat)](#g22----uart-name-table-flat)
- [g[23] -- UART name table (bucketed)](#g23----uart-name-table-bucketed)
- [g[24] -- mode membership table](#g24----mode-membership-table)
- [g[26] -- live stream records](#g26----live-stream-records)
- [g[27] -- APN/CSN/BRH records](#g27----apncsnbrh-records)
- [g[28] -- OXH (oximetry header)](#g28----oxh-oximetry-header)
- [Flags bitmask](#flags-bitmask)
- [RAM shadow](#ram-shadow)
- [Dependency chain](#dependency-chain)

---

## globals[] array

`CCX+0x108` holds an array of 29 pointers. Each points to a descriptor table in CCX.

### Variable dispatch

Variable IDs are implicitly encoded by table position: `var_id = id_base + record_index`.
These IDs are the numeric references stored inside the firmware image. For
cross-variant work, the 3-letter UART names in g[23] are the stable lookup key:
some IDs move across older SX567 catalog/build variants.

| globals | stride | id_base | id_range | content |
|---------|--------|---------|----------|---------|
| [3] | 10 | 0x000 | 0x000-0x01D | identity, metadata |
| [4] | 0x1C | 0x01E | 0x01E-0x1FC | numeric variables (pressure, therapy params) |
| [6] | 0x18 | 0x1FD | 0x1FD-0x20C | config/status |
| [8] | 0x14 | 0x20D | 0x20D-0x2B1 | enum/option variables |
| [9] | 0x18 | 0x2B2 | 0x2B2 | timer (single entry) |
| [10] | 0x24 | -- | -- | internal (3 entries) |

Dispatch function at CDX 0x0806f3cc:
```
var_id < 0x1E           -> g[3]
0x1E  <= var_id < 0x1FD -> g[4]
0x1FD <= var_id < 0x20D -> g[6]
0x20D <= var_id < 0x2B2 -> g[8]
0x2B2                   -> g[9]
0x2B6, 0x2B7            -> g[10]
```

### All identified globals

| globals | content |
|---------|---------|
| [0] | Device identity |
| [1] | Timer scale table |
| [2] | Localized string table |
| [3] | Variable descriptors: identity/metadata (stride 10, var 0x000-0x01D) |
| [4] | Variable descriptors: numeric (stride 0x1C, var 0x01E-0x1FC) |
| [5] | Mode visibility table (populated at runtime, flash value is stale) |
| [6] | Variable descriptors: config/status (stride 0x18, var 0x1FD-0x20C) |
| [7] | Localized string table (secondary) |
| [8] | Variable descriptors: enum/option (stride 0x14, var 0x20D-0x2B1) |
| [9] | Variable descriptors: timer (stride 0x18, var 0x2B2, single entry) |
| [10] | Variable descriptors: internal (stride 0x24, 3 entries) |
| [11] | Signal headers: BRP, PLD, SAD |
| [12] | STR field records: CSL/AEV/EVE |
| [13] | PSTR: STR channel descriptor |
| [14] | NPD signal group (contiguous with g[13]) |
| [15] | NPA signal group |
| [16] | Variable groups |
| [17]-[18] | Descriptor records (8B and 12B) |
| [19] | EEPROM stream table |
| [20] | PDL definition: var list + inline stat rule records |
| [21] | PDL rule count/pointer |
| [22] | UART name table, flat format |
| [23] | UART name table, bucketed |
| [24] | Mode table (settings x modes) |
| [26] | Stream records: TCE/PBT/PMD/FTX/RAW/DRT/CPU/SSK (8 x 20B) |
| [27] | APN/CSN/BRH records + shared OXH tail |
| [28] | OXH header + inline var_id/rate arrays |

Note: [15] through [24] form a contiguous opaque block in the observed CCX layout.

---

## g[0] -- device identity

```
+0x00: u32[7]  CID components (CX###-###-###-###-###-###-###)
+0x20: char[]  catalog number (e.g. "37101")
+0x30: char[]  product name (e.g. "AirSense 10 AutoSet")
```

---

## g[1] -- timer scale table

14 entries x 16 bytes:

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 2 | level (0-6, 10) |
| +0x02 | 2 | ticks per unit |
| +0x04 | 2 | multiplier |
| +0x06 | 2 | pad |
| +0x08 | 8 | period in seconds (f64) |

---

## g[2] -- localized string table

Array of 8-byte records, one per string ID:

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 2 | max string length across all locales |
| +0x02 | 2 | pad |
| +0x04 | 4 | pointer to locale index array |

Lookup: `string_lookup(str_id, locale)`:
```
locale_arr = u32(g[2] + str_id*8 + 4)
raw_index  = u16(locale_arr + locale*2)
str_ptr    = u32(raw_table + raw_index*4)
```

---

## g[3] -- identity/metadata variable descriptors

**Record stride:** 10 bytes, **Entry count:** 30, **var_id range:** 0x000-0x01D

Contains string-type variables (BID, SID, CID, PNA, SRN, etc.).

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 2 | flags |
| +0x02 | 1 | callback_id |
| +0x03 | 1 | -- |
| +0x04 | 2 | linked_var_id (0x7FFF = none) |
| +0x06 | 2 | name_str_id (0xDE = none) |
| +0x08 | 2 | max_length |

---

## g[4] -- numeric variable descriptors

**Record stride:** 0x1C (28 bytes), **Entry count:** 0x1DF (479)

### Record layout

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| +0x00 | 2 | flags | Status bitmask (see below) |
| +0x02 | 1 | callback_id | Post-change callback index. 0 = none |
| +0x03 | 1 | -- | |
| +0x04 | 2 | next_dependent_g4_idx | Linked-list pointer into g[4] for dependency chain. 0x7FFF = end |
| +0x06 | 2 | name_str_id | Localized display name via g[2] |
| +0x08 | 4 | default_value | Default value, copied to RAM on init |
| +0x0C | 4 | max_value | Upper clamp |
| +0x10 | 4 | min_value | Lower clamp |
| +0x14 | 1 | decimal_places | Display precision |
| +0x15 | 1 | -- | |
| +0x16 | 2 | scale_factor | Conversion factor for string<->value. Positive: divide. Negative: multiply by abs |
| +0x18 | 2 | step_size | Increment/decrement step |
| +0x1A | 2 | units_str_id | Units label string via g[2] |

### Sub-handler ranges

| Index range | var_id range | Notes |
|-------------|-------------|-------|
| 0x000-0x1B3 | 0x1E-0x1D1 | Standard numeric |
| 0x1B4-0x1D3 | 0x1D2-0x1F1 | Extended (per-mode max/min pairs) |
| 0x1D4-0x1D8 | 0x1F2-0x1F6 | Reminder dates |
| 0x1D9-0x1DC | 0x1F7-0x1FA | Reminder enables |
| 0x1DD-0x1DE | 0x1FB-0x1FC | Error tracking |

---

## g[6] -- config/status variable descriptors

**Record stride:** 0x18 (24 bytes), **Entry count:** 16, **var_id range:** 0x1FD-0x20C

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 2 | flags |
| +0x02 | 1 | callback_id |
| +0x03 | 1 | -- |
| +0x04 | 2 | linked_var_id |
| +0x06 | 2 | name_str_id |
| +0x08 | 4 | default_value |
| +0x0C | 4 | max_value |
| +0x10 | 4 | -- |
| +0x14 | 4 | -- |

---

## g[8] -- enum/option variable descriptors

**Record stride:** 0x14 (20 bytes), **Entry count:** 0xA5 (165)

### Record layout

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| +0x00 | 2 | flags | Status bitmask (see below) |
| +0x02 | 1 | callback_id | Post-change callback index. 0 = none |
| +0x03 | 1 | -- | |
| +0x04 | 2 | dependency_head_g4_idx | Index into g[4] for dependency propagation. 0x7FFF = none |
| +0x06 | 2 | name_str_id | Localized display name via g[2] |
| +0x08 | 1 | default_value | Default state byte |
| +0x09 | 1 | num_options | Number of valid options |
| +0x0A | 2 | -- | |
| +0x0C | 4 | permission_bitmask | Per-mode access. `(1 << mode_id) & bitmask` |
| +0x10 | 2 | base_string_id | Base string ID for option labels. `base + option_idx` = label. 0xDE = none |
| +0x12 | 2 | -- | |

---

## g[11] -- signal headers (BRP, PLD, SAD)

3 consecutive 32-byte headers defining EEPROM stream signal channels.
Each channel stores a var_id array, samples-per-record array, and optional signal
name string pointer array.

| Offset | Size | Field |
|--------|------|-------|
| +0x08 | 1 | field_count |
| +0x09 | 3 | name (e.g. "BRP") |
| +0x10 | 4 | var_id array pointer |
| +0x14 | 4 | samples-per-record array pointer |
| +0x18 | 4 | param |
| +0x1C | 4 | name string array pointer |

---

## g[12] -- STR field records

3 x 24-byte headers (CSL, AEV, EVE), followed by field records.

Each header:

| Offset | Size | Field |
|--------|------|-------|
| +0x08 | 1 | gap count |
| +0x10 | 4 | gap var_id array pointer |

Field records (10 bytes each), immediately after headers:

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 1 | type (0x0D=record, 0x00=empty) |
| +0x01 | 1 | fid (0=CSL, 1=AEV, 2=EVE, 3=EXT/CSL_B/CSL_C) |
| +0x02 | 2 | source var_id (inner_vid for AEV/EVE) |
| +0x04 | 6 | type-specific params |

---

## g[13] -- PSTR (STR channel descriptor)

52 bytes, immediately followed by g[14] (NPD, 32 bytes).
`field_record_count`, the two chain arrays, the string table, and the field
record pointer must agree with g[12].

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 4 | config |
| +0x04 | 4 | config |
| +0x08 | 1 | field_record_count |
| +0x09 | 3 | "STR" |
| +0x0C | 4 | reserved |
| +0x10 | 4 | col1 array pointer (chain_start) |
| +0x14 | 4 | col2 array pointer (chain_mid) |
| +0x18 | 4 | config |
| +0x1C | 4 | strtab pointer (signal name pointer array) |
| +0x20 | 4 | field records pointer |
| +0x24 | 16 | NPD var_id array (part of g[14] area) |

---

## g[14] -- NPD signal group

32 bytes at g[13]+52:

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 4 | flags/id |
| +0x04 | 4 | param |
| +0x08 | 4 | threshold |
| +0x0C | 4 | session config |
| +0x10 | 1 | signal_count |
| +0x11 | 3 | "NPD" |
| +0x14 | 4 | reserved |
| +0x18 | 4 | back-pointer to g[13]+0x24 |
| +0x1C | 4 | reserved |

---

## g[16] -- variable groups

16 entries x 16 bytes. Defines the AGL, BGL, CGL, etc. groups used by resmed_config.

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 4 | group name (3 char + null) |
| +0x04 | 2 | start var_id |
| +0x06 | 2 | param |
| +0x08 | 4 | member var_id array pointer |
| +0x0C | 4 | member count |

---

## g[19] -- EEPROM stream table

10 entries x 28 bytes. Defines the EEPROM data streams (ABR, TXC, TXH, TXE, TXW, TRR, DLL, ERR, ELI, ZRL).

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 4 | name (3 char + null) |
| +0x04 | 4 | descriptor pointer |
| +0x08 | 2 | type |
| +0x0A | 2 | capacity |
| +0x0C | 2 | source var_id |
| +0x0E | 2 | record size |
| +0x10 | 8 | reserved |
| +0x18 | 4 | max records |

---

## g[20] -- PDL definition

Header pointing to a list of var_ids, followed by inline rule records. The same
rule records are also referenced by g[21].

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 4 | name (`"PDL\0"`) |
| +0x04 | 4 | var_id array pointer |
| +0x08 | 4 | var_id count |
| +0x0C | -- | rule records (16 bytes each) |

Rule record:

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 2 | destination/stat var_id |
| +0x02 | 2 | source/input var_id |
| +0x04 | 4 | flags/type (`type = (flags >> 8) & 0xff`) |
| +0x08 | 4 | param_a (`0xffffffff` = unused) |
| +0x0C | 4 | param_b (`0xffffffff` = unused) |

---

## g[21] -- PDL rule pointer

Separate access path to the PDL rule records.

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 4 | rule count |
| +0x04 | 4 | rule record pointer |

Stock variants carry different rule counts.

---

## g[22] -- UART name table (flat)

Same data as g[23] but as a flat array. 16-byte header (16 u16 metadata var_ids), then 744 entries of `{u8 char2, u8 char3, u16 var_id}`.

---

## g[23] -- UART name table (bucketed)

26 entries x 8 bytes (one per letter A-Z):

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 4 | subtable pointer |
| +0x04 | 4 | entry count |

Each subtable entry (4 bytes): `{u8 char2, u8 char3, u16 var_id}`.

First character is implicit from bucket index. Resolved by CDX at 0x08067200.

---

## g[24] -- mode membership table

Setting-to-mode membership table. g[25] holds the entry count.

Each entry is `2 + MOP.num_options` bytes:

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 2 | setting var_id |
| +0x02 | N | one byte per MOP option (`0x01` = member of that mode) |

The mode columns are taken from the `MOP` enum order, not from hardcoded mode
names.

This table describes which setting variables belong to each therapy mode. It is
a per-mode setting membership map: for example, it can answer "which settings
are part of VAuto?".

The g[8] `permission_bitmask` is stored inside one enum/option descriptor and
gates that variable's option/mode availability. It is local to that variable.
g[24] is the broader table mapping many setting variables across all `MOP`
modes.

---

## g[26] -- live stream records

8 records x 20 bytes. Defines live stream schemas such as `TCE`, `PBT`, `PMD`,
`FTX`, `RAW`, `DRT`, `CPU`, and `SSK`.

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 1 | field count |
| +0x01 | 3 | stream name |
| +0x04 | 4 | config |
| +0x08 | 4 | var_id array pointer |
| +0x0C | 4 | rate/scale array pointer |
| +0x10 | 4 | config |

Some stream arrays differ by therapy family. The count field describes only the
number of entries to read; the pointer fields define where the var_id/rate
arrays actually live.

---

## g[27] -- APN/CSN/BRH records

3 records x 16 bytes (`APN`, `CSN`, `BRH`) followed by a 24-byte shared OXH tail.
The records point into a packed var_id pool near g[26].

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 1 | field count |
| +0x01 | 3 | record name |
| +0x04 | 4 | config |
| +0x08 | 4 | var_id array pointer |
| +0x0C | 4 | rate/scale array pointer |

Observed maximum windows:

| Record | Vars |
|--------|---------------|
| APN | AET, DUR |
| CSN | CET, CSR |
| BRH | TID, ATP, INT, EXT |

Live stream reporting is enabled over UART with `P S &TAG 1` and disabled with
`P S &TAG 0`; see [serial_protocol.md](serial_protocol.md#live-stream-reporting).

Common live stream fields across checked SX567 Air 10 variants:

| Stream | Fields | Purpose |
|--------|--------|---------|
| PMD | MKP, RFL, LYK | Pressure, flow, and leak samples |
| FTX | BPR, BFL, NSE, TEM | Flow/pressure sensor diagnostics |
| RAW | PRS, FLW, NOS, TEZ | Raw pressure, flow, and temperature samples |
| DRT | D00, D01, D02, D03, D04, D05, D06, D07, D08, D09 | Internal diagnostic values |
| CPU | ALL, L01, L02, L03, L04, L05, L06, L07, L08, L09, L10, L11, L12, L13, L14, L15, L16, L17, L18, L19, L20 | CPU load counters |
| SSK | S10, S20, S40, S11, S22, S44, S1S, S1M, SMM, SEE, SPL, SLD | Internal status values |
| APN | AET, DUR | Apnea event timing |

Variant-dependent live stream fields:

| Stream | AirCurve VAuto | AirCurve CS | AirSense AutoSet/AfH | AirSense Elite | Purpose |
|--------|----------------|-------------|---------------------|---------------|---------|
| TCE | TCV, MKP, RFL, LYK | MKP, RFL, LYK | MKP, RFL, LYK | MKP, RFL, LYK | Therapy control samples |
| PBT | MV5, RRR, LKF, TIP, TEP | MV5, TGT, RRR, LKF, TIP, TEP | MV5, RRR, LKF, TIP, TEP | MV5, RRR, LKF, TIP, TEP | Periodic breathing and ventilation summary |
| CSN | CSR | CSR | CET, CSR | CET, CSR | CSR/central event status |
| BRH | TID, ATP, INT, EXT | TID, ATP | TID, ATP | TID | Breath summary |

---

## g[28] -- OXH (oximetry header)

| Offset | Size | Field |
|--------|------|-------|
| +0x00 | 1 | field_count |
| +0x01 | 3 | "OXH" |
| +0x04 | 4 | reserved |
| +0x08 | 4 | var_id array pointer |
| +0x0C | 4 | output array pointer |

---

## Flags bitmask

Shared format at +0x00 of g[3], g[4], g[6], g[8] records. Copied from ROM to RAM shadow on init.

| Bit | Mask | Name | Description |
|-----|------|------|-------------|
| 0 | 0x01 | ACT | Active. Master enable gate. If clear, value changes are blocked |
| 1 | 0x02 | VIS | Visible in UI menus |
| 2 | 0x04 | EDT | Editable by user |
| 3 | 0x08 | -- | Unknown |
| 4 | 0x10 | LOCK | Read-only lock |
| 5 | 0x20 | DIRTY | Set on value change |
| 6 | 0x40 | FDEF | Factory default marker. Always cleared on boot |

Note: VIS/EDT assignment may be swapped. Contradicting findings exist.

---

## RAM shadow

### g[8] -- 4 bytes per entry

| Offset | Source | Content |
|--------|--------|---------|
| +0x00 | +0x00 | flags (mutable) |
| +0x02 | +0x08 | current value |
| +0x03 | -- | pad |

### g[4] -- 8 bytes per entry

| Offset | Source | Content |
|--------|--------|---------|
| +0x00 | +0x00 | flags (mutable) |
| +0x02 | -- | pad |
| +0x04 | +0x08 | current value (i32, mutable) |

---

## Dependency chain

When a g[8] variable changes, the firmware walks a linked list of dependent g[4] variables:

```
g[8] entry +0x04: dependency_head_g4_idx
  -> g[4][dependency_head_g4_idx] +0x04: next_dependent_g4_idx
    -> g[4][next_dependent_g4_idx] +0x04: next_dependent_g4_idx
      -> ... (up to 4 deep, 0x7FFF terminates)
```

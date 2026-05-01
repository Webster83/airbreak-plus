# as11_config

BLE / CAN configuration and data access tool for AirSense 11 / AirCurve 11 series.

Read and write settings, call JSON-RPC methods, stream live data, subscribe to events, download spool data, and manage BLE [pairing aliases](#devices).

## Connection

BLE:
```
as11_config.py -d ble:alias get SerialNumber
as11_config.py -d ble:AA:BB:CC:DD:EE:FF get SerialNumber
```

CAN:
```
as11_config.py -d can:/dev/ttyACM0 get SerialNumber
as11_config.py -d can:slcan0 --can-flavour socketcan get SerialNumber
```

Prefer `-d ble:...` and `-d can:...` to select the transport target. `--addr` and `-p/--port` are compatibility shortcuts, and `AS11_ADDR` and `AS11_CAN_PORT` are also supported.

## Commands

### get

Read one or more variables by name or group.

```
as11_config.py -d ble:as11 get SerialNumber
as11_config.py -d ble:as11 get _MOP _GOM _TOM
as11_config.py -d ble:as11 get --group DeviceConfiguration
as11_config.py -d ble:as11 get SerialNumber --group Network
```

### set

Write one or more settings using the `Set` RPC. Values default to strings unless `--type` is given.

```
as11_config.py -d ble:as11 set TherapyMode AutoSet
as11_config.py -d ble:as11 set SetPressure 10 --type int RampEnable true --type bool
as11_config.py -d ble:as11 set --json '{"SetPressure":10}'
```

### rpc

Call an arbitrary JSON-RPC method.

```
as11_config.py -d ble:as11 rpc --method GetVersion
as11_config.py -d ble:as11 rpc --method Get --params '["SerialNumber"]'
as11_config.py -d ble:as11 rpc --method SetDateTime --params '{"dateTime":"2026-01-01T00:00:00.000Z"}'
```

### gettime / settime

Read or set the device clock.

```
as11_config.py -d ble:as11 gettime
as11_config.py -d ble:as11 settime
as11_config.py -d ble:as11 settime 2026-01-01T00:00:00Z
as11_config.py -d ble:as11 settime +1h --dry-run
```

### session

Open an interactive REPL and keep the transport open across commands.

```
as11_config.py -d ble:as11 session
```

### stream / subscribe

Receive live NDJSON notifications from the device.

Without `--data-ids` or `--edf`, `stream` requests all EDF alias data IDs
(`BRP`, `PLD`, `SA2`) at the fastest accepted interval:
`sampleIntervalMs=10`, `reportIntervalMs=50`.

```
as11_config.py -d ble:as11 stream
as11_config.py -d can:can0 stream --duration 60
as11_config.py -d can:can0 stream --edf BRP
as11_config.py -d can:can0 stream --edf BRP,PLD --sample-ms 40
as11_config.py -d ble:as11 stream --data-ids Leak-50hz,RespiratoryRate-50hz --duration 60
as11_config.py -d ble:as11 subscribe --duration 60
```

EDF stream aliases:

| Alias | Data IDs |
|-------|----------|
| `BRP` | `PatientFlow-100hz`, `MaskPressure-100hz` |
| `PLD` | `MaskPressure-TwoSecond`, `InspiratoryPressure-TwoSecond`, `ExpiratoryPressure-TwoSecond`, `Leak-50hz`, `RespiratoryRate-50hz`, `TidalVolume-50hz`, `MinuteVentilation-50hz`, `TargetMinuteVentilation`, `IeRatio`, `SnoreIndex-50hz`, `FlowLimitation-50hz`, `InspiratoryDuration` |
| `SA2` | `HeartRate`, `SpO2` |

StartStream interval limits verified so far: minimum sample interval is `10 ms`,
intervals are rounded down to a `10 ms` boundary, and `reportIntervalMs` must
not exceed `sampleIntervalMs * 5`.

### spool

Download spool data, optionally decode it on the host.

```
as11_config.py -d ble:as11 spool Summary
as11_config.py -d ble:as11 spool TherapyEvents-RespiratoryEvents --decode
as11_config.py -d ble:as11 spool Summary --from-dt 2026-01-01T00:00:00.000Z -o summary.bin
as11_config.py -d ble:as11 spool --list-types
```

### known

Offline listing of known variables, groups, streams, events, and spool types.

```
as11_config.py known
as11_config.py known vars
as11_config.py known vars groups
as11_config.py known streams
as11_config.py known streams BRP
as11_config.py known streams BRP,SA2
as11_config.py known edf
as11_config.py known spools
```

`known streams <EDF>` prints the data IDs behind an EDF stream alias.

### devices

BLE device management: scan, pair, list, alias, and unalias.

```
as11_config.py devices scan
as11_config.py -d ble:AA:BB:CC:DD:EE:FF devices pair
as11_config.py devices alias AA:BB:CC:DD:EE:FF bedroom
as11_config.py devices list
```

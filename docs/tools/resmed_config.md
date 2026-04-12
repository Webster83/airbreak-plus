# resmed_config

UART configuration tool for ResMed Air 10 / s9 series

Read, write, dump, and restore device variables over the serial port. Works with direct serial, and TCP via AirBridge.

## Connection

```
resmed_config.py -p /dev/ttyACM0 ...
resmed_config.py -p tcp:airbridge-host ...
```

## Commands

### info

Show device identity (BID, SID, serial number, product name).

```
resmed_config.py -p /dev/ttyACM0 info
```

### get

Read one or more variables by name or group.

```
resmed_config.py -p /dev/ttyACM0 get IPC MPA MPI
resmed_config.py -p /dev/ttyACM0 get MGL
resmed_config.py -p /dev/ttyACM0 get all
```

### set / setv

Write a variable. `set` takes a raw hex value, `setv` takes a human-readable value with automatic scaling.

```
resmed_config.py -p /dev/ttyACM0 set IPC 01F4
resmed_config.py -p /dev/ttyACM0 setv IPC 10.0
resmed_config.py -p /dev/ttyACM0 setv MOP AutoSet
```

### dump / restore

Save all variables to JSON and restore them later.

```
resmed_config.py -p /dev/ttyACM0 dump -o config.json
resmed_config.py -p /dev/ttyACM0 dump --groups MGL EGL -o therapy.json
resmed_config.py -p /dev/ttyACM0 restore -i config.json
resmed_config.py -p /dev/ttyACM0 restore -i config.json --exclude-groups BGL
```

### list

Offline listing of known variables and descriptions.

```
resmed_config.py list
resmed_config.py list --groups MGL DGL
```

### caps

Query variable values and limits from the device.

```
resmed_config.py -p /dev/ttyACM0 caps IPC MOP EPR
```

## Variable groups

| Group | Content |
|-------|---------|
| AGL | AutoSet params |
| BGL | Board/identity |
| CGL | CPAP params |
| DGL | Bilevel timing |
| EGL | EPR params |
| IGL | Bilevel pressure |
| MGL | Machine settings |
| NGL | Backlight (?) |
| PGL | Peripherals/accessories |
| QXH | ASVAuto params |
| QXJ | iVAPS params |
| RGL | Reminders/replacement |
| SGL | System settings |
| UGL | Usage data |
| VGL | VAuto params |
| XGL | ASV fixed params |

# as11_flash

BLE / CAN firmware flash tool for AirSense 11 / AirCurve 11 series.

Push a raw firmware image to the device, target a specific flash block,
optionally apply the upgrade. Builds the `.abc` OTA container internally and
sends it over the same RPC path the device's own updater uses. Supports both
BLE and CAN transports.

## Commands

### flash

Build the OTA container from a raw firmware image and upload it in one step.
This is the primary path -- start here.

```
as11_flash.py flash -d ble:as11 -f patched.bin --block conf+app
as11_flash.py flash -d ble:AA:BB:CC:DD:EE:FF -f patched.bin --block conf+app
as11_flash.py flash -d can:/dev/ttyACM0 -f patched.bin --block conf+app
as11_flash.py flash -d can:can0 --can-flavour socketcan -f patched.bin --block conf+app
as11_flash.py flash -d ble:as11 -f patched.bin --block config --apply-plain
as11_flash.py flash -d ble:as11 -f patched.bin --block full --include-full-flash --apply
```

`-f` accepts a full internal flash image (the patcher's output), an APPL/CONF
extract, or any block payload. The tool auto-detects the layout and packages
the requested `--block` slice. If `--block` is omitted, `flash` guesses a
safe non-bootloader target from the input size when possible.

By default `flash` applies after `CheckUpgradeFile`: authenticated apply on
BLE, plain `ApplyUpgrade` on CAN/TCP. Use `--verify-only` to upload and verify
without rebooting or writing flash.

### upload

Push a pre-built `.abc` container without rebuilding it. Useful when the
container was produced ahead of time or by a separate workflow. Unlike
`flash`, `upload` is verify-only by default.

```
as11_flash.py upload -d ble:as11 patched.abc
as11_flash.py upload -d ble:as11 patched.abc --apply
as11_flash.py upload -d ble:as11 patched.abc --fix-crc
```

### build

Offline: assemble an `.abc` container from a raw image without touching a device.

```
as11_flash.py build -f patched.bin --block firmware -o patched.abc
as11_flash.py build -f patched.bin --block full --include-full-flash -o full.abc
```

### info

Inspect an existing `.abc` container.

```
as11_flash.py info patched.abc
```

### apply

Apply a previously uploaded and verified container. The command can use a
saved `.abc`, a raw firmware image that rebuilds to the same `.abc`, or the
known SHA-256 hash from an earlier successful upload.

```
as11_flash.py apply -d can:/dev/ttyACM0 --hash HASH64
as11_flash.py apply -d can:/dev/ttyACM0 -f patched.bin --block conf+app
as11_flash.py apply -d ble:as11 --abc-file patched.abc
```

### targets

List the supported `--block` names and what they cover.

```
as11_flash.py targets
```

## Flash specific blocks

| Block | Content | Extra flag |
|-------|---------|-----------|
| `config` | `CONF` config/aux block | -- |
| `firmware` / `app` | `APPL` main application image | -- |
| `conf+app` | `APCX` combined config + application range | -- |
| `bootloader` | `FGBL` bootloader / low updater region | `--include-bootloader` |
| `full` / `all` | `FGCB` complete internal flash image | `--include-full-flash` |

```
as11_flash.py flash -d ble:as11 -f patched.bin --block firmware
as11_flash.py flash -d ble:as11 -f patched.bin --block conf+app --apply
```

## Apply modes

| Flag | Effect |
|------|--------|
| no apply flag on `upload` | Verify only; stop after `CheckUpgradeFile` |
| no apply flag on BLE `flash`/`apply` | authenticated apply |
| no apply flag on CAN/TCP `flash`/`apply` | plain `ApplyUpgrade` |
| `--verify-only` | Verify only; stop after `CheckUpgradeFile` |
| `--apply` | Verify, then `ApplyAuthenticatedUpgrade` |
| `--apply-authenticated` | Synonym for `--apply` |
| `--apply-plain` | Verify, then `ApplyUpgrade` (unauthenticated) |

Authenticated apply resolves the OTA signing key from `--key`, `--key-file`,
`$AS11_OTA_KEY`, or a stored BLE device `otaKey`.

### Apply over BLE

The stock BLE RPC exposes authenticated apply, but the HMAC needs the
device's OTA key. Plain `ApplyUpgrade` over BLE needs a firmware permission
patch first. Pick one path before flashing:

1. **Authenticated path.** Retrieve the device's OTA key over SWD/OpenOCD
   using `tcl/as11-keys.tcl` and pass it via `--key`, `--key-file`, or
   `$AS11_OTA_KEY`, or store it as the device alias `otaKey`. The key is
   per-device. Procedure documented in
   [`docs/as11/ota_protocol.md`](../as11/ota_protocol.md#retrieving-the-local-ota-key).

2. **Unauthenticated path (`--apply-plain`).** Flash the `patch-rpc-permissions`
   patch first, which exposes `ApplyUpgrade` on encrypted BLE permission
   selector `0x0396`. Host requests still go over the paired VCID `0x0397`.
   After that `--apply-plain` works over BLE with no key. The first install
   of the patched firmware still has to land via SWD or CAN; subsequent BLE
   flashes can use unauthenticated apply.

CAN exposes `ApplyUpgrade` natively, so `--apply-plain` works there
without either step.

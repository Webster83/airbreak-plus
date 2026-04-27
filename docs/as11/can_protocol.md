# AS11 CAN Protocol

AS11 exposes a local service RPC path on the hidden CAN lines in the power
connector area. The bus also carries diagnostic log traffic.

This document describes the CAN bus and AS11 DatagramCan/RPC framing only. It
does not describe any specific USB-CAN adapter protocol.

## Contents

- [Physical bus](#physical-bus)
- [Known CAN IDs](#known-can-ids)
- [DatagramCan frame format](#datagramcan-frame-format)
  - [Single-frame datagram](#single-frame-datagram)
  - [Multi-frame datagram](#multi-frame-datagram)
- [JSON RPC over CAN](#json-rpc-over-can)
- [Service access](#service-access)
- [Debug log stream](#debug-log-stream)

## Physical bus

Observed electrical/protocol settings:

| Setting | Value |
|---------|-------|
| Bitrate | 1 Mbps |
| Identifier format | standard 11-bit IDs |
| Data frames | classic CAN, 8-byte payloads |
| Transceiver | board has a TLE9250V-class CAN transceiver |


## Known CAN IDs

| CAN ID | Direction | Meaning |
|--------|-----------|---------|
| `0x383` | host to device | JSON RPC request datagrams |
| `0x382` | device to host | JSON RPC response and notification datagrams |
| `0x796` | device to host | CAL/S70 debug log stream |
| `0x2c8` | device to host | `FgPowerup` boot notification |

## DatagramCan frame format

AS11 fragments one datagram across classic 8-byte CAN frames. The low two
bits of byte 0 are the frame flag; observed frames keep the upper bits zero.

### Single-frame datagram

Payloads up to 7 bytes:

```
[0x03] [payload:0..7]
```

### Multi-frame datagram

Payloads longer than 7 bytes:

```
start:  [0x01] [crc32_le:4] [payload bytes 0..2]
middle: [0x00] [payload bytes, up to 7]
end:    [0x02] [payload bytes, up to 7]
```

CRC32 is IEEE CRC32 over the complete reassembled payload. It is checked when
the end frame arrives.

There is no datagram sequence number. The receiver depends on CAN ordering for
frames with the same arbitration ID.

## JSON RPC over CAN

The RPC payload is a UTF-8 JSON object as described in `rpc_protocol.md`,
wrapped in DatagramCan and sent on:

| Direction | CAN ID |
|-----------|--------|
| host to device | `0x383` |
| device to host | `0x382` |

Example request payload before DatagramCan fragmentation:

```json
{"jsonrpc":"2.0","method":"GetVersion","id":1}
```

The device response is a DatagramCan payload on `0x382`:

```json
{"jsonrpc":"2.0","id":1,"result":{"RPC":{"GetVersion":"2.0"}}}
```

Notifications have a `method` field and no `id`. They can arrive while a
request is waiting for its matching response.

## Service access

The CAN RPC endpoint exposes a service-level method set, including methods not
normally visible on the paired BLE patient path. Examples include
`SetDateTime`, `ApplyUpgrade`, `ResetDevice`, `StoreSecurityData`,
`VerifySecurityData`, `ClearAutoConnectList`, and `EnableSecurity`.

This is a plaintext local service lane. The protocol does not add the BLE
SRP/AES layer.

## Debug log stream

CAN ID `0x796` carries CAL/S70 debug log text. The stream can contain boot
messages, internal JSON-RPC traffic to the cellular side, and application log
lines. Typical text includes records such as:

```text
S703CChecking CalManufacturingMode
S7048RPC TX:{"jsonrpc":"2.0","id":1,"method":"Get","params":["UniversalIdentifier"]}
```

The first byte of each 8-byte CAN frame belongs to DatagramCan framing on
modern captures, so text consumers should decode the datagram layer before
parsing the S70 records.

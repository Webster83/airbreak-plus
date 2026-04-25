"""Spool (device-side data archive) support. Transport-agnostic.

Protocol dance plus protobuf payload decoders. 
"""

from __future__ import annotations

import base64
import hashlib
import logging
import sys
from typing import Iterator


log = logging.getLogger("as11.spool")


# Single-round spool cycle. Transport-agnostic.

def spool_one_round(transport, spool_address: dict, max_size: int,
                    *, fragment_timeout: float = 30.0,
                    fragment_max: int = 2808,
                    ) -> tuple[bytes, str, dict | None, int]:
    """Run one StartSpool -> PullSpoolFragments cycle against `transport`.

    Returns (data_bytes, status, next_spool_address_or_None, frag_count).
    Verifies per-round SHA256 against spoolHash reported by the device.

    `transport` must implement the as11_rpc.Transport protocol with a
    working `listen_for_notifications`.
    """
    fragments: list[tuple[int, bytes]] = []
    state = {"status": "", "hash": "", "next": None, "done": False}

    def on_notify(msg: dict):
        if msg.get("method") != "SpoolFragment":
            return None
        params = msg.get("params", {})
        seq = params.get("seq", -1)
        data_b64 = params.get("data", "")
        status = params.get("status", "")
        if data_b64:
            try:
                fragments.append((seq, base64.b64decode(data_b64)))
            except Exception as exc:
                log.warning("SpoolFragment seq=%d base64 decode failed: %s",
                            seq, exc)
        print(f"  fragment seq={seq} len={len(data_b64)} status={status}",
              file=sys.stderr, flush=True)
        state["status"] = status
        state["hash"] = params.get("spoolHash", "")
        state["next"] = params.get("nextSpoolAddress")
        if status != "SPOOL_INCOMPLETE":
            state["done"] = True
            return True   # stop listener
        return None

    transport.set_notification_handler(on_notify)
    try:
        resp = transport.rpc("StartSpool", {
            "spoolAddress": spool_address,
            "maxSpoolSize": max_size,
        })
        spool_id = resp.get("result", {}).get("spoolId", 0)
        print(f"StartSpool: spoolId={spool_id}", file=sys.stderr)
        if spool_id == 0:
            return b"", "", None, 0

        transport.rpc("PullSpoolFragments", {
            "spoolId": spool_id,
            "maxFragmentSize": fragment_max,
            "maxNotifications": 0,
        }, timeout=5.0)

        transport.listen_for_notifications(duration=fragment_timeout)
    finally:
        transport.set_notification_handler(None)

    fragments.sort(key=lambda x: x[0])
    data = b"".join(f[1] for f in fragments)

    expected = state["hash"]
    if expected:
        actual = hashlib.sha256(data).hexdigest().upper()
        ok = "OK" if actual == expected.upper() else "MISMATCH"
        print(f"  SHA256: {ok} ({len(data)} bytes, {len(fragments)} fragments)",
              file=sys.stderr)
    elif not state["done"]:
        print(f"  warning: no terminal fragment received within "
              f"{fragment_timeout:.0f}s; got {len(fragments)} fragments "
              f"({len(data)} bytes)", file=sys.stderr)

    return data, state["status"], state["next"], len(fragments)



_PROTO_WIRE = {0: "varint", 1: "64-bit", 2: "bytes", 5: "32-bit"}


def _proto_read_varint(data, i):
    v = 0; shift = 0
    while True:
        b = data[i]; i += 1
        v |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return v, i
        shift += 7


def proto_decode(data: bytes) -> list[tuple[int, int, object]]:
    """Walk protobuf wire format. Returns [(field, wire, value), ...]."""
    out = []
    i = 0
    while i < len(data):
        key, i = _proto_read_varint(data, i)
        field = key >> 3
        wire = key & 7
        if wire == 0:
            v, i = _proto_read_varint(data, i); out.append((field, wire, v))
        elif wire == 1:
            out.append((field, wire, int.from_bytes(data[i:i + 8], "little"))); i += 8
        elif wire == 2:
            ln, i = _proto_read_varint(data, i)
            out.append((field, wire, bytes(data[i:i + ln]))); i += ln
        elif wire == 5:
            out.append((field, wire, int.from_bytes(data[i:i + 4], "little"))); i += 4
        else:
            raise ValueError(f"unsupported wire type {wire} at offset {i}")
    return out


def proto_pretty(data: bytes, indent: int = 0, out=None) -> None:
    """Pretty-print protobuf blob with nested-message heuristic."""
    from datetime import datetime, timezone
    if out is None:
        out = sys.stdout
    pad = "  " * indent
    for field, wire, value in proto_decode(data):
        if wire == 2:
            try:
                sub = proto_decode(value)
                if sub and all(0 < f < 2**29 for f, _, _ in sub):
                    print(f"{pad}{field} (msg, {len(value)}B):", file=out)
                    proto_pretty(value, indent + 1, out)
                    continue
            except (ValueError, IndexError):
                pass
            if value and all(32 <= b < 127 for b in value):
                print(f"{pad}{field} (str): {value.decode()!r}", file=out)
            else:
                h = value.hex()
                if len(h) > 80:
                    h = h[:80] + "..."
                print(f"{pad}{field} (bytes {len(value)}B): {h}", file=out)
        elif wire == 0:
            note = ""
            if 10**12 < value < 2 * 10**12:
                try:
                    note = f" [~{datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()}]"
                except (OverflowError, OSError):
                    pass
            elif 10**9 < value < 2 * 10**9:
                try:
                    note = f" [~{datetime.fromtimestamp(value, timezone.utc).isoformat()}]"
                except (OverflowError, OSError):
                    pass
            print(f"{pad}{field} (varint): {value}{note}", file=out)
        else:
            print(f"{pad}{field} ({_PROTO_WIRE.get(wire, wire)}): {value}", file=out)



SPOOL_LEGENDS: dict[str, dict] = {
    "TherapyEvents-RespiratoryEvents": {
        "event_types": {
            2: "Hypopnea", 3: "CentralApnea", 4: "ObstructiveApnea",
            5: "Apnea", 6: "Arousal",
        },
    },
}


_SUMMARY_FIELDS = {
    1:  "f1_init_marker",
    2:  "f2_clockA_start",
    3:  "f3_clockA_end",
    4:  "f4_clockA_diff_over_60000",
    5:  "f5_tag01",
    6:  "f6_init_session_struct",
    7:  "AHI (Summary-ApneaHypopneaIndex)",
    8:  "ApneaIndex",
    9:  "HypopneaIndex",
    10: "ObstructiveApneaIndex",
    11: "CentralApneaIndex",
    12: "UnknownApneaIndex",
    13: "ReraIndex",
    14: "Leak",
    15: "InspiratoryPressure",
    16: "f16_CSD",
    17: "f17_SAU",
    18: "SpontTriggerPercentage",
    19: "SpontCyclePercentage",
    20: "ExpiratoryPressure",
    21: "MeanMaskPressure",
    22: "TidalVolume",
    23: "MinuteVentilation",
    24: "TargetMinuteVentilation",
    25: "RespiratoryRate",
    26: "InspiratoryDuration",
    27: "IeRatio",
    28: "SpO2",
    29: "AmbientHumidity",
    30: "HumidifierTemperature",
    31: "HeatedTubeTemperature",
    32: "HumidifierPower",
    33: "HeatedTubePower",
    34: "HumidifierConnected (enum)",
    35: "TubeConnected (enum)",
    36: "BlowerPressure",
    37: "RespiratoryFlow",
    38: "BlowerFlow",
    39: "f39_unsourced",
    40: "f40_clockB",
    41: "HeartRate",
    42: "f42_AV*",
    43: "f43_unsourced",
}

_SUMMARY_SUBFIELDS = {
    14: {2: (50, 2.0), 3: (70, 2.0), 4: (95, 2.0), 5: (100, 2.0)},  # Leak
    15: {2: (50, 2.0), 3: (95, 2.0), 4: (100, 2.0)},
    20: {2: (50, 2.0), 3: (95, 2.0), 4: (100, 2.0)},
    21: {2: (50, 2.0), 3: (95, 2.0), 4: (100, 2.0)},
    22: {2: (50, 2.0), 3: (95, 2.0), 4: (100, 2.0)},
    23: {2: (50, 8.0), 3: (95, 8.0), 4: (100, 8.0)},
    24: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},
    25: {2: (50, 5.0), 3: (95, 5.0), 4: (100, 5.0)},
    26: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},
    27: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},
    28: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},
    29: {2: (50, 10.0)},
    30: {2: (50, 10.0)},
    31: {2: (50, 10.0)},
    32: {2: (50, 10.0)},
    33: {2: (50, 10.0)},
    36: {1: (5, 2.0),  3: (95, 2.0)},
    37: {1: (5, 0.2),  3: (95, 0.2)},
    38: {2: (50, 0.2)},
    41: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},
    42: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},
}


def summary_pretty(data: bytes, out=None) -> None:
    """Pretty-print the Summary protobuf using firmware-verified field names."""
    if out is None:
        out = sys.stdout

    while True:
        try:
            top = proto_decode(data)
        except (ValueError, IndexError):
            break
        if (len(top) == 1 and top[0][1] == 2
                and isinstance(top[0][2], (bytes, bytearray))):
            data = top[0][2]
            continue
        break
    for field, wire, value in proto_decode(data):
        label = _SUMMARY_FIELDS.get(field, f"field_{field}")
        if wire == 2:
            try:
                subs = proto_decode(value)
            except (ValueError, IndexError):
                subs = None
            if subs:
                print(f"{label} (msg, {len(value)}B):", file=out)
                submap = _SUMMARY_SUBFIELDS.get(field, {})
                for sf, sw, sv in subs:
                    if sf in submap:
                        pct, mult = submap[sf]
                        tail = f"  # p{pct}, mult={mult}x (wire=raw*mult)"
                    else:
                        tail = ""
                    print(f"  sub_f{sf} ({_PROTO_WIRE.get(sw, sw)}): {sv}{tail}",
                          file=out)
            else:
                h = value.hex()
                if len(h) > 80:
                    h = h[:80] + "..."
                print(f"{label} (bytes {len(value)}B): {h}", file=out)
        elif wire == 0:
            print(f"{label} (varint): {value}", file=out)
        elif wire == 1:
            print(f"{label} (u64): {value}", file=out)
        elif wire == 5:
            print(f"{label} (u32): {value}", file=out)
        else:
            print(f"{label} ({_PROTO_WIRE.get(wire, wire)}): {value}", file=out)


def print_spool_legend(spool_type: str) -> None:
    legend = SPOOL_LEGENDS.get(spool_type)
    if not legend:
        return
    et = legend.get("event_types")
    if et:
        print("# event record layout: field 1 = type, field 2 = start_ms, "
              "field 3 = end_ms, field 4 = duration_ms")
        parts = ", ".join(f"{k}={v}" for k, v in sorted(et.items()))
        print(f"# event types: {parts}")
        print()


def spool_walk_events(data: bytes, depth: int = 0) -> Iterator[bytes]:
    """Yield event records (field 1 innermost repeated) from spool payload."""
    try:
        for field, wire, value in proto_decode(data):
            if wire == 2:
                if depth < 2:
                    yield from spool_walk_events(value, depth + 1)
                elif depth == 2 and field == 1:
                    yield value
    except (ValueError, IndexError):
        pass


def print_spool_summary(spool_type: str, data: bytes) -> None:
    legend = SPOOL_LEGENDS.get(spool_type)
    if not legend:
        return
    et = legend.get("event_types")
    if not et:
        return
    from collections import Counter
    counts = Counter()
    total = 0
    for ev in spool_walk_events(data):
        total += 1
        try:
            for field, wire, value in proto_decode(ev):
                if field == 1 and wire == 0:
                    counts[value] += 1
                    break
        except (ValueError, IndexError):
            pass
    if total:
        print()
        print(f"# summary: {total} events")
        for k in sorted(counts):
            print(f"#   {et.get(k, f'type={k}'):20s} {counts[k]:6d}")


__all__ = [
    "SPOOL_LEGENDS",
    "spool_one_round",
    "proto_decode", "proto_pretty",
    "summary_pretty",
    "print_spool_legend", "print_spool_summary", "spool_walk_events",
]

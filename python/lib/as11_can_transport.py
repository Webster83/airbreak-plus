#!/usr/bin/env python3
"""CAN transport flavour selection."""

from __future__ import annotations

import argparse
from importlib import import_module
from as11_can_common import DEFAULT_RPC_RX_ID, DEFAULT_RPC_TX_ID, parse_int


CAN_TRANSPORTS = {
    "waveshare": ("as11_can_waveshare", "CanWaveshareTransport"),
    "canable": ("as11_can_canable", "CanCanableTransport"),
    "socketcan": ("as11_can_socketcan", "CanSocketcanTransport"),
}


def add_args(p: argparse.ArgumentParser) -> None:
    suppr = argparse.SUPPRESS
    g = p.add_argument_group("CAN adapter (ignored unless -d can:...)")
    g.add_argument("--can-flavour", default=suppr,
                   choices=tuple(CAN_TRANSPORTS),
                   help="which CAN adapter protocol to use (default: canable)")
    g.add_argument("--serial-baud", type=int, default=suppr,
                   help="serial adapter baud / line coding (backend default if omitted)")
    g.add_argument("--bitrate", type=parse_int, default=suppr,
                   help="CAN bitrate (default: 1000000)")
    g.add_argument("--mode", choices=("normal", "silent"), default=suppr,
                   help="adapter CAN mode (default: normal)")
    g.add_argument("--no-reset-buffers", action="store_true", default=suppr)
    g.add_argument("--dtr", dest="dtr", action="store_true", default=suppr)
    g.add_argument("--no-dtr", dest="dtr", action="store_false")
    g.add_argument("--rts", dest="rts", action="store_true", default=suppr)
    g.add_argument("--no-rts", dest="rts", action="store_false")
    g.add_argument("--tx-id", type=parse_int, default=suppr,
                   help=f"CAN host->device ID (default 0x{DEFAULT_RPC_TX_ID:03X})")
    g.add_argument("--rx-id", type=parse_int, default=suppr,
                   help=f"CAN device->host ID (default 0x{DEFAULT_RPC_RX_ID:03X})")
    g.add_argument("--frame-interval", type=float, default=suppr,
                   help="delay between outgoing CAN frames in a datagram (default: 0)")

def from_args(target: str, args: argparse.Namespace):
    flavour = getattr(args, "can_flavour", "canable")
    try:
        module_name, class_name = CAN_TRANSPORTS[flavour]
    except KeyError as exc:
        supported = ", ".join(repr(name) for name in sorted(CAN_TRANSPORTS))
        raise SystemExit(
            f"unsupported --can-flavour {flavour!r} (supported: {supported})"
        ) from exc
    module = import_module(module_name)
    transport_cls = getattr(module, class_name)
    return transport_cls.from_args(target, args)


__all__ = ["CAN_TRANSPORTS", "add_args", "from_args"]

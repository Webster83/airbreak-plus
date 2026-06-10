#!/usr/bin/env python3
"""CAN transport flavour selection."""

from __future__ import annotations

import argparse
import os
import re
from importlib import import_module
from as11_can_common import DEFAULT_RPC_RX_ID, DEFAULT_RPC_TX_ID, parse_int


CAN_TRANSPORTS = {
    "slcan": ("as11_can_canable", "CanCanableTransport"),
    "waveshare": ("as11_can_waveshare", "CanWaveshareTransport"),
    "canable": ("as11_can_canable", "CanCanableTransport"),
    "socketcan": ("as11_can_socketcan", "CanSocketcanTransport"),
}
CAN_FLAVOUR_ALIASES = {
    "canable": "slcan",
}


def add_args(p: argparse.ArgumentParser) -> None:
    suppr = argparse.SUPPRESS
    g = p.add_argument_group("CAN adapter (ignored unless -d can:...)")
    g.add_argument("--can-flavour", default=suppr,
                   choices=tuple(CAN_TRANSPORTS),
                   help="CAN adapter protocol. By default this is inferred from can:<target>")
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


def split_flavour_target(target: str) -> tuple[str | None, str]:
    """Return (explicit_flavour, stripped_target) for can:<flavour>:<target>."""
    prefix, sep, rest = target.partition(":")
    if sep and prefix in CAN_TRANSPORTS:
        if not rest:
            raise SystemExit(f"can:{prefix}: needs adapter target")
        return CAN_FLAVOUR_ALIASES.get(prefix, prefix), rest
    return None, target


def infer_flavour(target: str) -> str:
    """Pick the most likely CAN backend from the target spelling."""
    if re.fullmatch(r"(?:v?can|slcan)\d+", target):
        return "socketcan"

    basename = os.path.basename(target).lower()
    if (basename.startswith("ttyacm") or basename.startswith("ttyusb")
            or re.fullmatch(r"com\d+", target.lower())):
        return "slcan"

    return "slcan"


def from_args(target: str, args: argparse.Namespace):
    target_flavour, target = split_flavour_target(target)
    arg_flavour = getattr(args, "can_flavour", None)
    if arg_flavour:
        arg_flavour = CAN_FLAVOUR_ALIASES.get(arg_flavour, arg_flavour)
    if arg_flavour and target_flavour and arg_flavour != target_flavour:
        raise SystemExit(
            f"CAN flavour mismatch: target requests {target_flavour!r}, "
            f"but --can-flavour is {arg_flavour!r}"
        )
    flavour = arg_flavour or target_flavour or infer_flavour(target)
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


__all__ = [
    "CAN_TRANSPORTS",
    "add_args",
    "from_args",
    "infer_flavour",
    "split_flavour_target",
]

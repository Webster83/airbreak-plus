#!/usr/bin/env python3
import sys
import argparse
import zlib

CRC_LEN = 8
CRC_END = 0x75

FIELDS = {
    "PSH": {"off": 0x00, "len": 4,  "desc": "pressure sensor gain"},
    "PZH": {"off": 0x04, "len": 4,  "desc": "pressure sensor zero offset"},
    "FLG": {"off": 0x08, "len": 4,  "desc": "flow sensor gain"},
    "FLZ": {"off": 0x0C, "len": 4,  "desc": "flow sensor zero offset"},
    "SNZ": {"off": 0x10, "len": 3,  "desc": ""},
    "SNB": {"off": 0x13, "len": 3,  "desc": ""},
    "PCB": {"off": 0x16, "len": 31, "desc": ""},
    "PCD": {"off": 0x36, "len": 5,  "desc": "product code"},
    "SRN": {"off": 0x40, "len": 11, "desc": "serial number"},
    "PNA": {"off": 0x52, "len": 32, "desc": "product name"},
    "CCP": {"off": 0x72, "len": 2,  "desc": ""},
    "CCS": {"off": 0x74, "len": 2,  "desc": ""},
}

ALIASES = {
    "name": "PNA",
    "serial": "SRN",
}


def get_field(data: bytes, key: str) -> str:
    f = FIELDS[key]
    raw = data[f["off"]:f["off"] + f["len"]]
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="strict")

def set_field(data: bytearray, key: str, value: bytes):
    f = FIELDS[key]
    max_len = f["len"]

    if key in ("PNA"):
        if len(value) > max_len:
            raise ValueError(f"PNA/name too long (max {max_len} bytes)")

        padded = value + b"\x00" * (max_len - len(value))
        data[f["off"]:f["off"] + max_len] = padded
        return

    if len(value) != f["len"]:
        raise ValueError(f"{key} must be exactly {f['len']} bytes")

    data[f["off"]:f["off"] + f["len"]] = value

def fix_crc(data: bytearray):
    crc = zlib.crc32(data[:CRC_END + 1]) & 0xffffffff
    data[-CRC_LEN:] = f"{crc:08X}".encode("ascii")


def build_argparser():
    p = argparse.ArgumentParser(
        description="Inspect or patch AirSense calibration / identity fields"
    )

    p.add_argument(
        "input",
        help="input file or '-' for stdin",
    )

    p.add_argument(
        "-o", "--output",
        type=argparse.FileType("wb"),
        default=sys.stdout.buffer,
        help="output file (default: stdout)",
    )

    for key, meta in FIELDS.items():
        names = [f"--{key.lower()}"]
        for alias, target in ALIASES.items():
            if target == key:
                names.append(f"--{alias}")

        p.add_argument(
            *names,
            nargs="?",
            const="__GET__",
            metavar="VALUE",
            help=f"{key}: {meta['desc']}",
        )

    return p


def main():
    args = build_argparser().parse_args()

    if args.input == "-":
        data = bytearray(sys.stdin.buffer.read())
    else:
        with open(args.input, "rb") as f:
            data = bytearray(f.read())


    getters = []
    setters = []

    for arg, value in vars(args).items():
        if arg in ("input", "output") or value is None:
            continue

        key = ALIASES.get(arg, arg).upper()

        if value == "__GET__":
            getters.append(key)
        else:
            setters.append((key, value))

    if getters and setters:
        sys.exit("error: cannot mix getters (--field) and setters (--field VALUE)")

    out = args.output

    if not getters and not setters:
        for key in FIELDS:
            out.write(f"{key}={get_field(data, key)}\n".encode("ascii"))
        return

    if getters:
        for key in getters:
            out.write(f"{key}={get_field(data, key)}\n".encode("ascii"))
        return

    for key, value in setters:
        try:
            set_field(data, key, value.encode("ascii"))
        except ValueError as e:
            sys.exit(f"error: {e}")

    fix_crc(data)
    out.write(data)


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
AS11 OTA uploader.

Examples:
    as11_ota.py targets
    as11_ota.py build --block config --desc-preset 15.8.4.0 -f firmware.bin -o Upgrade-CONF.abc
    as11_ota.py info Upgrade-CONF.abc
    as11_ota.py --addr as11 upload Upgrade-CONF.abc
    as11_ota.py --addr as11 flash --block config -f firmware.bin
    as11_ota.py --addr as11 flash --block full --format 0006 --include-full-flash --apply --key $KOTA -f firmware.bin
"""

from __future__ import annotations

import argparse
import asyncio
import binascii
import hashlib
import hmac
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# defer import to allow offline target to work without ble stack
def _import_ble():
    try:
        from as11_ble import As11Connection, load_credentials, resolve_addr
    except ImportError as e:
        raise SystemExit(
            f"BLE functionality requires as11_ble (which imports bleak): {e}\n"
            f"run this from the python/ directory, or install bleak")
    return As11Connection, load_credentials, resolve_addr

log = logging.getLogger("as11_ota")


_FORCE_HELP = ("override local validation warnings (input image HW CRC "
               "mismatch, descriptor CRC mismatch, unexpected payload size)")


MAGIC          = b"OTA!"
FORMAT_0005    = b"0005"
FORMAT_0006    = b"0006"
PRIMARY_SIZE   = 0x58
DESCRIPTOR_SIZE = 0x50
PAYLOAD_OFFSET_0005 = PRIMARY_SIZE + DESCRIPTOR_SIZE   # 0xa8
PAYLOAD_OFFSET_0006 = PRIMARY_SIZE                     # 0x58

OFF_MAGIC      = 0x00
OFF_FORMAT     = 0x04
OFF_COMPONENT  = 0x48
COMPONENT_LEN  = 0x10

DEFAULT_COMPONENT_0005 = "PacificFG"
COMPONENTS_0006 = ("PacificFG", "AlarmModule")

# (parser cap is 1000 hex chars = 500 bytes).
XFER_RAW_BYTES    = 500
LONG_RPC_TIMEOUT  = 120.0   # CheckUpgradeFile / Apply* drain NOR flash; be patient
BLOCK_RPC_TIMEOUT = 15.0

FLASH_BASE       = 0x08000000
FULL_FLASH_SIZE  = 0x00200000



@dataclass(frozen=True)
class TargetRegion:
    code: str
    flash_start: int
    size: int
    desc2_required: bool = False
    desc3_required: bool = False
    danger_flag: str | None = None
    notes: str = ""
    # True for primitive HW regions that each carry their own CRC16-CCITT
    atomic: bool = False

    def __post_init__(self) -> None:
        if len(self.code.encode("ascii")) != 4:
            raise ValueError(
                f"TargetRegion code must be exactly 4 ASCII bytes, "
                f"got {self.code!r}")

    @property
    def full_image_offset(self) -> int:
        return self.flash_start - FLASH_BASE

    @property
    def flash_end(self) -> int:
        return self.flash_start + self.size


TARGETS: dict[str, TargetRegion] = {
    "APPL": TargetRegion(
        "APPL", flash_start=0x08040000, size=0x001C0000,
        desc2_required=True, desc3_required=True,
        atomic=True,
        notes="main app image"),
    "CONF": TargetRegion(
        "CONF", flash_start=0x08020000, size=0x00020000,
        desc2_required=True,
        atomic=True,
        notes="config/aux block before app"),
    "APCX": TargetRegion(
        "APCX", flash_start=0x08020000, size=0x001E0000,
        desc3_required=True,
        notes="combined CONF+APPL range"),
    "FGBL": TargetRegion(
        "FGBL", flash_start=0x08000000, size=0x00020000,
        desc3_required=True,
        atomic=True,
        danger_flag="include_bootloader",
        notes="bootloader / low updater region"),
    "FGCB": TargetRegion(
        "FGCB", flash_start=0x08000000, size=0x00200000,
        danger_flag="include_full_flash",
        notes="complete internal flash image"),
}


BLOCK_ALIASES: dict[str, str] = {
    # canonical codes always accepted, any case
    **{code.lower(): code for code in TARGETS},
    # friendly names
    "config":          "CONF",
    "firmware":        "APPL",
    "app":             "APPL",
    "conf+app":        "APCX",
    "config+firmware": "APCX",
    "bootloader":      "FGBL",
    "full":            "FGCB",
    "all":             "FGCB",
}

# Per-firmware descriptor presets for 0005 containers. 
# These are the firmware backed constants that compared against descriptor
# offsets 0x08 and 0x0c respectively.
# Only CONF/APPL/APCX/FGBL targets need them. FGCB (and all of format 0006)
# ignores these fields.
DESC_PRESETS = {
    "14.8.3.0": {
        "desc2": 0x2D89E58F,
        "desc3": 0xBEB37EE2,
    },
    "15.8.4.0": {
        "desc2": 0xD785ABA6,
        "desc3": 0xBEB37EE2,
    },
}

# K_ota is the 32-byte HMAC key the OTA verifier signs authenticated-apply
# tags with. Pulled via SWD from SecurityDataServer this+0x108
# Whether this key is the same across all AS11 units or provisioned per-device is an open question
# if ApplyAuthenticatedUpgrade fails with -11306, it's per-device and you need to extract your own.
DEFAULT_K_OTA_HEX = "9bc3e80b872227305052e5d045d8297ee90b0ddb49212a91bdad4ebbaa981368"


# ---------------------------------------------------------------------------

def u32_le(value: int) -> bytes:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"u32 out of range: {value!r}")
    return value.to_bytes(4, "little")


def get_u32(buf: bytes, off: int) -> int:
    return int.from_bytes(buf[off:off + 4], "little")


def put_u32(buf: bytearray, off: int, value: int) -> None:
    buf[off:off + 4] = u32_le(value)


def crc32_final(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc


def regions_in_payload(target: TargetRegion) -> list[tuple[str, int, int]]:
    t_start = target.full_image_offset
    t_end   = t_start + target.size
    atomics = sorted((t for t in TARGETS.values() if t.atomic),
                     key=lambda t: t.full_image_offset)
    return [(hw.code, hw.full_image_offset - t_start, hw.size)
            for hw in atomics
            if hw.full_image_offset >= t_start
            and hw.full_image_offset + hw.size <= t_end]


def verify_payload_crcs(payload: bytes, target: TargetRegion
                        ) -> list[tuple[str, int, int, bool]]:
    out = []
    for (name, off, size) in regions_in_payload(target):
        if off + size > len(payload):
            continue
        stored   = int.from_bytes(payload[off + size - 2:off + size], "big")
        computed = crc16_ccitt(payload[off:off + size - 2])
        out.append((name, stored, computed, stored == computed))
    return out


def fix_payload_crcs(payload: bytes, target: TargetRegion
                     ) -> tuple[bytes, list[tuple[str, int]]]:
    """Return (patched_payload, [(region, new_crc), ...])."""
    buf = bytearray(payload)
    fixed = []
    for (name, off, size) in regions_in_payload(target):
        if off + size > len(buf):
            continue
        crc = crc16_ccitt(bytes(buf[off:off + size - 2]))
        buf[off + size - 2] = (crc >> 8) & 0xFF
        buf[off + size - 1] = crc & 0xFF
        fixed.append((name, crc))
    return bytes(buf), fixed


def parse_u32(text: str | None, *, name: str) -> int | None:
    if text is None:
        return None
    s = text.strip().replace("_", "")
    if not s:
        return None
    try:
        if s.lower().startswith("0x"):
            value = int(s, 16)
        elif any(c in "abcdefABCDEF" for c in s):
            value = int(s, 16)
        else:
            value = int(s, 10)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"{name} is not an integer: {text!r}") from e
    if not 0 <= value <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError(
            f"{name} does not fit in u32: {text!r}")
    return value


_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)")


def normalize_version(raw: str | None) -> str | None:
    """Extract the first 4-dotted-digit semver-like prefix"""
    if not raw:
        return None
    m = _VERSION_RE.search(str(raw))
    return m.group(1) if m else None


async def fetch_pci(conn) -> int | None:
    """Query the device's PCI value. Returns None on any failure

    We also query `_PRI` in the same call for log context - if PRI==0
    the device doesn't actually check PCI, so the fallback to 0 when
    PCI fetch fails is harmless on that device.
    """
    try:
        resp = await conn.send_rpc("Get", ["_PCI", "_PRI"],
                                   encrypted=True, timeout=10.0)
    except Exception as e:
        log.warning("Get(_PCI,_PRI) failed: %s", e)
        return None
    result = resp.get("result")
    if not isinstance(result, dict):
        log.warning("Get(_PCI,_PRI) returned unexpected shape: %r", result)
        return None

    pri = result.get("_PRI")
    pci = result.get("_PCI")
    log.info("device reports _PRI=%r  _PCI=%r", pri, pci)

    if pci is None:
        return None
    try:
        return int(pci) & 0xFFFFFFFF
    except (TypeError, ValueError):
        log.warning("Get(_PCI) returned %r; can't coerce to int", pci)
        return None


async def fetch_firmware_version(conn) -> str | None:
    """Query the device's ApplicationIdentifier and return a normalized
    "major.minor.build.sub" string, or None on failure.
    """
    try:
        resp = await conn.send_rpc("Get", ["ApplicationIdentifier"],
                                   encrypted=True, timeout=10.0)
    except Exception as e:
        log.warning("Get(ApplicationIdentifier) failed: %s", e)
        return None
    result = resp.get("result")
    if isinstance(result, dict):
        return normalize_version(result.get("ApplicationIdentifier"))
    if isinstance(result, str):
        return normalize_version(result)
    return None


def resolve_block(raw: str) -> TargetRegion:
    code = BLOCK_ALIASES.get(raw.lower())
    if code is None:
        canon = sorted(TARGETS)
        aliases = sorted(k for k in BLOCK_ALIASES if k not in {c.lower() for c in TARGETS})
        raise SystemExit(f"unknown block {raw!r}. "
                         f"Canonical codes: {', '.join(canon)}. "
                         f"Aliases: {', '.join(aliases)}.")
    return TARGETS[code]


def parse_key(key_hex: str | None, key_file: str | None) -> bytes:
    """Resolve K_ota. Precedence: --key > --key-file > DEFAULT_K_OTA_HEX"""
    if key_hex and key_file:
        raise SystemExit("pass only one of --key / --key-file")
    if key_hex:
        raw = bytes.fromhex(key_hex.strip())
        source = "--key"
    elif key_file:
        data = Path(key_file).read_bytes()
        if len(data) == 32:
            raw = data
        else:
            raw = bytes.fromhex(data.decode("ascii").strip())
        source = f"--key-file {key_file}"
    else:
        raw = bytes.fromhex(DEFAULT_K_OTA_HEX)
        source = "built-in DEFAULT_K_OTA_HEX"
        log.warning("no --key/--key-file passed; using %s. "
                    "If ApplyAuthenticatedUpgrade fails with -11306, "
                    "K_ota is per-device and you need to extract your own.",
                    source)
    if len(raw) != 32:
        raise SystemExit(f"K_ota must be exactly 32 bytes, got {len(raw)} "
                         f"(source: {source})")
    return raw



def load_payload(args, target: TargetRegion) -> bytes:
    """Resolve the firmware input per args.from_full / args.payload / args.file.

    - --from-full: treat the file as a 2 MiB full internal dump and slice
      the target region out.
    - --payload: treat the file as already the target region's bytes.
    - -f/--file (auto): inspect file size, choose full-dump vs pre-sliced.
    """
    sources = [name for name, v in (
        ("--from-full", getattr(args, "from_full", None)),
        ("--payload",   getattr(args, "payload", None)),
        ("-f/--file",   getattr(args, "file", None)),
    ) if v]
    if len(sources) == 0:
        raise SystemExit("source file required: pass -f/--file, --from-full, or --payload")
    if len(sources) > 1:
        raise SystemExit(f"conflicting source args: {', '.join(sources)}; pick one")

    allow_mismatch = getattr(args, "force", False)

    if getattr(args, "from_full", None):
        full = Path(args.from_full).read_bytes()
        start, end = target.full_image_offset, target.full_image_offset + target.size
        if len(full) < end:
            raise SystemExit(f"{args.from_full}: too short for {target.code}; "
                             f"need at least 0x{end:x} bytes, got 0x{len(full):x}")
        if len(full) != FULL_FLASH_SIZE:
            print(f"warning: {args.from_full} is {len(full)} bytes, "
                  f"expected {FULL_FLASH_SIZE} for a full internal flash image",
                  file=sys.stderr)
        return full[start:end]

    if getattr(args, "payload", None):
        data = Path(args.payload).read_bytes()
        if len(data) != target.size and not allow_mismatch:
            raise SystemExit(
                f"{args.payload}: {target.code} payload must be {target.size} "
                f"bytes (got {len(data)}). Pass --force to override.")
        return data

    # auto-detect from -f/--file
    path = args.file
    data = Path(path).read_bytes()
    if len(data) == target.size:
        return data
    if len(data) == FULL_FLASH_SIZE:
        start, end = target.full_image_offset, target.full_image_offset + target.size
        return data[start:end]
    if allow_mismatch:
        print(f"warning: {path} is {len(data)} bytes - neither {target.size} "
              f"nor {FULL_FLASH_SIZE}; --force in effect", file=sys.stderr)
        return data
    raise SystemExit(
        f"{path}: cannot auto-detect source for {target.code}; got {len(data)} bytes. "
        f"Expected a {target.size}-byte {target.code} payload or a "
        f"{FULL_FLASH_SIZE}-byte full internal dump. Use --from-full or "
        f"--payload to force non-standard interpretation.")


def _auto_preset_needed(args, target: TargetRegion) -> bool:
    """
    False when the target ignores desc2/desc3 (FGCB), when the format is 0006
    (no secondary descriptor at all), or when the user already supplied
    explicit overrides for every required slot.
    """
    if getattr(args, "format", "0005") != "0005":
        return False
    if not target.desc2_required and not target.desc3_required:
        return False
    have_desc2 = parse_u32(getattr(args, "desc2", None), name="desc2") is not None
    have_desc3 = parse_u32(getattr(args, "desc3", None), name="desc3") is not None
    if target.desc2_required and not have_desc2: return True
    if target.desc3_required and not have_desc3: return True
    return False


def resolve_descriptor_words(args, target: TargetRegion,
                             *, detected_preset: str | None = None
                             ) -> tuple[int, int, int]:
    """Combine --desc-preset with explicit --desc2/--desc3/--pci.

    `detected_preset` is the firmware version string auto-detected by
    `cmd_flash`. When `args.desc_preset == "auto"` it substitutes in.

    Every "auto but detection failed" or "auto but version not in presets"
    case is caught earlier (by `cmd_flash.detect_preset_for_descriptor` or
    `cmd_build`'s pre-check). By the time we get here, if desc_preset is
    "auto" we either have a valid detected_preset, or the target doesn't
    actually need the fields. So this function only handles the remaining
    straightforward case: a preset key, optional overrides, and a
    target-requirement check for typos or --desc-preset none.
    """
    desc2     = parse_u32(args.desc2,     name="desc2")
    desc3     = parse_u32(args.desc3,     name="desc3")
    pci = parse_u32(getattr(args, "pci", None), name="pci")

    preset_key = args.desc_preset
    if preset_key == "auto":
        preset_key = detected_preset   # may be None if target didn't need it

    if preset_key and preset_key != "none" and preset_key in DESC_PRESETS:
        p = DESC_PRESETS[preset_key]
        if desc2 is None: desc2 = p["desc2"]
        if desc3 is None: desc3 = p["desc3"]

    if desc2 is None:     desc2 = 0
    if desc3 is None:     desc3 = 0
    if pci is None: pci = 0

    missing = []
    if target.desc2_required and desc2 == 0: missing.append("--desc2")
    if target.desc3_required and desc3 == 0: missing.append("--desc3")
    if missing:
        known = ", ".join(sorted(DESC_PRESETS))
        raise SystemExit(
            f"{target.code} needs descriptor word(s) {', '.join(missing)}. "
            f"Use --desc-preset (one of {known}) or pass explicit "
            f"--desc2/--desc3.")
    return desc2, desc3, pci



def build_primary_header(*, fmt: bytes, component: str) -> bytes:
    hdr = bytearray(PRIMARY_SIZE)
    hdr[OFF_MAGIC:OFF_MAGIC + 4]   = MAGIC
    hdr[OFF_FORMAT:OFF_FORMAT + 4] = fmt
    comp_bytes = component.encode("ascii")
    if len(comp_bytes) > COMPONENT_LEN:
        raise ValueError(f"component too long: {component!r}")
    hdr[OFF_COMPONENT:OFF_COMPONENT + len(comp_bytes)] = comp_bytes
    return bytes(hdr)


def build_descriptor(target: TargetRegion, payload: bytes,
                     *, primary_header: bytes,
                     desc2: int, desc3: int, pci: int,
                     flags: int = 0) -> bytes:
    if len(primary_header) != PRIMARY_SIZE:
        raise ValueError(f"primary header must be {PRIMARY_SIZE} bytes")
    if not 0 <= flags < 0x100:
        raise SystemExit(
            f"--flags out of range: 0x{flags:X}")
    desc = bytearray(DESCRIPTOR_SIZE)
    put_u32(desc, 0x00, 1)
    desc[0x04:0x08] = target.code.encode("ascii")
    put_u32(desc, 0x08, desc2)
    put_u32(desc, 0x0C, desc3)
    put_u32(desc, 0x10, pci)    # PCI (var 0x232); enforced when PRI (var 0x111) == 1
    put_u32(desc, 0x40, len(payload))
    put_u32(desc, 0x44, crc32_final(payload))
    put_u32(desc, 0x48, flags)
    # Descriptor CRC (0x4c) covers primary header + descriptor[0:0x4c]
    put_u32(desc, 0x4C, crc32_final(primary_header + bytes(desc[:0x4C])))
    return bytes(desc)


def build_0005(target: TargetRegion, payload: bytes,
               *, desc2: int, desc3: int, pci: int = 0,
               flags: int = 0) -> bytes:
    primary = build_primary_header(fmt=FORMAT_0005,
                                   component=DEFAULT_COMPONENT_0005)
    descriptor = build_descriptor(target, payload,
                                  primary_header=primary,
                                  desc2=desc2, desc3=desc3,
                                  pci=pci, flags=flags)
    return primary + descriptor + payload


def target_for_container(info: dict) -> TargetRegion | None:
    """Return the TargetRegion this container targets, or None if it can't
    be inferred. 0005 reads it from the descriptor's `code` field; 0006 is
    implicitly a full-flash (FGCB) payload per the app verifier's marker=5
    path."""
    if info["format"] == FORMAT_0005:
        return TARGETS.get(info.get("code"))
    if info["format"] == FORMAT_0006:
        return TARGETS["FGCB"]
    return None


def rebuild_0005_with_payload(primary: bytes, descriptor: bytes,
                              payload: bytes) -> bytes:
    """Assemble a 0005 container from its three parts, refreshing the
    payload-length, payload-CRC, and descriptor-CRC fields to match the
    (possibly patched) payload."""
    if len(primary) != PRIMARY_SIZE:
        raise ValueError(f"primary must be {PRIMARY_SIZE} B, got {len(primary)}")
    if len(descriptor) != DESCRIPTOR_SIZE:
        raise ValueError(f"descriptor must be {DESCRIPTOR_SIZE} B, "
                         f"got {len(descriptor)}")
    desc = bytearray(descriptor)
    put_u32(desc, 0x40, len(payload))
    put_u32(desc, 0x44, crc32_final(payload))
    put_u32(desc, 0x4C, crc32_final(primary + bytes(desc[:0x4C])))
    return primary + bytes(desc) + payload


def build_0006(payload: bytes, component: str) -> bytes:
    if component not in COMPONENTS_0006:
        raise SystemExit(f"format 0006: component must be one of "
                         f"{list(COMPONENTS_0006)}; got {component!r}")
    primary = build_primary_header(fmt=FORMAT_0006, component=component)
    return primary + payload



def inspect_container(data: bytes) -> dict:
    if len(data) < PRIMARY_SIZE:
        raise ValueError(f"file too short for OTA container: {len(data)} bytes")
    primary   = data[:PRIMARY_SIZE]
    magic     = primary[OFF_MAGIC:OFF_MAGIC + 4]
    fmt       = primary[OFF_FORMAT:OFF_FORMAT + 4]
    comp_raw  = primary[OFF_COMPONENT:OFF_COMPONENT + COMPONENT_LEN]
    component = comp_raw.split(b"\x00", 1)[0].decode("ascii", "replace")

    info = {
        "file_size":  len(data),
        "magic":      magic,
        "magic_ok":   magic == MAGIC,
        "format":     fmt,
        "component":  component,
        "sha256":     hashlib.sha256(data).hexdigest().upper(),
    }

    if fmt == FORMAT_0005:
        if len(data) < PAYLOAD_OFFSET_0005:
            raise ValueError(f"0005 container too short: {len(data)} bytes")
        descriptor = data[PRIMARY_SIZE:PAYLOAD_OFFSET_0005]
        payload    = data[PAYLOAD_OFFSET_0005:]
        exp_payload_len = get_u32(descriptor, 0x40)
        exp_payload_crc = get_u32(descriptor, 0x44)
        exp_desc_crc    = get_u32(descriptor, 0x4C)
        act_payload_crc = crc32_final(payload)
        act_desc_crc    = crc32_final(primary + descriptor[:0x4C])
        info.update({
            "payload_offset":     PAYLOAD_OFFSET_0005,
            "payload_size":       len(payload),
            "code":               descriptor[0x04:0x08].decode("ascii", "replace"),
            "marker":             get_u32(descriptor, 0x00),
            "desc2":              get_u32(descriptor, 0x08),
            "desc3":              get_u32(descriptor, 0x0C),
            "pci":                get_u32(descriptor, 0x10),
            "flags":              get_u32(descriptor, 0x48),
            "payload_len_ok":     len(payload) == exp_payload_len,
            "expected_payload_len": exp_payload_len,
            "payload_crc":        act_payload_crc,
            "expected_payload_crc": exp_payload_crc,
            "payload_crc_ok":     act_payload_crc == exp_payload_crc,
            "descriptor_crc":     act_desc_crc,
            "expected_desc_crc":  exp_desc_crc,
            "descriptor_crc_ok":  act_desc_crc == exp_desc_crc,
        })
    elif fmt == FORMAT_0006:
        info.update({
            "payload_offset":     PAYLOAD_OFFSET_0006,
            "payload_size":       len(data) - PAYLOAD_OFFSET_0006,
        })

    # HW-region CRC check inside the payload (applies to both formats).
    target = target_for_container(info)
    if target is not None and "payload_offset" in info:
        payload = data[info["payload_offset"]:]
        info["hw_crc_results"] = verify_payload_crcs(payload, target)
    else:
        info["hw_crc_results"] = []
    return info


def print_info(info: dict, path: str | None = None) -> None:
    if path:
        print(f"File:          {path}")
    print(f"Total size:    {info['file_size']} bytes")
    print(f"Magic:         {info['magic']!r}  "
          f"({'ok' if info['magic_ok'] else 'INVALID - expected OTA!'})")
    print(f"Format:        {info['format']!r}")
    print(f"Component:     {info['component']!r}")
    print(f"Payload size:  {info.get('payload_size', '?')}")
    if info["format"] == FORMAT_0005:
        print(f"Code:          {info['code']}  marker={info['marker']}")
        print(f"Descriptor:    desc2=0x{info['desc2']:08X}  "
              f"desc3=0x{info['desc3']:08X}  "
              f"pci=0x{info['pci']:08X}  "
              f"flags=0x{info['flags']:08X}")
        print(f"Payload CRC:   0x{info['payload_crc']:08X}  "
              f"({'ok' if info['payload_crc_ok'] else 'MISMATCH, desc says 0x'+format(info['expected_payload_crc'],'08X')})")
        print(f"Desc CRC:      0x{info['descriptor_crc']:08X}  "
              f"({'ok' if info['descriptor_crc_ok'] else 'MISMATCH, desc says 0x'+format(info['expected_desc_crc'],'08X')})")
        print(f"Desc CRC span: primary[0:0x58] + descriptor[0:0x4c]")

    hw = info.get("hw_crc_results") or []
    if hw:
        print(f"HW region CRC16-CCITT ({len(hw)} region(s) in payload):")
        for (name, stored, computed, ok) in hw:
            tag = "ok" if ok else "MISMATCH"
            print(f"  {name}: stored=0x{stored:04X} computed=0x{computed:04X} {tag}")
    print(f"SHA256(file):  {info['sha256']}")



async def _send_block(conn: As11Connection, params: dict) -> None:
    """Send one UpgradeDataBlock."""
    resp = await conn.send_rpc("UpgradeDataBlock", params,
                               encrypted=True,
                               timeout=BLOCK_RPC_TIMEOUT,
                               post_send_delay=0.0)
    if resp.get("result") is True:
        return
    raise RuntimeError(
        f"UpgradeDataBlock @0x{params['fileOffset']:08x} rejected by "
        f"device (result={resp.get('result')!r}). Restart the upload "
        f"with a fresh InitiateUpgrade.")


# Apply-mode resolution
# Three dispositions for the apply step:
#   "none"          - stop after CheckUpgradeFile
#   "plain"         - ApplyUpgrade (unauthenticated, admin VCID 0x396 only)
#   "authenticated" - ApplyAuthenticatedUpgrade (HMAC with K_ota)

ApplyMode = str   # Literal["none", "plain", "authenticated"] would need
                  # `from typing import Literal`; keep str for minimal churn.
APPLY_NONE          = "none"
APPLY_PLAIN         = "plain"
APPLY_AUTHENTICATED = "authenticated"


def resolve_apply_mode(args) -> ApplyMode:
    """
      (no flag)       -> NONE           verify-only
      --apply         -> AUTHENTICATED  ApplyAuthenticatedUpgrade  (+HMAC)
      --apply-plain   -> PLAIN          ApplyUpgrade               (admin VCID)
    """
    want_auth  = bool(getattr(args, "apply", False))
    want_plain = bool(getattr(args, "apply_plain", False))
    if want_auth and want_plain:
        raise SystemExit("pass only one of --apply / --apply-plain")
    if want_plain: return APPLY_PLAIN
    if want_auth:  return APPLY_AUTHENTICATED
    return APPLY_NONE



from contextlib import asynccontextmanager


@asynccontextmanager
async def open_session(args):
    """Resolve address + creds, connect, reconnect, yield the live
    As11Connection. Cleans up on exit regardless of failure mode."""
    As11Connection, load_credentials, resolve_addr = _import_ble()
    addr = resolve_addr(args.addr)
    creds = load_credentials(addr)
    if not creds.get("clientId") or not creds.get("masterPairKey"):
        raise SystemExit(f"no saved credentials for {addr}; run "
                         f"`as11_ble.py --addr {addr} devices pair` first.")

    conn = As11Connection(debug=args.debug)
    try:
        await conn.connect(addr)
        await conn.reconnect(creds["clientId"], creds["masterPairKey"])
        yield conn
    finally:
        try:
            await conn.disconnect()
        except Exception:
            pass


# Upload phases

async def phase_initiate(conn: As11Connection, total: int) -> int:
    """InitiateUpgrade -> validated raw-bytes-per-block."""
    print(f"[1/3] InitiateUpgrade size={total}")
    resp = await conn.send_rpc("InitiateUpgrade",
                               {"upgradeFileSize": total},
                               encrypted=True, timeout=BLOCK_RPC_TIMEOUT)
    raw_block = int(resp.get("result", {}).get("xferBlockSize", XFER_RAW_BYTES))
    if raw_block <= 0 or raw_block > XFER_RAW_BYTES:
        raise RuntimeError(f"device returned suspicious xferBlockSize={raw_block}")
    if raw_block != XFER_RAW_BYTES:
        print(f"  device advertised xferBlockSize={raw_block}")
    return raw_block


async def phase_stream(conn: As11Connection, abc: bytes,
                       raw_block: int, *,
                       block_delay_s: float) -> None:
    """UpgradeDataBlock loop with progress bar. Silences the `as11_ble`
    logger for the duration so per-RPC INFO lines don't stomp the bar."""
    total = len(abc)
    n_blocks = (total + raw_block - 1) // raw_block
    print(f"[2/3] UpgradeDataBlock x{n_blocks} "
          f"({raw_block} raw B/block, {raw_block * 2} hex chars/block)")

    ble_log = logging.getLogger("as11_ble")
    prev_level = ble_log.level
    if prev_level < logging.WARNING:
        ble_log.setLevel(logging.WARNING)

    t0 = time.monotonic()
    last_print = t0
    try:
        for i in range(n_blocks):
            off = i * raw_block
            chunk = abc[off:off + raw_block]
            await _send_block(
                conn,
                {"fileOffset": off, "encoding": "AsciiHex",
                 "data": chunk.hex().upper()})
            if block_delay_s > 0:
                await asyncio.sleep(block_delay_s)

            now = time.monotonic()
            if now - last_print >= 1.0 or i == n_blocks - 1:
                done = min(off + raw_block, total)
                elapsed = max(now - t0, 0.001)
                rate = done / elapsed
                eta = (total - done) / rate if rate > 0 else 0
                print(f"  block {i+1}/{n_blocks}  {done}/{total} B  "
                      f"{100.0 * done / total:5.1f}%  "
                      f"{rate/1024:.1f} KiB/s  ETA {eta:4.0f}s",
                      end="\r", flush=True)
                last_print = now
    finally:
        ble_log.setLevel(prev_level)
    print()   # newline after progress line


async def phase_check(conn: As11Connection, file_hash: str,
                      *, verify_timeout: float) -> None:
    """CheckUpgradeFile. Device drains NOR staging before replying - can
    take tens of seconds. Propagates device errors as RuntimeError."""
    print(f"[3/3] CheckUpgradeFile hash={file_hash[:16]}...  "
          f"(timeout {verify_timeout:.0f}s)")
    resp = await conn.send_rpc("CheckUpgradeFile",
                               {"upgradeFileHash": file_hash},
                               encrypted=True, timeout=verify_timeout)
    print(f"  result: {resp.get('result')!r}")


async def phase_apply(conn: As11Connection, *,
                      mode: ApplyMode,
                      file_hash: str, file_hash_bytes: bytes,
                      key: bytes,
                      reset_settings: bool,
                      apply_vcid: int | None,
                      verify_timeout: float) -> None:
    """ApplyUpgrade or ApplyAuthenticatedUpgrade"""

    if mode == APPLY_PLAIN:
        # Firmware defaults resetSettingsToDefault to true when omitted;
        # send it explicitly either way so behaviour is deterministic.
        params = {
            "upgradeFileHash": file_hash,
            "resetSettingsToDefault": bool(reset_settings),
        }
        print(f"[apply] ApplyUpgrade  (timeout {verify_timeout:.0f}s)")
        resp = await conn.send_rpc("ApplyUpgrade", params,
                                   encrypted=True,
                                   vcid_override=apply_vcid,
                                   timeout=verify_timeout)
        print(f"  result: {resp.get('result')!r}")
        return

    if mode == APPLY_AUTHENTICATED:
        tag = hmac.new(key, file_hash_bytes, hashlib.sha256).hexdigest().upper()
        print(f"[apply] ApplyAuthenticatedUpgrade tag={tag[:16]}...  "
              f"(timeout {verify_timeout:.0f}s)")
        resp = await conn.send_rpc("ApplyAuthenticatedUpgrade",
                                   {"upgradeFileHash": file_hash,
                                    "authentication":  tag},
                                   encrypted=True, timeout=verify_timeout)
        print(f"  result: {resp.get('result')!r}")
        print("Device should reboot and hand off to the bootloader/apply stage.")
        return

    raise ValueError(f"phase_apply called with mode={mode!r}; caller bug")


async def run_upload(conn: As11Connection, abc: bytes, *,
                     apply_mode: ApplyMode,
                     apply_vcid: int | None,
                     reset_settings: bool,
                     key: bytes,
                     block_delay_s: float,
                     verify_timeout: float) -> int:

    total = len(abc)
    file_hash_bytes = hashlib.sha256(abc).digest()
    file_hash = file_hash_bytes.hex().upper()

    raw_block = await phase_initiate(conn, total)
    await phase_stream(conn, abc, raw_block,
                       block_delay_s=block_delay_s)
    await phase_check(conn, file_hash, verify_timeout=verify_timeout)

    if apply_mode == APPLY_NONE:
        print()
        print("CheckUpgradeFile succeeded. Not committing (no --apply /")
        print("--apply-plain). Pass --apply once you're ready to reboot.")
        return 0

    await phase_apply(conn,
                      mode=apply_mode,
                      file_hash=file_hash,
                      file_hash_bytes=file_hash_bytes,
                      key=key, reset_settings=reset_settings,
                      apply_vcid=apply_vcid,
                      verify_timeout=verify_timeout)
    return 0



def check_danger_ack(args, target: TargetRegion) -> None:
    if not target.danger_flag:
        return
    if getattr(args, target.danger_flag, False):
        return
    flag = "--" + target.danger_flag.replace("_", "-")
    raise SystemExit(
        f"{target.code} targets {target.notes} "
        f"({target.flash_start:#010x}..{target.flash_end:#010x}); "
        f"pass {flag} to continue.")



def check_and_maybe_fix_hw_crcs(payload: bytes, target: TargetRegion,
                                *, fix: bool, force: bool,
                                label: str = "input image") -> bytes:
    """Verify CRC16-CCITT footers on HW regions inside `payload`
    Returns the payload (possibly patched if `fix=True`)
    Raises SystemExit on mismatch when neither fix nor force is set
    """
    crc_results = verify_payload_crcs(payload, target)
    if not crc_results:
        log.info("no HW CRC region fits inside this payload; skipping check")
        return payload

    print(f"CRC16-CCITT check ({len(crc_results)} region(s) in payload):")
    for (name, stored, computed, ok) in crc_results:
        tag = "ok" if ok else "MISMATCH"
        print(f"  {name}: stored=0x{stored:04X} computed=0x{computed:04X} {tag}")

    if all(ok for (_, _, _, ok) in crc_results):
        return payload

    if fix:
        payload, fixed = fix_payload_crcs(payload, target)
        for (name, new_crc) in fixed:
            print(f"  fixed {name} CRC -> 0x{new_crc:04X}")
        return payload
    if force:
        return payload
    raise SystemExit(
        f"CRC mismatch in {label}. Use --fix-crc to patch CRCs "
        f"in memory, or --force to proceed with the bad CRCs as-is.")


def _build_container(args, *,
                     detected_preset: str | None = None
                     ) -> tuple[bytes, TargetRegion, bytes]:
    """Assemble the .abc container"""

    target = resolve_block(args.block)
    check_danger_ack(args, target)
    payload = load_payload(args, target)
    payload = check_and_maybe_fix_hw_crcs(
        payload, target,
        fix=getattr(args, "fix_crc", False),
        force=getattr(args, "force", False))

    fmt = args.format.encode("ascii")
    if fmt == FORMAT_0006:
        # 0006 is implicitly a full-image shortcut; only FGCB makes semantic sense
        if target.code != "FGCB":
            raise SystemExit(
                f"format 0006 is a full-image shortcut; --block must resolve "
                f"to FGCB (e.g. --block full). Got --block {args.block} "
                f"({target.code}).")
        component = getattr(args, "component_0006", "PacificFG")
        abc = build_0006(payload, component)
        return abc, target, FORMAT_0006

    # 0005
    desc2, desc3, pci = resolve_descriptor_words(args, target,
                                                 detected_preset=detected_preset)
    flags = parse_u32(args.flags, name="flags") or 0
    abc = build_0005(target, payload,
                     desc2=desc2, desc3=desc3,
                     pci=pci, flags=flags)
    return abc, target, FORMAT_0005


def cmd_targets(_args) -> int:
    print(f"{'Code':5s} {'Range':26s} {'Size':>12s}  Notes")
    for t in TARGETS.values():
        flag = ""
        if t.danger_flag == "include_bootloader":
            flag = "  (needs --include-bootloader)"
        elif t.danger_flag == "include_full_flash":
            flag = "  (needs --include-full-flash)"
        print(f"{t.code:5s} {t.flash_start:#010x}..{t.flash_end:#010x}  "
              f"{t.size:>10d} B  {t.notes}{flag}")
    print()
    print("Block aliases: config->CONF, firmware/app->APPL, conf+app->APCX,")
    print("               bootloader->FGBL, full/all->FGCB")
    return 0


def cmd_build(args) -> int:
    # auto-detect is a runtime (device-query) concept and doesn't apply to
    # offline builds. Error early if the target actually needs a preset.
    tgt = resolve_block(args.block)
    if args.desc_preset == "auto" and _auto_preset_needed(args, tgt):
        known = "/".join(sorted(DESC_PRESETS))
        raise SystemExit(
            f"{tgt.code} needs descriptor preset, and `build` can't query a "
            f"device. Pass --desc-preset {known} (or --desc2/--desc3), or use "
            f"the `flash` subcommand which can auto-detect.")
    abc, target, fmt = _build_container(args)
    out = Path(args.output)
    out.write_bytes(abc)
    print(f"Wrote {out} ({len(abc)} bytes, format {fmt.decode('ascii')}, "
          f"target {target.code})")
    print_info(inspect_container(abc))
    return 0


def cmd_info(args) -> int:
    data = Path(args.file).read_bytes()
    print_info(inspect_container(data), path=args.file)
    return 0


async def detect_preset_for_descriptor(conn: As11Connection) -> str:
    """Query the device's ApplicationIdentifier and map it to a preset
    key in DESC_PRESETS. Raises SystemExit with a clean message on any
    failure path so the caller doesn't have to duplicate error handling."""
    print("[auto] querying device firmware version...")
    detected = await fetch_firmware_version(conn)
    if detected is None:
        raise SystemExit(
            "auto-detect failed: device didn't return ApplicationIdentifier. "
            "Pass --desc-preset or --desc2/--desc3 explicitly.")
    if detected not in DESC_PRESETS:
        known = ", ".join(sorted(DESC_PRESETS))
        raise SystemExit(
            f"device reports firmware {detected!r} which isn't in "
            f"DESC_PRESETS ({known}). Pass --desc-preset explicitly, or "
            f"extract the new version's desc2/desc3 constants "
            f"(see docs/s11_ota.md).")
    print(f"[auto] device reports {detected}; using matching preset")
    return detected


def _upload_kwargs_from_args(args) -> dict:
    """Build the keyword args to run_upload() from parsed CLI args. Extracted
    so cmd_upload and cmd_flash don't duplicate validation + parsing.
    """
    apply_mode = resolve_apply_mode(args)
    if apply_mode == APPLY_AUTHENTICATED:
        key = parse_key(getattr(args, "key", None),
                        getattr(args, "key_file", None))
    else:
        key = b""   # unused downstream; phase_apply guards on mode
    return dict(
        apply_mode=apply_mode,
        apply_vcid=parse_u32(getattr(args, "apply_vcid", None),
                             name="apply-vcid"),
        reset_settings=bool(getattr(args, "reset_settings", False)),
        key=key,
        block_delay_s=args.block_delay,
        verify_timeout=args.verify_timeout,
    )


def cmd_upload(args) -> int:
    resolve_apply_mode(args)

    abc = Path(args.file).read_bytes()
    info = inspect_container(abc)
    path = args.file

    if not info["magic_ok"]:
        raise SystemExit(f"{path}: bad magic {info['magic']!r}, "
                         f"expected {MAGIC!r}")
    if info["format"] not in (FORMAT_0005, FORMAT_0006):
        raise SystemExit(f"{path}: unknown format {info['format']!r}; "
                         f"expected {FORMAT_0005!r} or {FORMAT_0006!r}")

    def _soft(msg: str) -> None:
        if args.force:
            log.warning("ignoring: %s (--force)", msg)
        else:
            raise SystemExit(
                f"{path}: {msg} (pass --force to upload anyway)")

    known_components = {DEFAULT_COMPONENT_0005, *COMPONENTS_0006, "PacificBT"}
    if info["component"] not in known_components:
        _soft(f"unknown component string {info['component']!r}; "
              f"known: {sorted(known_components)}")

    if info["format"] == FORMAT_0005:
        if info.get("code") not in TARGETS:
            _soft(f"0005 descriptor code {info.get('code')!r} not in "
                  f"TARGETS ({sorted(TARGETS)})")
        if info.get("marker") != 1:
            _soft(f"0005 descriptor marker={info.get('marker')} "
                  f"(verifier requires 1)")
        if info.get("flags", 0) >= 0x100:
            _soft(f"0005 descriptor flags=0x{info.get('flags', 0):X} "
                  f"(verifier requires < 0x100)")
        if not info.get("payload_len_ok", True):
            _soft("descriptor payload length field doesn't match "
                  "actual payload size")

        if not info.get("payload_crc_ok", True) and not args.fix_crc:
            _soft("descriptor payload CRC mismatch "
                  "(pass --fix-crc to recompute)")
        if not info.get("descriptor_crc_ok", True) and not args.fix_crc:
            _soft("descriptor CRC mismatch (pass --fix-crc to recompute)")

    # HW-region CRC check inside the payload. May return a patched
    # payload when --fix-crc repaired a broken footer.
    target = target_for_container(info)
    payload = abc[info["payload_offset"]:] if target is not None else None
    if target is not None:
        payload = check_and_maybe_fix_hw_crcs(
            payload, target,
            fix=args.fix_crc, force=args.force,
            label=f"{args.file} payload")

    if args.fix_crc and target is not None:
        if info["format"] == FORMAT_0005:
            primary = abc[:PRIMARY_SIZE]
            desc    = abc[PRIMARY_SIZE:PAYLOAD_OFFSET_0005]
            abc = rebuild_0005_with_payload(primary, desc, payload)
            print("  rebuilt 0005 descriptor (payload-len / payload-CRC / "
                  "descriptor-CRC fields refreshed)")
        elif info["format"] == FORMAT_0006:
            abc = abc[:PRIMARY_SIZE] + payload

    if args.dry_run:
        print("dry-run: validated container, not contacting device")
        print_info(inspect_container(abc), path=args.file)
        return 0

    upload_kwargs = _upload_kwargs_from_args(args)

    async def run() -> int:
        async with open_session(args) as conn:
            return await run_upload(conn, abc, **upload_kwargs)
    return asyncio.run(run())


def cmd_flash(args) -> int:
    # Fail fast on things we can check without hitting the device.
    resolve_apply_mode(args)
    target = resolve_block(args.block)
    check_danger_ack(args, target)

    need_detect = (args.desc_preset == "auto"
                   and _auto_preset_needed(args, target))

    if args.dry_run:
        # dry-run can't query the device, so auto-detect isn't possible.
        if need_detect:
            known = "/".join(sorted(DESC_PRESETS))
            raise SystemExit(
                f"--dry-run can't query the device. For auto-detect, remove "
                f"--dry-run, or pass --desc-preset {known} (or "
                f"--desc2/--desc3) explicitly.")
        abc, _, fmt = _build_container(args)
        print(f"Built {fmt.decode('ascii')} container for {target.code}  "
              f"({target.flash_start:#010x}..{target.flash_end:#010x}, "
              f"{len(abc)} bytes)")
        if args.save_abc:
            Path(args.save_abc).write_bytes(abc)
            print(f"Saved built container to {args.save_abc}")
        print("dry-run: not contacting device")
        print_info(inspect_container(abc))
        return 0

    # Live flash path: connect, maybe detect version, build, upload.
    upload_kwargs = _upload_kwargs_from_args(args)

    # If user didn't supply --pci and we're building a 0005 container,
    # we'll try to fetch it from the device after connecting. Irrelevant
    # for 0006 (no secondary descriptor at all).
    pci_fetch_needed = (args.format == "0005" and args.pci is None)

    async def run() -> int:
        async with open_session(args) as conn:
            detected_preset = None
            if need_detect:
                detected_preset = await detect_preset_for_descriptor(conn)

            if pci_fetch_needed:
                print("[auto] querying device _PCI (and _PRI for context)...")
                pci_val = await fetch_pci(conn)
                if pci_val is None:
                    log.warning("could not read _PCI from device; falling "
                                "back to 0. If CheckUpgradeFile rejects "
                                "with -11309 it's likely this device has "
                                "_PRI=1 and enforces the check. Query "
                                "manually (`as11_ble.py --addr <dev> get "
                                "_PCI _PRI`) and pass --pci.")
                else:
                    print(f"[auto] using _PCI=0x{pci_val:08X} in descriptor")
                    args.pci = f"0x{pci_val:08X}"

            abc, _, fmt = _build_container(args, detected_preset=detected_preset)
            print(f"Built {fmt.decode('ascii')} container for {target.code}  "
                  f"({target.flash_start:#010x}..{target.flash_end:#010x}, "
                  f"{len(abc)} bytes)")
            if args.save_abc:
                Path(args.save_abc).write_bytes(abc)
                print(f"Saved built container to {args.save_abc}")

            return await run_upload(conn, abc, **upload_kwargs)
    return asyncio.run(run())



def _add_input_args(p: argparse.ArgumentParser) -> None:
    """-f/--file + optional --from-full / --payload force-overrides."""
    p.add_argument("-f", "--file", metavar="PATH",
                   help="firmware input (full 2 MiB flash dump or pre-sliced "
                        "block payload; auto-detected by size)")
    p.add_argument("--from-full", metavar="PATH",
                   help="force: treat this file as a full 2 MiB flash dump "
                        "and slice the selected block out of it")
    p.add_argument("--payload", metavar="PATH",
                   help="force: treat this file as the already-sliced payload "
                        "for the selected block")


def _add_build_args(p: argparse.ArgumentParser) -> None:
    """All build-side options: block, format, descriptor."""
    p.add_argument("--block", required=True, metavar="NAME",
                   help="target block (aliases: config, firmware/app, "
                        "conf+app, bootloader, full/all; or raw codes "
                        "CONF, APPL, APCX, FGBL, FGCB)")
    p.add_argument("--format", default="0005", choices=("0005", "0006"),
                   help="container format (default: 0005). 0006 is only "
                        "valid for --block full and is the PacificFG/AlarmModule "
                        "full-image shortcut.")
    p.add_argument("--component-0006", default="PacificFG",
                   choices=list(COMPONENTS_0006),
                   help="(format 0006 only) primary header component string "
                        "(default: PacificFG)")
    # 0005 descriptor knobs
    p.add_argument("--desc-preset", default="auto",
                   choices=["auto"] + sorted(DESC_PRESETS) + ["none"],
                   help="fill 0005 descriptor words from a known firmware "
                        "preset (default: auto). With `auto`, `flash` queries "
                        "the device's ApplicationIdentifier and matches it to "
                        "DESC_PRESETS; `build` requires an explicit version.")
    p.add_argument("--desc2", metavar="U32",
                   help="0005 descriptor word at offset 0x08 (hex or decimal); "
                        "overrides preset")
    p.add_argument("--desc3", metavar="U32",
                   help="0005 descriptor word at offset 0x0c; overrides preset")
    p.add_argument("--pci", default=None, metavar="U32",
                   help="0005 descriptor word at offset 0x10: the device's "
                        "PCI code (firmware var 0x0232). The app verifier "
                        "checks it only when PRI (var 0x0111) == 1 - a "
                        "runtime gate. To fetch from a live device: "
                        "`as11_ble.py --addr <dev> get _PCI _PRI`. "
                        "`flash` auto-fetches _PCI (and logs _PRI for "
                        "context) when this is omitted; `build` defaults "
                        "to 0 since it can't query a device.")
    p.add_argument("--flags", default="0", metavar="U8",
                   help="0005 descriptor word at offset 0x48; verifier "
                        "requires it to be < 0x100")
    # safety
    p.add_argument("--include-bootloader", action="store_true",
                   help="permit building/uploading FGBL (bootloader region)")
    p.add_argument("--include-full-flash", action="store_true",
                   help="permit building/uploading FGCB (complete 2 MiB flash)")
    # CRC handling (resmed_flash-style)
    p.add_argument("--fix-crc", action="store_true",
                   help="recompute and patch CRC16-CCITT footers in memory "
                        "before building (for hand-edited payloads where "
                        "the patcher didn't fix up footers)")


def _add_upload_args(p: argparse.ArgumentParser) -> None:
    """All BLE upload + apply options."""
    p.add_argument("--apply", action="store_true",
                   help="after CheckUpgradeFile succeeds, call "
                        "ApplyAuthenticatedUpgrade (requires --key)")
    p.add_argument("--apply-plain", action="store_true",
                   help="after CheckUpgradeFile succeeds, call "
                        "unauthenticated ApplyUpgrade (only reachable on "
                        "admin VCID 0x0396).")
    p.add_argument("--apply-vcid", metavar="VCID",
                   help="override VCID for the apply RPC (e.g. 0x0396)")
    p.add_argument("--reset-settings", action="store_true",
                   help="send resetSettingsToDefault=true with --apply-plain "
                        "(default sends false to preserve settings)")
    p.add_argument("--key", metavar="HEX32",
                   help="K_ota as 64 hex chars")
    p.add_argument("--key-file", metavar="PATH",
                   help="K_ota as a 32-byte binary file or a hex-text file")
    p.add_argument("--block-delay", type=float, default=0.0, metavar="SECONDS",
                   help="optional delay after each UpgradeDataBlock "
                        "(default: 0)")
    p.add_argument("--verify-timeout", type=float, default=LONG_RPC_TIMEOUT,
                   metavar="SECONDS",
                   help=(f"timeout for CheckUpgradeFile and Apply* "
                         f"(default: {int(LONG_RPC_TIMEOUT)}). "
                         f"The device drains NOR staging before replying."))
    p.add_argument("--dry-run", action="store_true",
                   help="validate the container and print the plan; "
                        "do not contact the device")
    p.add_argument("--force", action="store_true",
                   help=_FORCE_HELP)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    ap = argparse.ArgumentParser(
        prog="as11_ota",
        description="AirSense 11 OTA firmware uploader "
                    "(builds .abc, streams over BLE).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--addr", default=None,
                    help="device MAC / UUID / alias (defaults to $AS11_ADDR)")
    ap.add_argument("--debug", action="store_true",
                    help="verbose BLE packet logging")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # targets
    p_t = sub.add_parser("targets", help="list block targets")
    p_t.set_defaults(func=cmd_targets)

    # build
    p_b = sub.add_parser("build", help="build an .abc container locally")
    _add_input_args(p_b)
    _add_build_args(p_b)
    p_b.add_argument("-o", "--output", required=True,
                     help="output .abc path")
    p_b.add_argument("--force", action="store_true",
                     help=_FORCE_HELP)
    p_b.set_defaults(func=cmd_build)

    # info
    p_i = sub.add_parser("info", help="inspect an .abc container")
    p_i.add_argument("file", help=".abc file to inspect")
    p_i.set_defaults(func=cmd_info)

    # upload
    p_u = sub.add_parser("upload",
                         help="push a pre-built .abc over BLE; "
                              "CheckUpgradeFile only unless --apply "
                              "or --apply-plain is given")
    p_u.add_argument("file", help=".abc file to upload")
    p_u.add_argument("--fix-crc", action="store_true",
                     help="recompute and patch CRC16-CCITT HW-region footers "
                          "in the payload and refresh the 0005 descriptor "
                          "CRC fields before sending")
    _add_upload_args(p_u)
    p_u.set_defaults(func=cmd_upload)

    # flash (build + upload)
    p_f = sub.add_parser("flash",
                         help="build .abc from firmware and upload in one step; "
                              "CheckUpgradeFile only unless --apply "
                              "or --apply-plain is given")
    _add_input_args(p_f)
    _add_build_args(p_f)
    p_f.add_argument("--save-abc", metavar="PATH",
                     help="also write the built .abc to this path")
    _add_upload_args(p_f)
    p_f.set_defaults(func=cmd_flash)

    args = ap.parse_args(argv)

    # shared arg validation
    if getattr(args, "block_delay", 0.0) < 0:
        raise SystemExit("--block-delay must be non-negative")
    if getattr(args, "reset_settings", False) and not getattr(args, "apply_plain", False):
        raise SystemExit("--reset-settings only applies with --apply-plain")
    # apply-mode mutual exclusion is enforced inside resolve_apply_mode() now.

    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted.", file=sys.stderr)
        sys.exit(130)
    except SystemExit:
        raise
    except argparse.ArgumentTypeError as e:
        print(f"\nerror: {e}", file=sys.stderr)
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntimeout: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        if str(e).startswith("RPC error "):
            print(f"\n{e}", file=sys.stderr)
            sys.exit(1)
        raise
    except Exception as e:
        log.exception("fatal: %s", e)
        sys.exit(1)

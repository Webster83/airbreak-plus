#!/usr/bin/env python3
"""
s9_patch_lcd_ili9225.py - Patch SX474-12xx firmware for ILI9225 LCD (09xx boards).

Usage:
    python3 s9_patch_lcd_ili9225.py firmware.bin s9_lcd_ili9225.bin output_prefix

Produces: <prefix>_ili9225.bin and <prefix>_hx8347.bin
Both need CRC fixup via patch-airsense-s9.
"""

import sys
import struct

FLASH_BASE = 0x08000000

ORIG_LCD_INIT   = 0x08080EC8
ORIG_SET_WINDOW = 0x08045290
ORIG_SET_CURSOR = 0x0804526A

NEW_LCD_INIT    = 0x080D8001
NEW_SET_WINDOW  = 0x080D8211
NEW_SET_CURSOR  = 0x080D8275

INJECT_OFFSET   = 0x080D8000 - FLASH_BASE


def encode_thumb2_bw(source, target):
    target_addr = target & ~1
    offset = target_addr - (source + 4)
    if not (-16777216 <= offset <= 16777214):
        raise ValueError(f"B.W offset out of range: 0x{source:08X} to 0x{target:08X}")
    S = 1 if offset < 0 else 0
    if offset < 0:
        offset += (1 << 25)
    imm11 = (offset >> 1) & 0x7FF
    imm10 = (offset >> 12) & 0x3FF
    I1 = (offset >> 23) & 1
    I2 = (offset >> 22) & 1
    J1 = (~(I1 ^ S)) & 1
    J2 = (~(I2 ^ S)) & 1
    hw1 = 0xF000 | (S << 10) | imm10
    hw2 = 0x9000 | (J1 << 13) | (J2 << 11) | imm11
    return struct.pack('<HH', hw1, hw2)


def main():
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <firmware.bin> <s9_lcd_ili9225.bin> <output_prefix>")
        print(f"  Produces: <prefix>_ili9225.bin  (for 09xx boards)")
        print(f"            <prefix>_hx8347.bin   (for 12xx boards)")
        sys.exit(1)

    fw_path, patch_path, out_prefix = sys.argv[1:4]

    with open(fw_path, 'rb') as f:
        fw_data = f.read()
    with open(patch_path, 'rb') as f:
        patch_bin = f.read()

    print(f"Firmware: {fw_path} ({len(fw_data)} bytes)")
    print(f"Patch:    {patch_path} ({len(patch_bin)} bytes)")

    if any(b != 0xFF for b in fw_data[INJECT_OFFSET:INJECT_OFFSET + len(patch_bin)]):
        print("ERROR: Injection area not empty!")
        sys.exit(1)

    for addr, hw, name in [(ORIG_LCD_INIT, 0xB580, "lcd_init"),
                            (ORIG_SET_WINDOW, 0xB5F8, "set_window"),
                            (ORIG_SET_CURSOR, 0xB538, "set_cursor")]:
        actual = struct.unpack_from('<H', fw_data, addr - FLASH_BASE)[0]
        if actual != hw:
            print(f"ERROR: {name} at 0x{addr:08X}: expected 0x{hw:04X}, got 0x{actual:04X}")
            sys.exit(1)

    ili = bytearray(fw_data)
    ili[INJECT_OFFSET:INJECT_OFFSET + len(patch_bin)] = patch_bin
    for orig, new, name in [(ORIG_LCD_INIT, NEW_LCD_INIT, "lcd_init"),
                             (ORIG_SET_WINDOW, NEW_SET_WINDOW, "set_window"),
                             (ORIG_SET_CURSOR, NEW_SET_CURSOR, "set_cursor")]:
        bw = encode_thumb2_bw(orig, new)
        off = orig - FLASH_BASE
        ili[off:off+4] = bw
        print(f"  ILI9225: {name:12s} -> 0x{new:08X}")

    ili_path = f"{out_prefix}_ili9225.bin"
    with open(ili_path, 'wb') as f:
        f.write(ili)
    print(f"  -> {ili_path}")

    hx_path = f"{out_prefix}_hx8347.bin"
    with open(hx_path, 'wb') as f:
        f.write(fw_data)
    print(f"  -> {hx_path} (stock LCD)")

    print(f"\nRun patch-airsense-s9 on BOTH for CRC + tamper bypass.")


if __name__ == '__main__':
    main()

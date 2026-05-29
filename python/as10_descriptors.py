#!/usr/bin/env python3

import struct
import sys
import os
import argparse
import contextlib
import io
import shlex
try:
    import readline  # arrow-key history
except ImportError:
    pass
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

FLASH_BASE   = 0x08000000
RAM_BASE     = 0x20000000

LANG_MASTER = {
    0:  ("EN",  "English"),
    1:  ("FR",  "French"),
    2:  ("DE",  "German"),
    3:  ("IT",  "Italian"),
    4:  ("ES",  "Spanish"),
    5:  ("ES*", "Spanish (regional)"),
    6:  ("PT",  "Portuguese"),
    7:  ("PT*", "Portuguese (regional)"),
    8:  ("NL",  "Dutch"),
    9:  ("SV",  "Swedish"),
    10: ("DA",  "Danish"),
    11: ("NO",  "Norwegian"),
    12: ("FI",  "Finnish"),
    13: ("JA",  "Japanese (Katakana)"),
    14: ("RU",  "Russian"),
    15: ("TR",  "Turkish"),
    16: ("ZH",  "Chinese (Traditional)"),
    17: ("ZS",  "Chinese (Simplified)"),
    18: ("PL",  "Polish"),
    19: ("JK",  "Japanese (Kanji)"),
}

def detect_languages(flash, ta, lan_idx=5):
    """Detect language list from the LAN enum descriptor.

    The perm_mask has one bit per LAN value. Set bits indicate available
    languages. Locale slot = popcount of lower bits.
    Returns (count, labels_list, lan_ids_list).
    """
    g8 = ta.get('table8')
    if not g8:
        raise ValueError("globals[8] not loaded; cannot detect language list")
    lan_addr = g8 + lan_idx * TABLES[8]['stride']
    lan_options = flash.u8(lan_addr + 0x09) or 0
    perm = flash.u32(lan_addr + 0x0C)
    if perm is None or perm == 0:
        raise ValueError("LAN descriptor has no language permission mask")
    ids = []
    labels = []
    for bit in range(max(perm.bit_length(), lan_options)):
        if perm & (1 << bit):
            ids.append(bit)
            lbl = LANG_MASTER.get(bit, (f"L{bit}", f"Language {bit}"))[0]
            labels.append(lbl)
    if not ids:
        raise ValueError("LAN descriptor language mask is empty")
    return len(ids), labels, ids


def infer_language_count_from_g2(flash, g2_addr):
    ptrs = []
    for i in range(128):
        ptr = flash.u32(g2_addr + i * 8 + 4)
        if not ptr or not flash.is_flash_ptr(ptr):
            break
        ptrs.append(ptr)
    if len(ptrs) < 2:
        raise ValueError("globals[2] has too few locale arrays")

    deltas = [b - a for a, b in zip(ptrs, ptrs[1:])
              if b > a and (b - a) % 2 == 0 and (b - a) <= 128]
    if not deltas:
        raise ValueError("cannot infer language slot count from globals[2]")
    stride = max(set(deltas), key=deltas.count)
    slots = stride // 2

    # Locale arrays are u16 slots aligned to 4 bytes; odd language counts leave
    # a trailing zero pad word before the next array.
    sample = ptrs[:min(len(ptrs), 128)]
    while slots > 1:
        col = [flash.u16(ptr + (slots - 1) * 2) for ptr in sample]
        col = [value for value in col if value is not None]
        if col and all(value == 0 for value in col):
            slots -= 1
        else:
            break
    return slots

TABLES = {
    3:  dict(stride=10),
    4:  dict(stride=0x1C),
    6:  dict(stride=0x18),
    8:  dict(stride=0x14),
    9:  dict(stride=0x18),
    10: dict(stride=0x24),
}

GLOBAL_LABELS = {
    0: "device identity/config header",
    1: "timer/sampling scale table",
    2: "string descriptor table",
    3: "string variable descriptors",
    4: "numeric/settings descriptors",
    5: "display-name override table",
    6: "config/status descriptors",
    7: "unidentified globals[7] table",
    8: "enum/menu descriptors",
    9: "timer/composite descriptors",
    10: "internal numeric descriptors",
    11: "BRP/PLD/SAD channels",
    12: "CSL/AEV/EVE channels",
    13: "STR channel fields",
    14: "NPD signal group",
    15: "NPA signal group",
    16: "variable groups",
    17: "signal group descriptors",
    18: "stream descriptors",
    19: "stream table",
    20: "PDL definition",
    21: "PDL rules/count record",
    22: "flat UART name table",
    23: "UART name lookup buckets",
    24: "mode membership table",
    25: "mode count",
    26: "TCE/PBT/PMD/FTX/RAW/DRT/CPU/SSK channels",
    27: "APN/CSN/BRH channels",
    28: "OXH channel",
    29: "sentinel/end marker",
}

FLAG_DEFS = {
    0: ("ACT", "Active -- master enable"),
    1: ("VIS", "Visible in menu"),
    2: ("EDT", "Editable by user"),
    3: ("B3",  "Unknown/reserved"),
    4: ("RO",  "Read-only lock"),
    5: ("DRT", "Dirty/changed"),
    6: ("FAC", "Factory default marker"),
    7: ("B7",  "Unknown"),
}


class Flash:
    def __init__(self, path, base=FLASH_BASE):
        with open(path, "rb") as f:
            self.data = f.read()
        self.base = base
        self.end  = base + len(self.data)

    def _o(self, addr):
        o = addr - self.base
        return o if 0 <= o < len(self.data) else None

    def u8(self, a):
        o = self._o(a)
        return self.data[o] if o is not None else None

    def u16(self, a):
        o = self._o(a)
        return struct.unpack_from("<H", self.data, o)[0] if o is not None and o+2 <= len(self.data) else None

    def s16(self, a):
        o = self._o(a)
        return struct.unpack_from("<h", self.data, o)[0] if o is not None and o+2 <= len(self.data) else None

    def u32(self, a):
        o = self._o(a)
        return struct.unpack_from("<I", self.data, o)[0] if o is not None and o+4 <= len(self.data) else None

    def s32(self, a):
        o = self._o(a)
        return struct.unpack_from("<i", self.data, o)[0] if o is not None and o+4 <= len(self.data) else None

    def blob(self, a, n):
        o = self._o(a)
        return self.data[o:o+n] if o is not None and o+n <= len(self.data) else None

    def cstr(self, a, mx=256):
        o = self._o(a)
        if o is None: return None
        e = self.data.find(b'\x00', o, min(o+mx, len(self.data)))
        if e < 0: e = min(o+mx, len(self.data))
        return self.data[o:e]

    def is_flash_ptr(self, v):
        return v is not None and self.base <= v < self.end

    def is_ram_ptr(self, v):
        return v is not None and RAM_BASE <= v < RAM_BASE + 0x20000



def find_globals_array(flash):
    """Find the globals[] pointer array by scanning for a run of ascending flash pointers.

    The globals array is a flat array of u32 pointers in the CCX region.
    Signature: 10+ consecutive u32 values that are valid flash pointers,
    mostly in ascending order, within the CCX address range.
    """
    scan_start = flash.base + 0x4000   # CCX starts after BLX
    scan_end = flash.base + 0x8000     # globals is early in CCX
    best_score, best_addr = 0, None

    for probe in range(scan_start, scan_end, 4):
        score = 0
        prev = 0
        for i in range(20):
            ptr = flash.u32(probe + i * 4)
            if ptr is None:
                break
            if flash.is_flash_ptr(ptr):
                score += 1
                if ptr > prev:
                    score += 1  # bonus for ascending order
                prev = ptr
            elif ptr == 0 or ptr == 0xFFFFFFFF:
                pass  # sentinel, don't penalize
            else:
                if i < 10:
                    break  # non-pointer too early = wrong candidate
        if score > best_score:
            best_score = score
            best_addr = probe

    return best_addr, best_score


def find_tables_direct(flash):
    """Find descriptor tables by locating the globals[] pointer array.

    Scans CCX for the globals pointer array (run of ascending flash pointers),
    then reads table addresses directly from it.
    """
    results = {}

    print("[*] Scanning for globals[] pointer array...")
    g_addr, g_score = find_globals_array(flash)

    if not g_addr or g_score < 20:
        print(f"[-] globals[] not found (best score={g_score})")
        return results

    print(f"[+] globals[] at 0x{g_addr:08X} (score={g_score})")
    results['_globals_addr'] = g_addr

    # Read all table pointers
    ptrs = {i: flash.u32(g_addr + i * 4) for i in range(30)}
    results['_globals_values'] = ptrs

    for t in (3, 4, 6, 8, 9, 10):
        if ptrs.get(t) and flash.is_flash_ptr(ptrs[t]):
            results[f"table{t}"] = ptrs[t]
            print(f"    globals[{t:2d}] = 0x{ptrs[t]:08X}")

    if ptrs.get(1) and flash.is_flash_ptr(ptrs[1]):
        results['timers'] = ptrs[1]

    if ptrs.get(5) and flash.is_flash_ptr(ptrs[5]):
        results['globals5'] = ptrs[5]

    if ptrs.get(2) and flash.is_flash_ptr(ptrs[2]):
        results['globals2'] = ptrs[2]

    if ptrs.get(23) and flash.is_flash_ptr(ptrs[23]):
        results['names'] = ptrs[23]

    if ptrs.get(19) and flash.is_flash_ptr(ptrs[19]):
        results['streams'] = ptrs[19]

    if ptrs.get(14) and flash.is_flash_ptr(ptrs[14]):
        results['npd'] = ptrs[14]

    if ptrs.get(15) and flash.is_flash_ptr(ptrs[15]):
        results['npa'] = ptrs[15]

    if ptrs.get(22) and flash.is_flash_ptr(ptrs[22]):
        results['signals'] = ptrs[22]

    if ptrs.get(0) and flash.is_flash_ptr(ptrs[0]):
        results['device'] = ptrs[0]
    if ptrs.get(20) and flash.is_flash_ptr(ptrs[20]):
        results['pdl'] = ptrs[20]
    if ptrs.get(21) and flash.is_flash_ptr(ptrs[21]):
        results['pdl_rules'] = ptrs[21]
    if ptrs.get(24) and flash.is_flash_ptr(ptrs[24]):
        results['modes'] = ptrs[24]
        # globals[25] is count, not a pointer
        g25 = ptrs.get(25, 0)
        if 0 < g25 < 200:
            results['modes_count'] = g25
    if ptrs.get(16) and flash.is_flash_ptr(ptrs[16]):
        results['vargroups'] = ptrs[16]
    if ptrs.get(17) and flash.is_flash_ptr(ptrs[17]):
        results['desc17'] = ptrs[17]
    if ptrs.get(18) and flash.is_flash_ptr(ptrs[18]):
        results['desc18'] = ptrs[18]
    if ptrs.get(11) and flash.is_flash_ptr(ptrs[11]):
        results['brp'] = ptrs[11]
    if ptrs.get(12) and flash.is_flash_ptr(ptrs[12]):
        results['csl'] = ptrs[12]
    if ptrs.get(13) and flash.is_flash_ptr(ptrs[13]):
        results['str_ch'] = ptrs[13]
    if ptrs.get(26) and flash.is_flash_ptr(ptrs[26]):
        results['tce'] = ptrs[26]
    if ptrs.get(27) and flash.is_flash_ptr(ptrs[27]):
        results['apn'] = ptrs[27]
    if ptrs.get(28) and flash.is_flash_ptr(ptrs[28]):
        results['oxh'] = ptrs[28]

    return results


def decode_flags(f):
    return "|".join(s for bit, (s, _) in FLAG_DEFS.items() if f & (1 << bit)) or "-"


def fmt_flags(f):
    return f"fl=0x{f:04X} [{decode_flags(f):>20s}]"


def _vid_str(var_id, db=None):
    """Format var_id with optional UART name: '0x02C4:BRP' or '0x001E'."""
    if db and db.names:
        n = db.uart_name(var_id)
        if n:
            return f"0x{var_id:04X}:{n}"
    return f"0x{var_id:04X}"


def _g4_idx_ref(idx, db=None, none="none", detail=False):
    if idx == 0x7FFF:
        return none
    idx_hex = f"0x{idx & 0xFFFF:04X}"
    entry = db.g4_by_idx(idx) if db else None
    if entry:
        var = _vid_str(entry.var_id, db)
        if detail:
            return f"[4] idx {idx_hex} -> var_id {var}"
        return f"[4]{idx_hex}->{var}"
    if detail:
        return f"[4] idx {idx_hex} (not loaded)"
    return f"[4]{idx_hex}"


class Entry3:
    """globals[3] -- String variable descriptor (10 bytes).

    30 entries for string-type variables (device ID, serial, etc.).
    Each variable has a RAM shadow at 0x20000104 + idx*8: {u16 flags, u32 value}.

    ROM record layout:
      +0x00  u16  flags
      +0x02  u8   notify_handler  (callback index, 0=none)
      +0x03  u8   _pad
      +0x04  s16  linked_var_id   (propagate value on change, 0x7FFF=none)
      +0x06  s16  format_str_id   (display format string, 0x00DE=none)
      +0x08  u16  max_length      (max string length / default)
    """
    TABLE = 3
    def __init__(self, fl, addr, idx, id_base):
        self.addr, self.idx = addr, idx
        self.var_id = id_base + idx
        self.flags          = fl.u16(addr + 0x00)
        self.notify_handler = fl.u8(addr + 0x02)   # callback jump table index
        self.linked_var_id  = fl.s16(addr + 0x04)   # value propagation target
        self.format_str_id  = fl.s16(addr + 0x06)   # format string, 0xDE=none
        self.max_length     = fl.u16(addr + 0x08)    # max string length

    def oneline(self, db=None):
        off = self.addr - (db.table_bases.get(3, self.addr) if db else self.addr)
        lv = _vid_str(self.linked_var_id, db) if self.linked_var_id != 0x7FFF else "--"
        fs = f"0x{self.format_str_id & 0xFFFF:04X}" if self.format_str_id != 0xDE else "--"
        cb = f"cb={self.notify_handler}" if self.notify_handler else ""
        return (f"0x{self.idx:03X} var={_vid_str(self.var_id, db)} @0x{self.addr:08X} +0x{off:04X}  "
                f"{fmt_flags(self.flags)}  "
                f"maxlen={self.max_length}  linked={lv}  fmt={fs}  {cb}")

    def detail(self, db=None):
        off = self.addr - (db.table_bases.get(3, self.addr) if db else self.addr)
        lv = _vid_str(self.linked_var_id, db) if self.linked_var_id != 0x7FFF else "0x7FFF (none)"
        fs = f"0x{self.format_str_id & 0xFFFF:04X}" if self.format_str_id != 0xDE else "0x00DE (none)"
        return (f"  [3] idx=0x{self.idx:03X}  var_id={_vid_str(self.var_id, db)}  "
                f"@ 0x{self.addr:08X} +0x{off:04X}\n"
                f"    flags          = 0x{self.flags:04X} ({decode_flags(self.flags)})\n"
                f"    notify_handler = {self.notify_handler}\n"
                f"    linked_var_id  = {lv}\n"
                f"    format_str_id  = {fs}\n"
                f"    max_length     = {self.max_length}")


class Entry4:
    TABLE = 4
    def __init__(self, fl, addr, idx, id_base):
        self.addr, self.idx = addr, idx
        self.var_id = id_base + idx
        self.flags         = fl.u16(addr + 0x00)
        self.callback_id   = fl.u8(addr + 0x02)
        self._pad_03       = fl.u8(addr + 0x03)   # alignment padding (always 0)
        self.next_var_idx  = fl.s16(addr + 0x04)
        self.name_str_id   = fl.u16(addr + 0x06)  # variable name/label string ID
        self.default_value = fl.s32(addr + 0x08)
        self.max_value     = fl.s32(addr + 0x0C)
        self.min_value     = fl.s32(addr + 0x10)
        self.decimal_places= fl.u8(addr + 0x14)
        self._pad_15       = fl.u8(addr + 0x15)   # alignment padding (always 0)
        self.scale_factor  = fl.s16(addr + 0x16)
        self.step_size     = fl.s16(addr + 0x18)
        self.units_str_id  = fl.u16(addr + 0x1A)

    def _fmt(self, v):
        s = self.scale_factor
        dp = self.decimal_places if self.decimal_places is not None and self.decimal_places < 10 else 0
        if s and s > 0:  return f"{v / s:.{dp}f}"
        if s and s < 0:  return f"{v * (-s)}"
        return str(v)

    def range_str(self):
        return (f"{self._fmt(self.min_value)} .. {self._fmt(self.max_value)} "
                f"step {self._fmt(self.step_size)}")

    def scale_str(self):
        s = self.scale_factor
        if s > 0: return f"/{s}"
        if s < 0: return f"x{-s}"
        return "raw"

    def oneline(self, db=None):
        off = self.addr - (db.table_bases.get(4, self.addr) if db else self.addr)
        name = ""
        if db and self.name_str_id and self.name_str_id not in (0xFFFF, 0xDE):
            n = db.string(self.name_str_id)
            if n: name = f' "{n}"'
        unit = ""
        if db and self.units_str_id and self.units_str_id not in (0xFFFF, 0xDE):
            u = db.string(self.units_str_id)
            if u: unit = f" [{u}]"
        chain_ref = _g4_idx_ref(self.next_var_idx, db, none="")
        chain = f"next={chain_ref}" if chain_ref else ""
        g5 = ""
        if db:
            rec = db.g5_lookup(self.idx)
            if rec is not None:
                a, b = rec
                parts_g5 = []
                if a != 0xDE:
                    sa = db.string(a) if db.strtab else None
                    parts_g5.append(f'a="{sa}"' if sa else f'a=0x{a:04X}')
                if b != 0xDE:
                    sb = db.string(b) if db.strtab else None
                    parts_g5.append(f'b="{sb}"' if sb else f'b=0x{b:04X}')
                if parts_g5:
                    g5 = f"  g5[{', '.join(parts_g5)}]"
                else:
                    g5 = "  g5[HIDDEN]"
        return (f"0x{self.idx:03X} var={_vid_str(self.var_id, db)} @0x{self.addr:08X} +0x{off:05X}  "
                f"{fmt_flags(self.flags)}  "
                f"def={self._fmt(self.default_value):>8s}  "
                f"[{self.range_str()}]{unit}  "
                f"{chain}{name}{g5}")

    def detail(self, db=None):
        off = self.addr - (db.table_bases.get(4, self.addr) if db else self.addr)
        chain_str = _g4_idx_ref(self.next_var_idx, db, none="end", detail=True)
        name = ""
        if db and self.name_str_id and self.name_str_id not in (0xFFFF, 0xDE):
            n = db.string(self.name_str_id)
            if n: name = f' = "{n}"'
        unit = ""
        if db and self.units_str_id and self.units_str_id not in (0xFFFF, 0xDE):
            u = db.string(self.units_str_id)
            if u: unit = f' = "{u}"'
        sub_base = db.g4_subrange_base_idx if db else None
        sub = (f"  (sub-range 0x{sub_base:03X}+{self.idx - sub_base})"
               if sub_base is not None and self.idx >= sub_base else "")
        lines = [
            f"  [4] idx=0x{self.idx:03X}  var_id={_vid_str(self.var_id, db)}  "
            f"@ 0x{self.addr:08X} +0x{off:05X}{sub}",
            f"    flags      = 0x{self.flags:04X} ({decode_flags(self.flags)})  "
            f"0b{self.flags:016b}",
            f"    callback   = {self.callback_id}",
            f"    next_chain = 0x{self.next_var_idx & 0xFFFF:04X} ({chain_str})",
            f"    name_str   = 0x{self.name_str_id:04X}{name}",
            f"    default    = {self.default_value} ({self._fmt(self.default_value)})",
            f"    max        = {self.max_value} ({self._fmt(self.max_value)})",
            f"    min        = {self.min_value} ({self._fmt(self.min_value)})",
            f"    step       = {self.step_size} ({self._fmt(self.step_size)})",
            f"    scale      = {self.scale_factor} ({self.scale_str()})  "
            f"dp={self.decimal_places}",
            f"    range      : {self.range_str()}",
            f"    units_str  = 0x{self.units_str_id:04X}{unit}",
        ]
        if db:
            rec = db.g5_lookup(self.idx)
            if rec is not None:
                a, b = rec
                sa = db.string(a) if db.strtab and a != 0xDE else None
                sb = db.string(b) if db.strtab and b != 0xDE else None
                lines.append(f"    -- globals[5] display-name override --")
                lines.append(f"      str_a = 0x{a:04X}"
                             f'{f" ({sa!r})" if sa else " [HIDDEN]" if a == 0xDE else ""}')
                lines.append(f"      str_b = 0x{b:04X}"
                             f'{f" ({sb!r})" if sb else " [HIDDEN]" if b == 0xDE else ""}')
                if a == 0xDE and b == 0xDE:
                    lines.append("      -> NOT VISIBLE in any mode")
        return "\n".join(lines)


class Entry6:
    TABLE = 6
    def __init__(self, fl, addr, idx, id_base):
        self.addr, self.idx = addr, idx
        self.var_id = id_base + idx
        self.flags       = fl.u16(addr + 0x00)
        self.config_group= fl.u16(addr + 0x02)    # sub-group/category index
        self.linked_var  = fl.u16(addr + 0x04)     # linked var_id pair
        self.parent_var  = fl.u16(addr + 0x06)     # parent var_id (often 0x00DE)
        self.default     = fl.u32(addr + 0x08)
        self.perm_mask   = fl.u32(addr + 0x0C)
        self.item_count  = fl.u8(addr + 0x10)      # child/option count
        self.step_div    = fl.u8(addr + 0x11)
        self.child_index = fl.u16(addr + 0x12)     # first child index (into g[8])
        self.label_str   = fl.u16(addr + 0x14)     # label string_id
        self._pad_16     = fl.u16(addr + 0x16)     # always 0

    def oneline(self, db=None):
        off = self.addr - (db.table_bases.get(6, self.addr) if db else self.addr)
        lbl = ""
        if db and self.label_str and self.label_str not in (0xFFFF, 0xDE):
            s = db.string(self.label_str)
            if s: lbl = f' "{s}"'
        return (f"0x{self.idx:03X} var={_vid_str(self.var_id, db)} @0x{self.addr:08X} +0x{off:04X}  "
                f"{fmt_flags(self.flags)}  "
                f"def=0x{self.default:08X}  perm=0x{self.perm_mask:08X}  "
                f"items={self.item_count}  stepdiv={self.step_div}  "
                f"child=0x{self.child_index:04X}{lbl}")

    def detail(self, db=None):
        off = self.addr - (db.table_bases.get(6, self.addr) if db else self.addr)
        sd = "1" if self.step_div == 0 else f"{self.step_div}/4"
        lbl = ""
        if db and self.label_str and self.label_str not in (0xFFFF, 0xDE):
            s = db.string(self.label_str)
            if s: lbl = f' = "{s}"'
        pv = _vid_str(self.parent_var, db) if self.parent_var != 0xDE else "0x00DE (none)"
        lv = _vid_str(self.linked_var, db) if self.linked_var != 0 else "0x0000 (none)"
        return (
            f"  [6] idx=0x{self.idx:03X}  var_id={_vid_str(self.var_id, db)}  "
            f"@ 0x{self.addr:08X} +0x{off:04X}\n"
            f"    flags      = 0x{self.flags:04X} ({decode_flags(self.flags)})\n"
            f"    group      = {self.config_group}  linked={lv}  parent={pv}\n"
            f"    default    = 0x{self.default:08X} ({self.default})\n"
            f"    perm       = 0x{self.perm_mask:08X}  "
            f"0b{self.perm_mask:032b}\n"
            f"    item_count = {self.item_count}  step_div={self.step_div} (step={sd})\n"
            f"    child_idx  = 0x{self.child_index:04X}\n"
            f"    label_str  = 0x{self.label_str:04X}{lbl}")


class Entry8:
    TABLE = 8
    def __init__(self, fl, addr, idx, id_base):
        self.addr, self.idx = addr, idx
        self.var_id = id_base + idx
        self.flags         = fl.u16(addr + 0x00)
        self.callback_id   = fl.u8(addr + 0x02)
        self._pad_03       = fl.u8(addr + 0x03)   # alignment padding (always 0)
        self.linked_var_idx= fl.s16(addr + 0x04)
        self.name_str_id   = fl.u16(addr + 0x06)
        self.default_value = fl.u8(addr + 0x08)
        self.num_options   = fl.u8(addr + 0x09)
        self.param_0a      = fl.s16(addr + 0x0A)   # s16 param slot (0 = unused)
        self.perm_mask     = fl.u32(addr + 0x0C)
        self.base_str_id   = fl.s16(addr + 0x10)
        self.param_12      = fl.s16(addr + 0x12)   # s16 param slot (0 = unused)

    def has_strings(self):
        return self.base_str_id not in (0x00DE, -1, 0) and self.base_str_id >= 0

    def option_strings(self, db):
        """Return list of option name strings."""
        if not db or not self.has_strings():
            return []
        out = []
        for i in range(self.num_options):
            s = db.string(self.base_str_id + i)
            if s is None:
                out.append(f"?str#{self.base_str_id + i}")
            else:
                out.append(s)
        return out

    def perm_bits(self):
        """Return list of (option_idx, allowed) for each option."""
        return [(i, bool(self.perm_mask & (1 << i)))
                for i in range(self.num_options)]

    def oneline(self, db=None):
        off = self.addr - (db.table_bases.get(8, self.addr) if db else self.addr)
        name = ""
        if db and self.name_str_id and self.name_str_id not in (0xFFFF, 0xDE):
            n = db.string(self.name_str_id)
            if n: name = f' "{n}"'
        link_ref = _g4_idx_ref(self.linked_var_idx, db, none="")
        link = f"dep={link_ref}" if link_ref else ""
        opts = ""
        if db and self.has_strings():
            labels = self.option_strings(db)
            parts = []
            for i, lb in enumerate(labels):
                if lb:
                    parts.append(lb)
                elif lb is not None:
                    # Empty string in ROM -- likely filled at runtime (e.g. formatted numeric)
                    parts.append(f"[str#0x{self.base_str_id + i:04X}]")
                else:
                    parts.append(f"?str#0x{self.base_str_id + i:04X}")
            opts = "  (" + ", ".join(parts) + ")"
        return (f"0x{self.idx:03X} var={_vid_str(self.var_id, db)} @0x{self.addr:08X} +0x{off:04X}  "
                f"{fmt_flags(self.flags)}  "
                f"def={self.default_value}  opts={self.num_options:>2}  "
                f"perm=0x{self.perm_mask:08X}  {link}{name}{opts}")

    def detail(self, db=None):
        off = self.addr - (db.table_bases.get(8, self.addr) if db else self.addr)
        link = _g4_idx_ref(self.linked_var_idx, db, none="none", detail=True)
        name = ""
        if db and self.name_str_id and self.name_str_id not in (0xFFFF, 0xDE):
            n = db.string(self.name_str_id)
            if n: name = f' = "{n}"'
        stxt = "none"
        if self.has_strings():
            stxt = f"str#{self.base_str_id}"
            if db:
                s = db.string(self.base_str_id)
                if s: stxt += f' = "{s}"'
        lines = [
            f"  [8] idx=0x{self.idx:03X}  var_id={_vid_str(self.var_id, db)}  "
            f"@ 0x{self.addr:08X} +0x{off:04X}",
            f"    flags      = 0x{self.flags:04X} ({decode_flags(self.flags)})  "
            f"0b{self.flags:016b}",
            f"    callback   = {self.callback_id}",
            f"    dep_head   = 0x{self.linked_var_idx & 0xFFFF:04X} ({link})",
            f"    name_str   = 0x{self.name_str_id:04X}{name}",
            f"    default    = {self.default_value}   num_options={self.num_options}",
            f"    param_0a   = {self.param_0a}   param_12={self.param_12}",
            f"    perm_mask  = 0x{self.perm_mask:08X}  "
            f"0b{self.perm_mask:032b}",
            f"    base_str   = 0x{self.base_str_id & 0xFFFF:04X} ({stxt})",
        ]
        # Per-option breakdown
        if self.num_options > 0:
            lines.append("    -- options --")
            for i in range(self.num_options):
                allowed = "Y" if self.perm_mask & (1 << i) else "N"
                label = ""
                if db and self.has_strings():
                    s = db.string(self.base_str_id + i)
                    sid = self.base_str_id + i
                    if s:
                        label = f'  "{s}"'
                    elif s is not None:
                        label = f'  [empty -- runtime-filled? str#0x{sid:04X}]'
                    else:
                        label = f'  ?str#0x{sid:04X}'
                lines.append(f"      [{i:>2}] perm={allowed}{label}")
            lan_idx = db._table_index_for_name('LAN', 8, fallback=5) if db else 5
            lnc_idx = db._table_index_for_name('LNC', 6, fallback=7) if db else 7
            htx_idx = db._table_index_for_name('HTX', 8, fallback=0x19) if db else 0x19
            cco_idx = db._table_index_for_name('CCO', 8, fallback=0x16) if db else 0x16
            hum_idx = db._table_index_for_name('HUM', 8, fallback=0x1A) if db else 0x1A
            if self.idx == lan_idx:
                lines.append(f"    NOTE: idx=0x{lan_idx:03X} has extra language-availability gate "
                             f"via LNC (globals[6] idx 0x{lnc_idx:03X}, available languages bitmask)")
            elif self.idx == htx_idx:
                lines.append(f"    NOTE: idx=0x{htx_idx:03X} has extra visibility gate "
                             f"checking CCO ([8] idx 0x{cco_idx:03X}) and HUM ([8] idx 0x{hum_idx:03X})")
        return "\n".join(lines)


ENTRY_CLS = {3: Entry3, 4: Entry4, 6: Entry6, 8: Entry8}


class Entry9:
    """globals[9] -- Timer/composite variable descriptor (0x18 bytes).

    Only 1 entry (var_id 0x2B2). Similar layout to Entry8 but with
    min/max/step range fields instead of option strings.

    ROM record layout (0x18 = 24 bytes):
      +0x00  u16  flags
      +0x02  u16  pad
      +0x04  u16  linked_var_idx (0x0141 on AS10)
      +0x06  u16  name_str_id    (0xDE = hidden)
      +0x08  u8   default_byte
      +0x09  u8   num_options
      +0x0A  u16  pad
      +0x0C  u32  perm_bitmask
      +0x10  u16  base_str_id    (0xDE = hidden)
      +0x12  u16  min_value
      +0x14  u16  max_value
      +0x16  u16  step_size
    """
    TABLE = 9

    def __init__(self, fl, addr, idx, id_base):
        self.addr, self.idx = addr, idx
        self.var_id = id_base + idx

        self.flags        = fl.u16(addr + 0x00)
        self.pad_02       = fl.u16(addr + 0x02)
        self.linked_var   = fl.u16(addr + 0x04)
        self.name_str_id  = fl.u16(addr + 0x06)
        self.default_byte = fl.u8(addr + 0x08)
        self.num_options  = fl.u8(addr + 0x09)
        self.pad_0a       = fl.u16(addr + 0x0A)
        self.perm_bitmask = fl.u32(addr + 0x0C)
        self.base_str_id  = fl.u16(addr + 0x10)
        self.min_value    = fl.u16(addr + 0x12)
        self.max_value    = fl.u16(addr + 0x14)
        self.step_size    = fl.u16(addr + 0x16)

    def oneline(self, db=None):
        off = self.addr - (db.table_bases.get(9, self.addr) if db else self.addr)
        name = ""
        if db and self.name_str_id and self.name_str_id not in (0xFFFF, 0xDE):
            s = db.string(self.name_str_id)
            if s: name = f'  "{s}"'
        return (f"0x{self.idx:03X} var={_vid_str(self.var_id, db)} @0x{self.addr:08X} +0x{off:04X}  "
                f"{fmt_flags(self.flags)}  "
                f"def={self.default_byte}  opts={self.num_options}  "
                f"[{self.min_value}..{self.max_value} step {self.step_size}]  "
                f"perm=0x{self.perm_bitmask:08X}{name}")

    def detail(self, db=None):
        off = self.addr - (db.table_bases.get(9, self.addr) if db else self.addr)
        name = ""
        if db and self.name_str_id and self.name_str_id not in (0xFFFF, 0xDE):
            s = db.string(self.name_str_id)
            if s: name = f' = "{s}"'
        base_str = ""
        if db and self.base_str_id and self.base_str_id not in (0xFFFF, 0xDE):
            s = db.string(self.base_str_id)
            if s: base_str = f' = "{s}"'
        link = f"-> idx 0x{self.linked_var:04X}" if self.linked_var != 0x7FFF else "none"
        return (
            f"  [9] idx=0x{self.idx:03X}  var_id={_vid_str(self.var_id, db)}  "
            f"@ 0x{self.addr:08X} +0x{off:04X}\n"
            f"    flags      = 0x{self.flags:04X} ({decode_flags(self.flags)})  "
            f"0b{self.flags:016b}\n"
            f"    linked     = 0x{self.linked_var:04X} ({link})\n"
            f"    name_str   = 0x{self.name_str_id:04X}{name}\n"
            f"    default    = {self.default_byte}\n"
            f"    num_opts   = {self.num_options}\n"
            f"    perm_mask  = 0x{self.perm_bitmask:08X}  "
            f"0b{self.perm_bitmask:032b}\n"
            f"    base_str   = 0x{self.base_str_id:04X}{base_str}\n"
            f"    range      = {self.min_value}..{self.max_value} step {self.step_size}")


ENTRY_CLS[9] = Entry9


class Entry10:
    """globals[10] -- Internal numeric variable descriptor (0x24 bytes).

    3 entries, not exposed through the variable ID dispatch system.
    Accessed directly by index (0, 1, 2) from specific code paths.

    ROM record layout (0x24 = 36 bytes):
      +0x00  u16  flags
      +0x02  u8   callback_id
      +0x03  u8   _pad (alignment)
      +0x04  s16  next_var_idx   (always 0x7FFF = none)
      +0x06  u16  name_str_id
      +0x08  s32  default_value  (copied to secondary RAM on init)
      +0x0C  s32  max_value      (upper clamp)
      +0x10  s32  min_value      (lower clamp)
      +0x14  u8   decimal_places
      +0x15  u8   _pad (alignment)
      +0x16  s16  scale_factor
      +0x18  s16  step_size
      +0x1A  u16  units_str_id
      +0x1C  s32  ram_base_index (index into secondary RAM array)
      +0x20  u8   ram_entry_count
      +0x21  3B   _pad (tail alignment)
    """
    TABLE = 10

    def __init__(self, fl, addr, idx):
        self.addr, self.idx = addr, idx
        # No var_id in the standard dispatch system
        self.var_id = 0xF000 + idx  # synthetic ID for internal tracking

        self.flags          = fl.u16(addr + 0x00)
        self.callback_id    = fl.u8(addr + 0x02)
        self._pad_03        = fl.u8(addr + 0x03)   # alignment padding (always 0)
        self.next_var_idx   = fl.s16(addr + 0x04)   # linked var (always 0x7FFF = none)
        self.name_str_id    = fl.u16(addr + 0x06)
        self.default_value  = fl.s32(addr + 0x08)
        self.max_value      = fl.s32(addr + 0x0C)
        self.min_value      = fl.s32(addr + 0x10)
        self.decimal_places = fl.u8(addr + 0x14)
        self._pad_15        = fl.u8(addr + 0x15)   # alignment padding (always 0)
        self.scale_factor   = fl.s16(addr + 0x16)
        self.step_size      = fl.s16(addr + 0x18)
        self.units_str_id   = fl.u16(addr + 0x1A)
        self.ram_base_index = fl.s32(addr + 0x1C)
        self.ram_count      = fl.u8(addr + 0x20)

    def _fmt(self, v):
        s = self.scale_factor
        dp = self.decimal_places if self.decimal_places is not None and self.decimal_places < 10 else 0
        if s and s > 0:  return f"{v / s:.{dp}f}"
        if s and s < 0:  return f"{v * (-s)}"
        return str(v)

    def range_str(self):
        return (f"{self._fmt(self.min_value)} .. {self._fmt(self.max_value)} "
                f"step {self._fmt(self.step_size)}")

    def scale_str(self):
        s = self.scale_factor
        if s > 0: return f"/{s}"
        if s < 0: return f"x{-s}"
        return "raw"

    def oneline(self, db=None):
        off = self.addr - (db.table_bases.get(10, self.addr) if db else self.addr)
        name = ""
        if db and self.name_str_id and self.name_str_id not in (0xFFFF, 0xDE, 0):
            n = db.string(self.name_str_id)
            if n: name = f' "{n}"'
        unit = ""
        if db and self.units_str_id and self.units_str_id not in (0xFFFF, 0xDE, 0):
            u = db.string(self.units_str_id)
            if u: unit = f" [{u}]"
        return (f"0x{self.idx:03X} (int) @0x{self.addr:08X} +0x{off:04X}  "
                f"{fmt_flags(self.flags)}  "
                f"def={self._fmt(self.default_value):>8s}  "
                f"[{self.range_str()}]{unit}  "
                f"ram[{self.ram_base_index}..+{self.ram_count}]{name}")

    def detail(self, db=None):
        off = self.addr - (db.table_bases.get(10, self.addr) if db else self.addr)
        name = ""
        if db and self.name_str_id and self.name_str_id not in (0xFFFF, 0xDE, 0):
            n = db.string(self.name_str_id)
            if n: name = f' = "{n}"'
        unit = ""
        if db and self.units_str_id and self.units_str_id not in (0xFFFF, 0xDE, 0):
            u = db.string(self.units_str_id)
            if u: unit = f' = "{u}"'
        return (
            f"  [10] idx=0x{self.idx:03X}  (internal, no var_id)  "
            f"@ 0x{self.addr:08X} +0x{off:04X}\n"
            f"    flags      = 0x{self.flags:04X} ({decode_flags(self.flags)})  "
            f"0b{self.flags:016b}\n"
            f"    callback   = {self.callback_id}\n"
            f"    name_str   = 0x{self.name_str_id:04X}{name}\n"
            f"    default    = {self.default_value} ({self._fmt(self.default_value)})\n"
            f"    max        = {self.max_value} ({self._fmt(self.max_value)})\n"
            f"    min        = {self.min_value} ({self._fmt(self.min_value)})\n"
            f"    step       = {self.step_size} ({self._fmt(self.step_size)})\n"
            f"    scale      = {self.scale_factor} ({self.scale_str()})  "
            f"dp={self.decimal_places}\n"
            f"    range      : {self.range_str()}\n"
            f"    units_str  = 0x{self.units_str_id:04X}{unit}\n"
            f"    ram_base   = {self.ram_base_index}  ram_count={self.ram_count}")


ENTRY_CLS[10] = Entry10


class StringTable:
    """
    globals[2] is a table of 8-byte records:
      +0x00: u16 max_strlen (max char count across all locale translations)
      +0x02: u16 _pad (alignment, always 0)
      +0x04: u32 pointer to locale index array

    locale_index_array: array of globals[2]-inferred language slots
    string_raw_table[index] -> pointer to C string

    string_lookup(str_id, locale):
      locale_arr = u32(globals[2] + str_id*8 + 4)
      raw_index  = u16(locale_arr + locale*2)
      str_ptr    = u32(raw_table + raw_index*4)
      return cstr(str_ptr)
    """
    def __init__(self, flash, g2_addr, num_langs, raw_addr=None):
        self.fl, self.g2, self.num_langs = flash, g2_addr, num_langs
        # Derive raw_table_ptr from g2[0].locale_arr - 8 if not provided.
        # Layout: [raw_table_ptr u32][0xFFFFFFFF][locale_arr[0]...]
        # raw_table_ptr is an indirect pointer: *(raw_table_ptr) -> string pointer array base
        if raw_addr is None:
            la0 = flash.u32(g2_addr + 4)  # g2[0].locale_arr
            if la0 and flash.is_flash_ptr(la0):
                raw_addr = la0 - 8
            else:
                raise ValueError("cannot derive string raw table from globals[2]")
        raw_ptr = flash.u32(raw_addr)
        if raw_ptr and flash.is_flash_ptr(raw_ptr):
            self.raw = raw_ptr
            print(f"    string_raw_table: 0x{raw_addr:08X} -> 0x{raw_ptr:08X}")
        else:
            raise ValueError(
                f"string raw table dereference failed at 0x{raw_addr:08X}")
        self.max_id = 0
        for i in range(2000):
            ptr = flash.u32(self.g2 + i * 8 + 4)
            if ptr is None or (ptr != 0 and not flash.is_flash_ptr(ptr)):
                break
            self.max_id = i + 1

    def get(self, str_id, lang=0):
        if str_id < 0 or str_id >= self.max_id:
            return None
        la = self.fl.u32(self.g2 + str_id * 8 + 4)
        if not la or not self.fl.is_flash_ptr(la):
            return None
        ri = self.fl.u16(la + lang * 2)
        if ri is None:
            return None
        sp = self.fl.u32(self.raw + ri * 4)
        if not sp or not self.fl.is_flash_ptr(sp):
            return None
        bs = self.fl.cstr(sp)
        if bs is None:
            return None
        try:
            return bs.decode('utf-8', errors='replace')
        except:
            return bs.hex()

    def get_all(self, str_id):
        return [self.get(str_id, l) for l in range(self.num_langs)]


class NameLookup:
    """globals[23]: 26-bucket lookup table mapping 3-letter UART names to var_ids.

    Structure: 26 entries x 8 bytes = {u32 subtable_ptr, u32 count}, one per letter A-Z.
    Each subtable entry: {u8 char2, u8 char3, u16 var_id}.
    """
    def __init__(self, flash, g23_addr):
        self.by_name = {}   # "ABC" -> var_id
        self.by_varid = {}  # var_id -> "ABC"
        total = 0
        for letter_idx in range(26):
            off = g23_addr + letter_idx * 8
            sub_ptr = flash.u32(off)
            count = flash.u32(off + 4)
            if not sub_ptr or not flash.is_flash_ptr(sub_ptr) or count is None or count > 200:
                continue
            for j in range(count):
                c2 = flash.u8(sub_ptr + j * 4)
                c3 = flash.u8(sub_ptr + j * 4 + 1)
                vid = flash.u16(sub_ptr + j * 4 + 2)
                if c2 is None or c3 is None or vid is None:
                    continue
                name = chr(letter_idx + ord('A')) + chr(c2) + chr(c3)
                self.by_name[name] = vid
                self.by_varid[vid] = name
                total += 1
        print(f"[+] globals[23]: UART name lookup, {total} variables")

    def name(self, var_id):
        return self.by_varid.get(var_id)

    def var_id(self, name):
        return self.by_name.get(name.upper())


class DeviceIdentity:
    """globals[0]: Device identity and config header.

    +0x00: u32[7]  CID components (reordered: CX g[1]-g[0]-g[3]-g[2]-g[5]-g[4]-g[6])
    +0x20: char[]  catalog number (e.g. '37101')
    +0x30: char[]  product name (e.g. 'AirSense 10 AutoSet')
    """
    def __init__(self, flash, addr):
        self.addr = addr
        self.cid_vals = [flash.u32(addr + i * 4) or 0 for i in range(7)]
        raw_cat = flash.cstr(addr + 0x20)
        self.catalog = raw_cat.decode('ascii', errors='replace') if raw_cat else ""
        raw_prod = flash.cstr(addr + 0x30)
        self.product = raw_prod.decode('ascii', errors='replace') if raw_prod else ""
        v = self.cid_vals
        self.cid = "CX%03d-%03d-%03d-%03d-%03d-%03d-%03d" % (
            v[1], v[0], v[3], v[2], v[5], v[4], v[6])
        if self.catalog or self.product:
            print(f"[+] globals[0]: {self.catalog} / {self.product} ({self.cid})")

    def dump(self):
        return (f"  Product code:  {self.catalog}\n"
                f"  Product name:  {self.product}\n"
                f"  CID:           {self.cid}")


class VariableGroups:
    """globals[16]: variable groups (AGL, CGL, RGL, etc.)

    Each entry: 16 bytes:
      +0x00: char[4]  group name (3-char + null)
      +0x04: u16      start_var_id
      +0x06: u16      param
      +0x08: u32      member_var_id_array_ptr
      +0x0C: u32      member_count
    """
    STRIDE = 16

    def __init__(self, flash, addr, end_addr=None, names=None):
        self.groups = []
        limit = (end_addr - addr) // self.STRIDE if end_addr and end_addr > addr else 16
        for i in range(limit):
            base = addr + i * self.STRIDE
            raw_name = flash.blob(base, 4)
            if not raw_name or not all(0x41 <= b <= 0x5A for b in raw_name[:3]):
                break
            name = raw_name[:3].decode('ascii')
            start_vid = flash.u16(base + 4)
            param = flash.u16(base + 6)
            arr_ptr = flash.u32(base + 8)
            count = flash.u32(base + 12)
            members = []
            if arr_ptr and flash.is_flash_ptr(arr_ptr) and count and count < 100:
                for j in range(count):
                    vid = flash.u16(arr_ptr + j * 2)
                    if vid is not None:
                        uart = names.name(vid) if names else None
                        members.append((vid, uart))
            self.groups.append({
                'name': name, 'start_vid': start_vid,
                'param': param, 'members': members,
            })
        print(f"[+] globals[16]: {len(self.groups)} variable groups")

    def dump(self, group_name=None):
        lines = []
        for g in self.groups:
            if group_name and g['name'] != group_name.upper():
                continue
            members = ', '.join(
                f"{u}" if u else f"0x{v:04X}" for v, u in g['members'])
            lines.append(f"  {g['name']} ({len(g['members'])} vars): {members}")
        return "\n".join(lines) if lines else f"  group '{group_name}' not found"


class DescriptorTable:
    """globals[17]/[18]: 8-byte descriptor records for signal groups and streams.

    g[17]: 2 entries — descriptors for NPD/NPA signal groups
    g[18]: 12 entries — descriptors for the 10 EEPROM streams (+ 2 header entries)

    Each record: {u16 a, u16 b, u16 c, u16 var_id}
    Stream entries share common prefix {0x01F6:UDT, 0x00E1, 0x00AD:NOC, <src_var_id>}.
    """
    STRIDE = 8

    def __init__(self, flash, gidx, addr, end_addr, names=None):
        self.gidx = gidx
        self.entries = []
        count = (end_addr - addr) // self.STRIDE
        for i in range(count):
            base = addr + i * self.STRIDE
            a = flash.u16(base)
            b = flash.u16(base + 2)
            c = flash.u16(base + 4)
            d = flash.u16(base + 6)
            if a is None:
                break
            uart_d = names.name(d) if names and d else None
            self.entries.append((a, b, c, d, uart_d))
        print(f"[+] globals[{gidx}]: {len(self.entries)} descriptor records")

    def dump(self):
        lines = [f"  {len(self.entries)} records (stride 8):"]
        for i, (a, b, c, d, uart) in enumerate(self.entries):
            u = f":{uart}" if uart else ""
            lines.append(f"    [{i:2d}] 0x{a:04X} 0x{b:04X} 0x{c:04X} 0x{d:04X}{u}")
        return "\n".join(lines)


class StreamTable:
    """globals[19]: stream table mapping EEPROM data channels.

    Each entry: 28 bytes.
      +0x00: char[4]  name (3-char + null)
      +0x04: u32      descriptor_ptr
      +0x08: u16      type (0x0004)
      +0x0A: u16      capacity
      +0x0C: u16      source_var_id
      +0x0E: u16      record_size
      +0x10-0x17:      reserved / extra fields
      +0x18: u32      last_field
    """
    STRIDE = 28

    def __init__(self, flash, g19_addr, end_addr=None, names=None):
        self.entries = []
        scan_end = end_addr if end_addr and end_addr > g19_addr else g19_addr + 0x400
        i = 0
        while g19_addr + (i + 1) * self.STRIDE <= scan_end:
            base = g19_addr + i * self.STRIDE
            raw_name = flash.blob(base, 4)
            if raw_name is None:
                break
            name = raw_name.split(b'\x00')[0].decode('ascii', errors='replace')
            if not name or not name[0].isalpha():
                break
            desc_ptr = flash.u32(base + 4)
            typ = flash.u16(base + 8)
            capacity = flash.u16(base + 0xA)
            var_id = flash.u16(base + 0xC)
            rec_size = flash.u16(base + 0x0E)
            last = flash.u32(base + 0x18)
            uart_name = names.name(var_id) if names and var_id else None
            self.entries.append({
                'name': name, 'desc_ptr': desc_ptr, 'type': typ,
                'capacity': capacity, 'rec_size': rec_size,
                'var_id': var_id, 'var_name': uart_name, 'max_records': last,
            })
            i += 1
        print(f"[+] globals[19]: stream table, {len(self.entries)} streams")

    def dump(self):
        lines = ["  Stream  Capacity  RecSz  VarID  VarName  +0x18"]
        for e in self.entries:
            sn = e['var_name'] or ''
            lines.append(f"  {e['name']:>5}  {e['capacity']:>8}  {e['rec_size']:>5}  "
                         f"0x{e['var_id']:04X}    {sn:>7}  0x{e['max_records']:04X}")
        return "\n".join(lines)


class NameTableFlat:
    """globals[22]: UART name table (flat format).

    Same data as globals[23] (bucketed name lookup) but as a flat array.
    Header = u16 var_ids, followed by flat entries.
    Then entries of {char[2] name_suffix, u16 var_id}.
    The 2-char suffix = UART name chars 2+3. First char determined by position.
    """
    FALLBACK_HEADER = 16

    def __init__(self, flash, g22_addr, g22_end, names=None):
        self.header_vids = []
        self.entries = []       # (label, var_id, uart_name)
        self.by_label = {}      # label -> var_id
        self.by_varid = {}      # var_id -> label
        self.header_count = self._infer_header_count(flash, g22_addr, g22_end, names)

        for i in range(self.header_count):
            vid = flash.u16(g22_addr + i * 2)
            if vid is not None:
                self.header_vids.append(vid)

        off = g22_addr + self.header_count * 2
        while off < g22_end:
            c0 = flash.u8(off)
            c1 = flash.u8(off + 1)
            vid = flash.u16(off + 2)
            if c0 is None or c1 is None or vid is None:
                break
            if c0 == 0 and c1 == 0 and vid == 0:
                break
            label = chr(c0) + chr(c1) if 0x20 <= c0 < 0x7F and 0x20 <= c1 < 0x7F else "??"
            uart = names.name(vid) if names else None
            self.entries.append((label, vid, uart))
            self.by_label[label] = vid
            self.by_varid[vid] = label
            off += 4

        print(f"[+] globals[22]: name table (flat), {len(self.header_vids)} header + {len(self.entries)} entries")

    def _infer_header_count(self, flash, g22_addr, g22_end, names):
        if not names:
            return self.FALLBACK_HEADER
        best_count = self.FALLBACK_HEADER
        best_hits = -1
        max_header = min(64, max(0, (g22_end - g22_addr) // 2))
        for header_count in range(max_header + 1):
            off = g22_addr + header_count * 2
            hits = 0
            while off + 4 <= g22_end:
                c0 = flash.u8(off)
                c1 = flash.u8(off + 1)
                vid = flash.u16(off + 2)
                name = names.name(vid) if vid is not None else None
                suffix = (chr(c0) + chr(c1)) if c0 is not None and c1 is not None else None
                if not name or len(name) != 3 or suffix != name[1:]:
                    break
                hits += 1
                off += 4
            if hits > best_hits:
                best_hits = hits
                best_count = header_count
        return best_count

    def dump(self, names=None):
        lines = [f"  {len(self.entries)} UART name entries:"]
        lines.append(f"  {'Suffix':>6}  {'VarID':>10}  {'UART':>5}")
        for label, vid, uart in self.entries:
            u = uart or ""
            lines.append(f"  {label:>5}  0x{vid:04X}      {u:>5}")
        return "\n".join(lines)

    def dump_header(self, names=None):
        lines = ["  Header metadata var_ids:"]
        for vid in self.header_vids:
            n = names.name(vid) if names else None
            ns = f":{n}" if n else ""
            lines.append(f"    0x{vid:04X}{ns}")
        return "\n".join(lines)

    def lookup(self, query):
        """Lookup by 2-char label or var_id. Returns list of (label, var_id, uart_name)."""
        if isinstance(query, int):
            return [(l, v, u) for l, v, u in self.entries if v == query]
        else:
            q = query.upper()
            return [(l, v, u) for l, v, u in self.entries if l == q]


class SignalChannel:
    """Signal channel descriptor. Used for BRP, CSL, STR, OXH, etc.

    Two formats depending on where count/name appear:

    BRP/CSL/STR format (globals[11]/[12]/[13]):
      +0x00: u32 config_a
      +0x04: u32 config_b
      +0x08: u8  field_count, char[3] name
      +0x0C: u32 reserved
      +0x10: u32 var_id_array_ptr
      +0x14: u32 config_array_ptr
      +0x18: u32 param (sample count?)
      +0x1C: u32 name_string_ptr

    OXH format (globals[28]):
      +0x00: u8  field_count, char[3] name
      +0x04: u32 reserved
      +0x08: u32 var_id_array_ptr
      +0x0C: u32 output_array_ptr
    """
    def __init__(self, flash, gidx, addr, names=None):
        self.gidx = gidx
        self.addr = addr
        self.name = "?"
        self.count = 0
        self.var_ids = []       # [(vid, uart_name)]
        self.field_names = []   # per-field signal names (e.g. "Flow.40ms")
        self.samples_per_rec = []  # per-field samples per EDF data record
        self.param = None
        self.format = None      # 'extended', 'compact', or 'oxh'

        # Try OXH format: count+name at +0x00, array ptr at +0x08
        name_00 = flash.blob(addr + 1, 3)
        count_00 = flash.u8(addr)

        # Try BRP format: count+name at +0x08, array ptr at +0x10
        name_08 = flash.blob(addr + 0x09, 3)
        count_08 = flash.u8(addr + 0x08)

        self.header_size = 0

        if name_08 and all(0x41 <= b <= 0x5A for b in name_08) and count_08 and 0 < count_08 < 200:
            self.name = name_08.decode('ascii')
            self.count = count_08
            arr_ptr = flash.u32(addr + 0x10)
            # Samples-per-record array at +0x14
            spr_ptr = flash.u32(addr + 0x14)
            if spr_ptr and flash.is_flash_ptr(spr_ptr):
                for i in range(self.count):
                    v = flash.u16(spr_ptr + i * 2)
                    self.samples_per_rec.append(v if v is not None else 0)
            # Check if extended format: +0x1C has a valid flash pointer (name string array)
            names_ptr = flash.u32(addr + 0x1C)
            if names_ptr and flash.is_flash_ptr(names_ptr):
                self.format = 'extended'
                self.header_size = 0x20
                self.param = flash.u32(addr + 0x18)
                for i in range(self.count):
                    sp = flash.u32(names_ptr + i * 4)
                    if sp and flash.is_flash_ptr(sp):
                        s = flash.cstr(sp)
                        self.field_names.append(s.decode('ascii', errors='replace') if s else None)
                    else:
                        self.field_names.append(None)
            else:
                self.format = 'compact'
                self.header_size = 0x18
        elif name_00 and all(0x41 <= b <= 0x5A for b in name_00) and count_00 and 0 < count_00 < 200:
            self.name = name_00.decode('ascii')
            self.count = count_00
            arr_ptr = flash.u32(addr + 0x08)
            # Check for second pointer at +0x0C — if valid flash ptr, stride is 0x14
            ptr2 = flash.u32(addr + 0x0C)
            if ptr2 and flash.is_flash_ptr(ptr2):
                self.format = 'oxh_ext'
                self.header_size = 0x14
            else:
                self.format = 'oxh'
                self.header_size = 0x10
        else:
            return

        if arr_ptr and flash.is_flash_ptr(arr_ptr):
            for i in range(self.count):
                vid = flash.u16(arr_ptr + i * 2)
                if vid is not None:
                    self.var_ids.append((vid, names.name(vid) if names else None))

        print(f"[+] globals[{gidx}]: {self.name} ({self.count} fields)")

    def dump(self):
        lines = [f"  {self.name} ({self.count} fields) @ 0x{self.addr:08X}:"]
        for i, (vid, uart) in enumerate(self.var_ids):
            u = f":{uart}" if uart else ""
            fn = f"  \"{self.field_names[i]}\"" if i < len(self.field_names) and self.field_names[i] else ""
            spr = ""
            if i < len(self.samples_per_rec):
                n = self.samples_per_rec[i]
                # Assume 60s record duration for rate calculation
                rate = n / 60.0 if n > 1 else 0
                spr = f"  [{n} samp" + (f", {rate:.1f} Hz" if rate > 0 else "") + "]"
            lines.append(f"    0x{vid:04X}{u}{fn}{spr}")
        return "\n".join(lines)


class SignalGroup:
    """Parse NPD or NPA signal group from globals[14] or globals[15].

    NPD (globals[14], 32 bytes):
      +0x00: u16 flags, u16 id
      +0x04: u32 param
      +0x08: u32 threshold
      +0x0C: u32 session_config
      +0x10: u8  signal_count, char[3] group_name
      +0x14: u32 reserved
      +0x18: u32 var_id_array_ptr
      +0x1C: u16 linked_var_id

    NPA (globals[15], 24+ bytes):
      +0x00: u16 flags, u16 id
      +0x04: u16 sample_rate?, u16 param
      +0x08: u8  signal_count, char[3] group_name
      +0x0C: u32 reserved
      +0x10: u32 var_id_array_ptr
      +0x14: u16 linked_var_id
    """
    def __init__(self, flash, addr, names=None):
        self.addr = addr
        self.signals = []
        self.name = "?"
        self.linked_vid = None

        # Try NPD format first (name at +0x10)
        count_10 = flash.u8(addr + 0x10)
        name_10 = flash.blob(addr + 0x11, 3)

        # Try NPA format (name at +0x08)
        count_08 = flash.u8(addr + 0x08)
        name_08 = flash.blob(addr + 0x09, 3)

        if name_10 and all(0x41 <= b <= 0x5A for b in name_10):
            # NPD format
            self.name = name_10.decode('ascii')
            count = count_10
            arr_ptr = flash.u32(addr + 0x18)
            self.linked_vid = flash.u16(addr + 0x1C)
        elif name_08 and all(0x41 <= b <= 0x5A for b in name_08):
            # NPA format
            self.name = name_08.decode('ascii')
            count = count_08
            arr_ptr = flash.u32(addr + 0x10)
            self.linked_vid = flash.u16(addr + 0x14)
        else:
            return

        if arr_ptr and flash.is_flash_ptr(arr_ptr):
            for i in range(count):
                vid = flash.u16(arr_ptr + i * 2)
                if vid is not None:
                    uart = names.name(vid) if names else None
                    self.signals.append((vid, uart))

    def dump(self):
        linked = f"0x{self.linked_vid:04X}" if self.linked_vid else "?"
        lines = [f"  {self.name} ({len(self.signals)} signals, linked={linked}):"]
        for vid, uart in self.signals:
            n = f":{uart}" if uart else ""
            lines.append(f"    0x{vid:04X}{n}")
        return "\n".join(lines)


class TimerScaleTable:
    """Parse globals[1] -- Timer/sampling resolution table.

    14 entries of 16 bytes each:
      +0x00: u16  level (scale level 0-6, 10)
      +0x02: u16  ticks (ticks per unit)
      +0x04: u16  multiplier
      +0x06: u16  pad (0)
      +0x08: f64  period_seconds
    """
    STRIDE = 16

    def __init__(self, flash, addr, end_addr):
        self.addr = addr
        self.entries = []
        count = (end_addr - addr) // self.STRIDE
        for i in range(count):
            ea = addr + i * self.STRIDE
            level = flash.u16(ea)
            ticks = flash.u16(ea + 2)
            mult = flash.u16(ea + 4)
            o = flash._o(ea + 8)
            period = struct.unpack_from('<d', flash.data, o)[0] if o is not None else 0.0
            self.entries.append(dict(idx=i, level=level, ticks=ticks,
                                     multiplier=mult, period=period))

    def dump(self):
        lines = [f"  {len(self.entries)} entries (stride {self.STRIDE}):"]
        lines.append(f"  {'idx':>4s}  {'level':>5s}  {'ticks':>5s}  {'mult':>4s}  {'period':>12s}")
        for e in self.entries:
            p = e['period']
            if p >= 3600:
                ps = f"{p:.0f}s ({p/3600:.1f}h)"
            elif p >= 60:
                ps = f"{p:.0f}s ({p/60:.0f}m)"
            elif p >= 1:
                ps = f"{p:.0f}s"
            else:
                ps = f"{p*1000:.0f}ms"
            lines.append(f"  [{e['idx']:2d}]  {e['level']:5d}  {e['ticks']:5d}  {e['multiplier']:4d}  {ps:>12s}")
        return "\n".join(lines)


class ModeTable:
    """Parse globals[24] -- Setting-to-mode membership table.

    globals[24] = pointer to table data
    globals[25] = entry count (49 on AirSense, not a flash pointer)

    Each entry:
      +0x00: u16      var_id (setting variable)
      +0x02: u8[]     mode_flags (0x00 or 0x01, one per MOP option)
    """
    FALLBACK_NUM_FLAGS = 12

    def __init__(self, flash, addr, count, names=None, num_flags=None):
        self.addr = addr
        self.count = count
        self.num_flags = num_flags or self.FALLBACK_NUM_FLAGS
        self.stride = 2 + self.num_flags
        self.entries = []

        for i in range(count):
            ea = addr + i * self.stride
            vid = flash.u16(ea)
            if vid is None:
                break
            flags = []
            for f in range(self.num_flags):
                b = flash.u8(ea + 2 + f)
                flags.append(b if b is not None else 0)
            uart = names.name(vid) if names else None
            self.entries.append(dict(idx=i, var_id=vid, uart=uart, flags=flags))

    def dump(self):
        hdr = "     var_id     " + " ".join(f"{i:>2d}" for i in range(self.num_flags))
        lines = [f"  {len(self.entries)} entries (stride {self.stride}):", f"  {hdr}"]
        for e in self.entries:
            n = f":{e['uart']}" if e['uart'] else ""
            fstr = "  ".join(str(f) for f in e['flags'])
            lines.append(f"  [{e['idx']:2d}] 0x{e['var_id']:04X}{n:>4s}   {fstr}")
        return "\n".join(lines)


class PDLTable:
    """Parse globals[20] -- PDL (Patient Data Log) definition.

    Structure at globals[20]:
      +0x00: char[4]  name ("PDL\\0")
      +0x04: u32      var_id_array_ptr (-> array of u16 var_ids)
      +0x08: u32      var_id_count
      +0x0C: rule entries (also referenced by g[21])

    Each rule entry (16 bytes):
      +0x00: u16      var_id_a
      +0x02: u16      var_id_b
      +0x04: u32      flags (0x00000000..0x00030000)
      +0x08: u32      param_a (0xFFFFFFFF = unused)
      +0x0C: u32      param_b (0xFFFFFFFF = unused)

    globals[21] is a {u32 count, u32 ptr} that points into g[20]+0x0C,
    providing a separate access path to the same rule entries.
    """
    def __init__(self, flash, addr, rules_ref=None, names=None):
        self.addr = addr
        self.var_ids = []      # list of (var_id, uart_name)
        self.rules = []        # list of dicts
        self.name = "?"

        # Header
        raw_name = flash.blob(addr, 4)
        if raw_name:
            self.name = raw_name.rstrip(b'\x00').decode('ascii', errors='replace')
        arr_ptr = flash.u32(addr + 0x04)
        count = flash.u32(addr + 0x08)

        # Var_id array
        if arr_ptr and flash.is_flash_ptr(arr_ptr) and count and count < 200:
            for i in range(count):
                vid = flash.u16(arr_ptr + i * 2)
                if vid is not None:
                    uart = names.name(vid) if names else None
                    self.var_ids.append((vid, uart))

        rule_base = addr + 0x0C
        rule_count = None
        if rules_ref and flash.is_flash_ptr(rules_ref):
            count_from_g21 = flash.u32(rules_ref)
            ptr_from_g21 = flash.u32(rules_ref + 4)
            if count_from_g21 is not None and count_from_g21 < 200:
                rule_count = count_from_g21
            if ptr_from_g21 and flash.is_flash_ptr(ptr_from_g21):
                rule_base = ptr_from_g21
        if rule_count is None:
            rule_count = 0
            while rule_count < 64:
                ea = rule_base + rule_count * 16
                if flash.u16(ea) is None:
                    break
                rule_count += 1

        for i in range(rule_count):
            ea = rule_base + i * 16
            vid_a = flash.u16(ea + 0x00)
            vid_b = flash.u16(ea + 0x02)
            flags = flash.u32(ea + 0x04)
            param_a = flash.u32(ea + 0x08)
            param_b = flash.u32(ea + 0x0C)
            if vid_a is None:
                break
            ua = names.name(vid_a) if names else None
            ub = names.name(vid_b) if names else None
            self.rules.append(dict(
                idx=i, vid_a=vid_a, vid_b=vid_b, name_a=ua, name_b=ub,
                flags=flags, param_a=param_a, param_b=param_b))

    def dump(self):
        lines = [f"  {self.name} ({len(self.var_ids)} vars, {len(self.rules)} rules)"]
        lines.append(f"  Var_ids:")
        for i, (vid, uart) in enumerate(self.var_ids):
            n = f":{uart}" if uart else ""
            lines.append(f"    [{i:2d}] 0x{vid:04X}{n}")
        lines.append(f"  Rules:")
        for r in self.rules:
            na = f":{r['name_a']}" if r['name_a'] else ""
            nb = f":{r['name_b']}" if r['name_b'] else ""
            fg = (r['flags'] >> 8) & 0xFF
            pa = f"0x{r['param_a']:08X}" if r['param_a'] != 0xFFFFFFFF else "--"
            pb = f"0x{r['param_b']:08X}" if r['param_b'] != 0xFFFFFFFF else "--"
            lines.append(f"    [{r['idx']:2d}] a=0x{r['vid_a']:04X}{na}  b=0x{r['vid_b']:04X}{nb}  "
                         f"type={fg}  param_a={pa}  param_b={pb}")
        return "\n".join(lines)

    def dump_rules(self):
        """Dump only the rule entries (for g21 command)."""
        lines = [f"  {len(self.rules)} rule entries (stride 16, from {self.name}+0x0C):"]
        for r in self.rules:
            na = f":{r['name_a']}" if r['name_a'] else ""
            nb = f":{r['name_b']}" if r['name_b'] else ""
            fg = (r['flags'] >> 8) & 0xFF
            pa = f"0x{r['param_a']:08X}" if r['param_a'] != 0xFFFFFFFF else "--"
            pb = f"0x{r['param_b']:08X}" if r['param_b'] != 0xFFFFFFFF else "--"
            lines.append(f"    [{r['idx']:2d}] a=0x{r['vid_a']:04X}{na}  b=0x{r['vid_b']:04X}{nb}  "
                         f"type={fg}  param_a={pa}  param_b={pb}")
        return "\n".join(lines)


class DB:
    def __init__(self, flash, ta, g2=None, raw=None,
                 globals_addr=None, globals_values=None):
        self.fl = flash
        self.g2_addr = g2
        self.raw_strings = raw
        self.globals_addr = globals_addr
        if globals_values is None:
            raise ValueError("globals[] array not found")
        self.globals_values = {
            idx: value for idx, value in globals_values.items()
            if value is not None
        }
        self.tables = {}
        self.by_varid = {}
        self.strtab = None
        self.names = None      # NameLookup (globals[23])
        self.streams = None    # StreamTable (globals[19])
        self.npd = None        # SignalGroup (globals[14])
        self.npa = None        # SignalGroup (globals[15])
        self.device = None     # DeviceIdentity (globals[0])
        self.vargroups = None  # VariableGroups (globals[16])
        self.desc17 = None     # DescriptorTable (globals[17])
        self.desc18 = None     # DescriptorTable (globals[18])
        self.nametab = None    # NameTableFlat (globals[22], flat copy of g[23])
        self.pdl = None        # PDLTable (globals[20], patient data log)
        self.modes = None      # ModeTable (globals[24], setting-to-mode flags)
        self.timers = None     # TimerScaleTable (globals[1])
        self.channels = {}     # gidx -> SignalChannel (globals[11,12,13,28])
        self.table_bases = {}  # table_num -> base address
        self.id_bases = {}     # table_num -> first var_id, derived from globals[23]
        self.g5_ptr = None
        self.g5_count = 0
        self.g5_base_idx = None
        self.g5_end_idx = None
        self.g5_alias_count = 0
        self.g4_subrange_base_idx = None

        g23 = ta.get('names')
        if g23:
            self.names = NameLookup(flash, g23)
        self._load_var_tables(flash, ta)

        # G2 gives string slot count; LAN gives the labels/order for those slots.
        n = infer_language_count_from_g2(flash, g2) if g2 else None
        lan_n, labels, ids = detect_languages(
            flash, ta, self._table_index_for_name('LAN', 8, fallback=5))
        if n is not None and n != lan_n:
            raise ValueError(
                f"language count mismatch: globals[2] has {n} slots, "
                f"LAN mask has {lan_n} ({', '.join(labels)})")
        self.num_languages = n if n is not None else lan_n
        self.lang_labels = labels
        self.lang_ids = ids
        print(f"[+] Languages: {self.num_languages} locales [{', '.join(labels)}]")

        if g2:
            self.strtab = StringTable(flash, g2, self.num_languages, raw)
            raw_s = f"0x{raw:08X}" if raw else "auto"
            print(f"[+] Strings: globals[2]=0x{g2:08X}, "
                  f"raw={raw_s}, max_id={self.strtab.max_id}")

        # Load timer scale table (globals[1], bounded by globals[2])
        g1 = ta.get('timers')
        if g1 and g2:
            self.timers = TimerScaleTable(flash, g1, g2)
            if self.timers.entries:
                print(f"[+] globals[1]: timer scale table ({len(self.timers.entries)} entries)")

        # Load device identity (globals[0])
        g0 = ta.get('device')
        if g0:
            self.device = DeviceIdentity(flash, g0)

        # Load variable groups (globals[16])
        g16 = ta.get('vargroups')
        g17 = ta.get('desc17')
        if g16:
            self.vargroups = VariableGroups(flash, g16, g17, self.names)

        # Load descriptor tables (globals[17], [18])
        g18 = ta.get('desc18')
        g19 = ta.get('streams')
        if g17 and g18:
            self.desc17 = DescriptorTable(flash, 17, g17, g18, self.names)
        if g18 and g19:
            self.desc18 = DescriptorTable(flash, 18, g18, g19, self.names)

        # Load UART name table flat (globals[22], ends at globals[23])
        g22 = ta.get('signals')
        g22_end = ta.get('names')  # g[23] is the end boundary
        if g22 and g22_end:
            self.nametab = NameTableFlat(flash, g22, g22_end, self.names)

        # Load stream table (globals[19])
        g19 = ta.get('streams')
        g20 = ta.get('pdl')
        if g19:
            self.streams = StreamTable(flash, g19, g20, self.names)

        # Load signal groups (globals[14]/[15])
        g14 = ta.get('npd')
        if g14:
            self.npd = SignalGroup(flash, g14, self.names)
            if self.npd.signals:
                print(f"[+] globals[14]: {self.npd.name} ({len(self.npd.signals)} signals)")
        g15 = ta.get('npa')
        if g15:
            self.npa = SignalGroup(flash, g15, self.names)
            if self.npa.signals:
                print(f"[+] globals[15]: {self.npa.name} ({len(self.npa.signals)} signals)")

        # Load PDL (globals[20], also covers g[21] rules)
        if g20:
            self.pdl = PDLTable(flash, g20, ta.get('pdl_rules'), self.names)
            if self.pdl.var_ids:
                print(f"[+] globals[20]: {self.pdl.name} ({len(self.pdl.var_ids)} vars, {len(self.pdl.rules)} rules)")

        # Load mode table (globals[24], count from globals[25])
        g24 = ta.get('modes')
        g25 = ta.get('modes_count')
        if g24 and g25:
            self.modes = ModeTable(flash, g24, g25, self.names, self._mode_count())
            if self.modes.entries:
                print(f"[+] globals[24]: mode table ({len(self.modes.entries)} settings x {self.modes.num_flags} modes)")

        # Load signal channels (globals[11,12,13,28])
        for key, gidx in [('brp', 11), ('csl', 12), ('str_ch', 13),
                          ('tce', 26), ('apn', 27), ('oxh', 28)]:
            addr = ta.get(key)
            if not addr:
                continue
            # Some globals entries contain multiple channels packed together
            # Scan for channel headers until we hit a non-header
            scan_end = addr + 0x500  # reasonable scan limit
            off = addr
            while off < scan_end:
                ch = SignalChannel(flash, gidx, off, self.names)
                if not ch.var_ids:
                    break
                self.channels[ch.name] = ch
                off += ch.header_size

        g5 = ta.get('globals5')
        if g5:
            self._load_g5(g5)

        print(f"[+] Total: {len(self.by_varid)} variables")

    def _load_var_tables(self, flash, ta):
        next_id_base = None
        for tnum in (3, 4, 6, 8, 9, 10):
            base = ta.get(f"table{tnum}")
            if not base:
                continue
            self.table_bases[tnum] = base
            info = TABLES[tnum]
            cls = ENTRY_CLS[tnum]
            count = self._table_count(tnum, base, info['stride'])
            id_base = None
            if tnum != 10:
                id_base = self._infer_id_base(tnum, count, next_id_base)
                self.id_bases[tnum] = id_base
                next_id_base = id_base + count
            entries = []
            for i in range(count):
                addr = base + i * info['stride']
                if tnum == 10:
                    entries.append(cls(flash, addr, i))
                else:
                    entries.append(cls(flash, addr, i, id_base))
            self.tables[tnum] = entries
            if id_base is not None:
                for e in entries:
                    self.by_varid[e.var_id] = e
            print(f"[+] globals[{tnum}]: {len(entries)} entries @ 0x{base:08X}")

        if 4 in self.tables:
            self.g4_subrange_base_idx = self._infer_g4_subrange_base()

    def _infer_g4_subrange_base(self):
        prev_had_b7 = False
        for entry in self.tables[4]:
            has_b7 = bool(entry.flags & 0x0080)
            if prev_had_b7 and not has_b7:
                return entry.idx
            prev_had_b7 = has_b7
        return None

    def _table_index_for_name(self, name, table_num, fallback=None):
        if self.names:
            vid = self.names.var_id(name)
            base = self.id_bases.get(table_num)
            entries = self.tables.get(table_num)
            if vid is not None and base is not None and entries:
                idx = vid - base
                if 0 <= idx < len(entries):
                    return idx
        return fallback

    def _entry_for_name(self, name):
        if not self.names:
            return None
        vid = self.names.var_id(name)
        return self.get(vid) if vid is not None else None

    def _mode_count(self):
        mop = self._entry_for_name('MOP')
        if isinstance(mop, Entry8) and mop.num_options:
            return mop.num_options
        return ModeTable.FALLBACK_NUM_FLAGS

    def _next_global_ptr_after(self, base):
        candidates = [
            value for value in self.globals_values.values()
            if self.fl.is_flash_ptr(value) and value > base
        ]
        return min(candidates) if candidates else None

    def _table_count(self, tnum, base, stride):
        if tnum == 10:
            return self._table10_count(base, stride)
        end = self._next_global_ptr_after(base)
        if end is None:
            raise ValueError(f"cannot infer globals[{tnum}] count")
        size = end - base
        if size <= 0 or size % stride:
            raise ValueError(
                f"globals[{tnum}] size 0x{size:X} is not aligned to stride 0x{stride:X}")
        return size // stride

    def _table10_count(self, base, stride):
        count = 0
        for i in range(64):
            addr = base + i * stride
            if not self._valid_table10_entry(addr):
                break
            count += 1
        if count == 0:
            raise ValueError("cannot infer globals[10] count")
        return count

    def _valid_table10_entry(self, addr):
        flags = self.fl.u16(addr)
        callback = self.fl.u8(addr + 0x02)
        default = self.fl.s32(addr + 0x08)
        max_value = self.fl.s32(addr + 0x0C)
        min_value = self.fl.s32(addr + 0x10)
        decimal_places = self.fl.u8(addr + 0x14)
        scale = self.fl.s16(addr + 0x16)
        step = self.fl.s16(addr + 0x18)
        if None in (flags, callback, default, max_value, min_value,
                    decimal_places, scale, step):
            return False
        if flags & ~0x00FF:
            return False
        if callback > 64:
            return False
        if max_value < min_value:
            return False
        if decimal_places > 6:
            return False
        if scale == 0 or abs(scale) > 10000:
            return False
        if step <= 0 or abs(step) > 10000:
            return False
        return True

    def _load_g5(self, addr):
        end = self._next_global_ptr_after(addr)
        if end is None:
            raise ValueError("cannot infer globals[5] size")
        size = end - addr
        if size <= 0 or size % 4:
            raise ValueError(f"globals[5] size 0x{size:X} is not aligned")
        if 4 not in self.tables:
            raise ValueError("globals[4] not loaded; cannot map globals[5]")

        # The final B8-tagged g[4] records are a shared handler tail; they reuse
        # the first g[5] records rather than extending the physical g[5] window.
        alias_count = 0
        for entry in reversed(self.tables[4]):
            if entry.flags & 0x0100:
                alias_count += 1
            else:
                break

        count = size // 4
        base_idx = len(self.tables[4]) - count - alias_count
        if base_idx < 0:
            raise ValueError("globals[5] is larger than the globals[4] tail window")

        self.g5_ptr = addr
        self.g5_count = count
        self.g5_base_idx = base_idx
        self.g5_end_idx = base_idx + count
        self.g5_alias_count = alias_count
        print(f"[+] globals[5]: display-name table @ 0x{addr:08X} "
              f"({count} entries, idx 0x{base_idx:03X}..0x{self.g5_end_idx-1:03X})")

    def _infer_id_base(self, tnum, count, expected_base):
        if not self.names:
            raise ValueError(f"globals[23] not loaded; cannot infer globals[{tnum}] var_id base")
        ids = set(self.names.by_varid)
        if expected_base is not None:
            if self._has_id_range(ids, expected_base, count):
                return expected_base
            raise ValueError(
                f"globals[{tnum}] var_id range 0x{expected_base:04X}"
                f"..0x{expected_base + count - 1:04X} missing from globals[23]")

        for candidate in sorted(ids):
            if candidate - 1 in ids:
                continue
            if self._has_id_range(ids, candidate, count):
                return candidate
        raise ValueError(f"cannot infer globals[{tnum}] var_id base from globals[23]")

    @staticmethod
    def _has_id_range(ids, start, count):
        return all(start + i in ids for i in range(count))

    def uart_name(self, var_id):
        """Return 3-letter UART name for var_id, or None."""
        return self.names.name(var_id) if self.names else None

    def get(self, vid):
        return self.by_varid.get(vid)

    def g4_by_idx(self, idx):
        entries = self.tables.get(4)
        if entries and 0 <= idx < len(entries):
            entry = entries[idx]
            if isinstance(entry, Entry4):
                return entry
        return None

    def string(self, sid, lang=0):
        return self.strtab.get(sid, lang) if self.strtab else None

    def strings_all(self, sid):
        return self.strtab.get_all(sid) if self.strtab else [None] * self.num_languages

    def g5_lookup(self, t4_idx):
        """Look up globals[5] display-name record for a [4] table index.
        Returns (str_id_a, str_id_b) or None if not in range or g5 not loaded."""
        if self.g5_ptr is None or self.g5_base_idx is None:
            return None
        if not (self.g5_base_idx <= t4_idx < self.g5_end_idx):
            return None
        offset = t4_idx - self.g5_base_idx
        addr = self.g5_ptr + offset * 4
        a = self.fl.u16(addr)
        b = self.fl.u16(addr + 2)
        return (a, b)

    def g5_visible(self, t4_idx):
        """Check if a [4] entry is potentially visible via globals[5].
        Returns True if not in g5 valid range (no override),
        or if at least one string != 0xDE (visible in some context)."""
        rec = self.g5_lookup(t4_idx)
        if rec is None:
            return True  # not in g5 range -> no g5 restriction
        return rec[0] != 0xDE or rec[1] != 0xDE

    def chain(self, entry):
        result = [entry]
        if not isinstance(entry, Entry8):
            return result
        nxt = entry.linked_var_idx
        seen = set()
        while nxt != 0x7FFF and nxt >= 0 and nxt not in seen and len(result) < 10:
            seen.add(nxt)
            e = self.g4_by_idx(nxt)
            if not e or not isinstance(e, Entry4):
                result.append(f"[4] idx=0x{nxt:04X} (not loaded)")
                break
            result.append(e)
            nxt = e.next_var_idx
        return result



def parse_numeric_arg(value, what="number"):
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{what} must be decimal or explicit hex") from exc


def resolve_var_arg(db, ident):
    try:
        return int(ident, 0)
    except ValueError:
        pass
    if db.names:
        vid = db.names.var_id(ident)
        if vid is not None:
            return vid
    raise ValueError(f"could not resolve {ident!r} to a var_id")


def _print_var_detail(db, ident, verbose=False):
    vid = resolve_var_arg(db, ident)
    e = db.get(vid)
    if not e:
        print(f"  var 0x{vid:04X} not found")
        return
    print(e.detail(db) if verbose else f"  {e.oneline(db)}")


def _print_table(db, tnum, idx=None, to=None):
    if tnum not in db.tables:
        print(f"  globals[{tnum}] not loaded")
        return
    n = len(db.tables[tnum])
    if idx is None:
        for i in range(n):
            print(f"  {db.tables[tnum][i].oneline(db)}")
        return

    idx = parse_numeric_arg(idx, "index")
    to = parse_numeric_arg(to, "end index") if to is not None else None
    if to is not None:
        for i in range(idx, min(to, n)):
            print(f"  {db.tables[tnum][i].oneline(db)}")
    elif 0 <= idx < n:
        print(db.tables[tnum][idx].detail(db))
    else:
        e = db.get(idx)
        if e and e.TABLE == tnum:
            print(e.detail(db))
            return
        id_hint = ""
        id_base = db.id_bases.get(tnum)
        if id_base is not None:
            id_hint = f"  var_ids: 0x{id_base:04X}..0x{id_base+n-1:04X}"
        print(f"  idx 0x{idx:X} out of range (0..0x{n-1:X}){id_hint}")


def _print_g2_info(db):
    if not db.strtab:
        print("  globals[2] not loaded")
        return
    st = db.strtab
    print("  String descriptor table:")
    print(f"    globals[2]  = 0x{st.g2:08X}")
    print(f"    raw base    = 0x{st.raw:08X}")
    print(f"    max_id      = {st.max_id}")
    print(f"    languages   = {db.num_languages} ({', '.join(db.lang_labels)})")
    print("  Use 'strid <id> [lang]' to look up strings.")


def _print_g5(db):
    if db.g5_ptr is None:
        print("  globals[5] not loaded")
        return
    print("  globals[5] display-name override table:")
    print(f"  addr=0x{db.g5_ptr:08X}  entries={db.g5_count} "
          f"(idx 0x{db.g5_base_idx:03X}..0x{db.g5_end_idx-1:03X})")
    for idx in range(db.g5_base_idx, db.g5_end_idx):
        rec = db.g5_lookup(idx)
        if rec is None:
            continue
        a, b = rec
        vid = idx + db.id_bases[4]
        sa = db.string(a) if db.strtab and a != 0xDE else None
        sb = db.string(b) if db.strtab and b != 0xDE else None
        vis = "HIDDEN" if (a == 0xDE and b == 0xDE) else "vis"
        la = f'"{sa}"' if sa else ("--" if a == 0xDE else f"0x{a:04X}")
        lb = f'"{sb}"' if sb else ("--" if b == 0xDE else f"0x{b:04X}")
        off = idx - db.g5_base_idx
        shared = ""
        alt_idx = db.g5_end_idx + off
        if off < db.g5_alias_count:
            shared = f"  (shared w/ idx 0x{alt_idx:03X})"
        print(f"  [4] idx=0x{idx:03X} var=0x{vid:04X}  off={off:+3d}  "
              f"a={la:>24s}  b={lb:>24s}  [{vis}]{shared}")


def _print_strinfo(db, sid):
    if not db.strtab:
        print("  string table not loaded")
        return
    st = db.strtab
    print(f"  globals[2] base  = 0x{st.g2:08X}")
    print(f"  raw string base  = 0x{st.raw:08X}")
    print(f"  max string ID    = {st.max_id}")
    rec_addr = st.g2 + sid * 8
    field0 = db.fl.u32(rec_addr)
    la = db.fl.u32(rec_addr + 4)
    print(f"  record[{sid}] @ 0x{rec_addr:08X}:")
    print(f"    field0 = 0x{field0:08X} ({field0})")
    print(f"    locale_arr_ptr = 0x{la:08X}")
    if la and db.fl.is_flash_ptr(la):
        for l in range(db.num_languages):
            ri = db.fl.u16(la + l * 2)
            sp = db.fl.u32(st.raw + ri * 4) if ri is not None else None
            if sp and db.fl.is_flash_ptr(sp):
                s = db.fl.cstr(sp).decode('utf-8', errors='replace')
                print(f"    [{db.lang_labels[l]}] raw_idx={ri} "
                      f"str_ptr=0x{sp:08X} -> \"{s}\"")
            else:
                print(f"    [{db.lang_labels[l]}] raw_idx={ri} -> ?")


def _search_strings(db, query):
    needle = query.lower()
    hits = []
    if 8 in db.tables:
        for e in db.tables[8]:
            if e.name_str_id and e.name_str_id not in (0xFFFF, 0xDE):
                s = db.string(e.name_str_id)
                if s and needle in s.lower():
                    hits.append((e, s))
                    continue
            if e.has_strings():
                for i in range(max(1, e.num_options)):
                    s = db.string(e.base_str_id + i)
                    if s and needle in s.lower():
                        hits.append((e, s))
                        break
    for tnum in (4, 9, 10):
        if tnum not in db.tables:
            continue
        for e in db.tables[tnum]:
            bad_ids = (0xFFFF, 0xDE, 0) if tnum == 10 else (0xFFFF, 0xDE)
            if getattr(e, "name_str_id", 0) not in bad_ids:
                s = db.string(e.name_str_id)
                if s and needle in s.lower():
                    hits.append((e, s))
                    continue
            if isinstance(e, (Entry4, Entry10)) and getattr(e, "units_str_id", 0) not in bad_ids:
                s = db.string(e.units_str_id)
                if s and needle in s.lower():
                    hits.append((e, s))
    for entry, s in hits:
        print(f"  [{entry.TABLE}] var=0x{entry.var_id:04X} "
              f'idx=0x{entry.idx:03X}: "{s}"')
    if not hits:
        print(f'  no matches for "{query}"')


def _print_chain(db, ident):
    vid = resolve_var_arg(db, ident)
    e = db.get(vid)
    if not e or not isinstance(e, Entry8):
        print("  not a [8] entry")
        return
    ch = db.chain(e)
    print(f"  Chain from 0x{vid:04X} ({len(ch)} nodes):")
    for i, ce in enumerate(ch):
        pipe = "+--" if i == len(ch) - 1 else "|--"
        if isinstance(ce, Entry8):
            st = ""
            if ce.has_strings():
                s = db.string(ce.base_str_id)
                if s:
                    st = f'  "{s}"'
            print(f"  {pipe} [8] 0x{ce.var_id:04X} "
                  f"dep={_g4_idx_ref(ce.linked_var_idx, db, none='none')}{st}")
        elif isinstance(ce, Entry4):
            u = ""
            if ce.units_str_id and ce.units_str_id != 0xFFFF:
                s = db.string(ce.units_str_id)
                if s:
                    u = f" [{s}]"
            print(f"  {pipe} [4] 0x{ce.var_id:04X} "
                  f"next={_g4_idx_ref(ce.next_var_idx, db, none='end')} "
                  f"{ce.range_str()}{u}")
        else:
            print(f"  {pipe} {ce}")


def _print_info(db):
    print("  Air10 CCX block navigator")
    print(f"  image       {len(db.fl.data)} bytes  "
          f"0x{db.fl.base:08X}..0x{db.fl.end:08X}")
    print(f"  languages   {db.num_languages} ({', '.join(db.lang_labels)})")
    if db.strtab:
        print(f"  strings     g2=0x{db.strtab.g2:08X} raw=0x{db.strtab.raw:08X}")
    for tnum in sorted(db.tables):
        base = db.table_bases.get(tnum)
        print(f"  globals[{tnum:<2}] {len(db.tables[tnum]):>4} entries @ 0x{base:08X}")
    extras = []
    for name, value in (
        ("g0 device", db.device),
        ("g1 timers", db.timers),
        ("g14 NPD", db.npd),
        ("g15 NPA", db.npa),
        ("g16 groups", db.vargroups),
        ("g19 streams", db.streams),
        ("g20 PDL", db.pdl),
        ("g22 flat names", db.nametab),
        ("g23 UART names", db.names),
        ("g24 modes", db.modes),
    ):
        if value:
            extras.append(name)
    if db.channels:
        extras.append(f"{len(db.channels)} signal channels")
    if extras:
        print("  loaded      " + ", ".join(extras))
    print(f"  variables   {len(db.by_varid)}")


def _print_globals(db):
    if db.globals_addr:
        print(f"  globals[] @ 0x{db.globals_addr:08X}")
    else:
        print("  globals[] values inferred from loaded globals entries")
    print("  idx  value       kind   description")
    for idx in sorted(db.globals_values):
        value = db.globals_values[idx]
        if value == 0:
            continue
        label = GLOBAL_LABELS.get(idx, "")
        if value == 0xFFFFFFFF:
            kind = "sentinel"
            shown = f"0x{value:08X}"
        elif idx == 25:
            kind = "count"
            shown = f"0x{value:08X} ({value})"
        elif db.fl.is_flash_ptr(value):
            kind = "ptr"
            shown = f"0x{value:08X}"
        else:
            kind = "value"
            shown = f"0x{value:08X} ({value})"
        print(f"  [{idx:2d}] {shown:<15} {kind:<5} {label}")
    if db.raw_strings:
        print(f"       raw strings 0x{db.raw_strings:08X}")


def add_command_parsers(subparsers):
    subparsers.add_parser("info", help="show firmware summary and loaded tables")
    p = subparsers.add_parser("globals", help="show globals[] map or decoded entries")
    p.add_argument("items", nargs="*", help="globals[] indices")

    p = subparsers.add_parser("var", help="show one variable descriptor")
    p.add_argument("ident", help="var_id or UART tag")

    p = subparsers.add_parser("channels", help="show signal channels")
    p.add_argument("name", nargs="?")

    p = subparsers.add_parser("mode", help="list vars mapped to one therapy mode")
    p.add_argument("mode", nargs="*", help="mode index or name")

    p = subparsers.add_parser("strid", help="lookup raw string id")
    p.add_argument("id")
    p.add_argument("lang", nargs="?")

    p = subparsers.add_parser("strinfo", help="show string table record internals")
    p.add_argument("id", nargs="?", default="0")

    p = subparsers.add_parser("search", help="search descriptor strings")
    p.add_argument("query", nargs="+")

    p = subparsers.add_parser("chain", help="walk [8] -> [4] dependency chain")
    p.add_argument("ident")

    p = subparsers.add_parser("dump-tsv", help="dump descriptor tables as TSV")
    p.add_argument("outfile", help="output path, or - for stdout")
    p.add_argument("--tables", default="3,4,6,8,9,10",
                   help="tables to dump (default: 3,4,6,8,9,10)")


def build_command_parser(prog="as10"):
    parser = argparse.ArgumentParser(prog=prog)
    subparsers = parser.add_subparsers(dest="command")
    add_command_parsers(subparsers)
    return parser


def build_main_parser():
    parser = argparse.ArgumentParser(
        description="ResMed AirSense 10 -- Descriptor Navigator")
    parser.add_argument("firmware", help="raw flash binary")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="start interactive descriptor shell")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show multiline variable details")
    parser.add_argument("--globals", type=lambda x: int(x, 0), default=None,
                        help="globals[] pointer array address in flash")
    subparsers = parser.add_subparsers(dest="command")
    add_command_parsers(subparsers)
    return parser


def _run_global(db, item):
    parts = item.split(":", 1)
    gidx = parse_numeric_arg(parts[0], "globals index")
    extra = parts[1].split(",") if len(parts) > 1 and parts[1] else []
    if gidx in (3, 4, 6, 8, 9, 10):
        if len(extra) > 2:
            raise ValueError(f"globals {gidx} takes at most: :idx[,to]")
        idx = extra[0] if extra else None
        to = extra[1] if len(extra) > 1 else None
        _print_table(db, gidx, idx, to)
    elif gidx == 0:
        print(db.device.dump() if db.device else "  globals[0] not loaded")
    elif gidx == 1:
        print(db.timers.dump() if db.timers else "  globals[1] not loaded")
    elif gidx == 2:
        _print_g2_info(db)
    elif gidx == 5:
        _print_g5(db)
    elif gidx == 14:
        print(db.npd.dump() if db.npd else "  globals[14] not loaded")
    elif gidx == 15:
        print(db.npa.dump() if db.npa else "  globals[15] not loaded")
    elif gidx == 16:
        if len(extra) > 1:
            raise ValueError("globals 16 takes at most: :group")
        name = extra[0] if extra else None
        print(db.vargroups.dump(name) if db.vargroups else "  globals[16] not loaded")
    elif gidx == 17:
        print(db.desc17.dump() if db.desc17 else "  globals[17] not loaded")
    elif gidx == 18:
        print(db.desc18.dump() if db.desc18 else "  globals[18] not loaded")
    elif gidx == 19:
        print(db.streams.dump() if db.streams else "  globals[19] not loaded")
    elif gidx == 20:
        print(db.pdl.dump() if db.pdl else "  globals[20] not loaded")
    elif gidx == 21:
        print(db.pdl.dump_rules() if db.pdl else "  globals[21] not loaded (shares data with g[20])")
    elif gidx == 22:
        if len(extra) > 1:
            raise ValueError("globals 22 takes at most: :query")
        _run_g22(db, extra[0] if extra else None)
    elif gidx == 23:
        if len(extra) > 1:
            raise ValueError("globals 23 takes at most: :query")
        _run_g23(db, extra[0] if extra else None)
    elif gidx == 24:
        print(db.modes.dump() if db.modes else "  globals[24] not loaded")
    elif gidx in (11, 12, 13, 26, 27, 28):
        if extra:
            raise ValueError(f"globals {gidx} takes no extra args")
        _run_channels(db, gidx, None)
    else:
        raise ValueError(f"globals[{gidx}] is not decoded")


def run_command(db, args):
    command = args.command or "info"
    if command == "info":
        _print_info(db)
    elif command == "globals":
        if args.items:
            for i, item in enumerate(args.items):
                if i:
                    print()
                _run_global(db, item)
        else:
            _print_globals(db)
    elif command == "var":
        verbose = getattr(args, "verbose", getattr(db, "verbose", False))
        _print_var_detail(db, args.ident, verbose)
    elif command == "channels":
        _run_channels(db, None, args.name)
    elif command == "mode":
        _run_mode(db, " ".join(args.mode) if args.mode else None)
    elif command == "strid":
        sid = parse_numeric_arg(args.id, "string id")
        lang = parse_numeric_arg(args.lang, "language") if args.lang is not None else None
        if not db.strtab:
            print("  string table not loaded")
        elif lang is not None:
            print(f"  {db.string(sid, lang)}")
        else:
            for lb, s in zip(db.lang_labels, db.strings_all(sid)):
                print(f"  {lb}: {s}")
    elif command == "strinfo":
        _print_strinfo(db, parse_numeric_arg(args.id, "string id"))
    elif command == "search":
        _search_strings(db, " ".join(args.query))
    elif command == "chain":
        _print_chain(db, args.ident)
    elif command == "dump-tsv":
        tables = [int(t.strip()) for t in args.tables.split(",")]
        outfile = None if args.outfile == "-" else args.outfile
        dump_tsv(db, tables, outfile)
    else:
        raise ValueError(f"unknown command: {command}")


def _run_g22(db, query):
    if not db.nametab:
        print("  globals[22] not loaded")
        return
    if query is None:
        print(db.nametab.dump())
    elif query.lower() == 'header':
        print(db.nametab.dump_header(db.names))
    else:
        try:
            results = db.nametab.lookup(int(query, 0))
        except ValueError:
            results = db.nametab.lookup(query)
        if results:
            for label, vid, uart in results:
                u = f":{uart}" if uart else ""
                print(f"  '{label}' -> 0x{vid:04X}{u}")
        else:
            print(f"  '{query}' not found")


def _run_g23(db, query):
    if not db.names:
        print("  globals[23] not loaded")
        return
    if query is None:
        print(f"  {len(db.names.by_name)} UART names loaded")
        print("  usage: g23 <var_id> or g23 <ABC>")
        return
    try:
        vid = int(query, 0)
        name = db.uart_name(vid)
        print(f"  0x{vid:04X} = {name}" if name else f"  0x{vid:04X}: no UART name")
    except ValueError:
        vid = db.names.var_id(query)
        print(f"  {query.upper()} = 0x{vid:04X}" if vid is not None else f"  {query.upper()}: not found")


def _mode_labels(db):
    count = db.modes.num_flags if db.modes else ModeTable.FALLBACK_NUM_FLAGS
    labels = [str(i) for i in range(count)]
    mop_vid = db.names.var_id("MOP") if db.names else None
    mop = db.get(mop_vid) if mop_vid is not None else None
    if isinstance(mop, Entry8):
        for i, label in enumerate(mop.option_strings(db)[:count]):
            if label:
                labels[i] = label
    return labels


def _mode_key(value):
    return "".join(c.lower() for c in value if c.isalnum())


def _resolve_mode_index(db, mode):
    labels = _mode_labels(db)
    try:
        idx = int(mode, 0)
        if 0 <= idx < len(labels):
            return idx, labels
    except ValueError:
        pass

    wanted = _mode_key(mode)
    for i, label in enumerate(labels):
        if wanted == _mode_key(label):
            return i, labels
    raise ValueError(f"unknown mode {mode!r}; use 'mode' to list known modes")


def _run_mode(db, mode):
    if not db.modes:
        print("  globals[24] not loaded")
        return
    labels = _mode_labels(db)
    if not mode:
        for i, label in enumerate(labels):
            count = sum(1 for e in db.modes.entries if e['flags'][i])
            print(f"  {i:2d}  {label}  ({count} vars)")
        return

    idx, labels = _resolve_mode_index(db, mode)
    hits = [e for e in db.modes.entries if e['flags'][idx]]
    print(f"  {idx} {labels[idx]} ({len(hits)} vars):")
    for item in hits:
        entry = db.get(item['var_id'])
        if entry:
            print(f"  {entry.oneline(db)}")
        else:
            name = f":{item['uart']}" if item['uart'] else ""
            print(f"  0x{item['var_id']:04X}{name}")


def _run_channels(db, gidx, name):
    if not db.channels:
        print("  no signal channels loaded")
        return
    if gidx is not None:
        hits = [ch for ch in db.channels.values() if ch.gidx == gidx]
        if hits:
            for ch in hits:
                print(ch.dump())
        else:
            print(f"  no channels from globals[{gidx}]")
    elif name:
        ch = db.channels.get(name.upper())
        if ch:
            print(ch.dump())
        else:
            print(f"  channel '{name}' not found")
            print(f"  available: {', '.join(sorted(db.channels.keys()))}")
    else:
        for ch_name in sorted(db.channels):
            print(db.channels[ch_name].dump())


def run_repl(db):
    parser = build_command_parser()
    print()
    print("  AS10 Descriptor Navigator")
    print("  " + "-" * 40)
    _print_info(db)
    print()
    print('  Type "help" for commands, "quit" to exit.')
    print()

    while True:
        try:
            line = input("as10> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ("quit", "exit", "q"):
            break
        if line.lower() == "help":
            parser.print_help()
            print()
            continue
        if line.lower().startswith("help "):
            parts = shlex.split(line)
            if len(parts) == 2:
                try:
                    parser.parse_args([parts[1], "--help"])
                except SystemExit:
                    pass
                print()
                continue
        try:
            args = parser.parse_args(shlex.split(line))
            run_command(db, args)
        except SystemExit:
            pass
        except Exception as exc:
            print(f"  Error: {exc}")
        print()


def dump_tsv(db, tables_to_dump, outfile=None):
    """Dump all entries as TSV for import into spreadsheets."""
    import io
    out = open(outfile, 'w', encoding='utf-8') if outfile else sys.stdout

    def s(str_id):
        """Resolve string or return empty."""
        if not db.strtab or not str_id or str_id in (0xFFFF, 0xDE):
            return ""
        r = db.string(str_id)
        return r if r else ""

    def g4_target_fields(idx):
        entry = db.g4_by_idx(idx)
        if not entry:
            return "", ""
        return f"0x{entry.var_id:04X}", db.uart_name(entry.var_id) or ""

    for tnum in tables_to_dump:
        if tnum not in db.tables:
            continue
        base = db.table_bases.get(tnum, 0)

        if tnum == 4:
            out.write(f"# globals[4] -- base=0x{base:08X}  stride=0x1C  count={len(db.tables[4])}\n")
            out.write("idx\tvar_id\taddr\toffset\tflags\tflags_str\t"
                      "callback\tnext_dependent_g4_idx\tnext_dependent_var_id\tnext_dependent_name\t"
                      "name_str_id\tname\t"
                      "default\tmax\tmin\tstep\tscale\tdp\t"
                      "default_fmt\tmax_fmt\tmin_fmt\tstep_fmt\trange\t"
                      "units_str_id\tunits\t"
                      "g5_str_a\tg5_name_a\tg5_str_b\tg5_name_b\n")
            for e in db.tables[4]:
                off = e.addr - base
                g5a = g5b = g5na = g5nb = ""
                rec = db.g5_lookup(e.idx)
                if rec is not None:
                    a, b = rec
                    g5a = f"0x{a:04X}"
                    g5b = f"0x{b:04X}"
                    if a != 0xDE: g5na = s(a)
                    if b != 0xDE: g5nb = s(b)
                next_vid, next_name = g4_target_fields(e.next_var_idx)
                out.write(f"0x{e.idx:03X}\t0x{e.var_id:04X}\t0x{e.addr:08X}\t0x{off:05X}\t"
                          f"0x{e.flags:04X}\t{decode_flags(e.flags)}\t"
                          f"{e.callback_id}\t0x{e.next_var_idx & 0xFFFF:04X}\t"
                          f"{next_vid}\t{next_name}\t"
                          f"0x{e.name_str_id:04X}\t{s(e.name_str_id)}\t"
                          f"{e.default_value}\t{e.max_value}\t{e.min_value}\t"
                          f"{e.step_size}\t{e.scale_factor}\t{e.decimal_places}\t"
                          f"{e._fmt(e.default_value)}\t{e._fmt(e.max_value)}\t"
                          f"{e._fmt(e.min_value)}\t{e._fmt(e.step_size)}\t"
                          f"{e.range_str()}\t"
                          f"0x{e.units_str_id:04X}\t{s(e.units_str_id)}\t"
                          f"{g5a}\t{g5na}\t{g5b}\t{g5nb}\n")

        elif tnum == 8:
            out.write(f"# globals[8] -- base=0x{base:08X}  stride=0x14  count={len(db.tables[8])}\n")
            out.write("idx\tvar_id\taddr\toffset\tflags\tflags_str\t"
                      "callback\tdependency_head_g4_idx\tdependency_head_var_id\tdependency_head_name\t"
                      "name_str_id\tname\t"
                      "default\tnum_options\t"
                      "perm_mask\tbase_str_id\toption_names\t"
                      "param_0a\tparam_12\n")
            for e in db.tables[8]:
                off = e.addr - base
                nstr = s(e.name_str_id) if e.name_str_id not in (0xFFFF, 0xDE) else ""
                opts_str = ""
                if e.has_strings():
                    labels = e.option_strings(db)
                    # mark permitted with Y, denied with N
                    parts_o = []
                    for i, lbl in enumerate(labels):
                        mark = "Y" if e.perm_mask & (1 << i) else "N"
                        parts_o.append(f"{mark}{lbl}")
                    opts_str = " | ".join(parts_o)
                linked_vid, linked_name = g4_target_fields(e.linked_var_idx)
                out.write(f"0x{e.idx:03X}\t0x{e.var_id:04X}\t0x{e.addr:08X}\t0x{off:04X}\t"
                          f"0x{e.flags:04X}\t{decode_flags(e.flags)}\t"
                          f"{e.callback_id}\t0x{e.linked_var_idx & 0xFFFF:04X}\t"
                          f"{linked_vid}\t{linked_name}\t"
                          f"0x{e.name_str_id:04X}\t{nstr}\t"
                          f"{e.default_value}\t{e.num_options}\t"
                          f"0x{e.perm_mask:08X}\t"
                          f"0x{e.base_str_id & 0xFFFF:04X}\t{opts_str}\t"
                          f"{e.param_0a}\t{e.param_12}\n")

        elif tnum == 6:
            out.write(f"# globals[6] -- base=0x{base:08X}  stride=0x18  count={len(db.tables[6])}\n")
            out.write("idx\tvar_id\taddr\toffset\tflags\tflags_str\t"
                      "config_group\tlinked_var\tparent_var\t"
                      "default\tperm_mask\t"
                      "item_count\tstep_div\tchild_index\tlabel_str\n")
            for e in db.tables[6]:
                off = e.addr - base
                out.write(f"0x{e.idx:03X}\t0x{e.var_id:04X}\t0x{e.addr:08X}\t0x{off:04X}\t"
                          f"0x{e.flags:04X}\t{decode_flags(e.flags)}\t"
                          f"{e.config_group}\t0x{e.linked_var:04X}\t0x{e.parent_var:04X}\t"
                          f"0x{e.default:08X}\t0x{e.perm_mask:08X}\t"
                          f"{e.item_count}\t{e.step_div}\t0x{e.child_index:04X}\t0x{e.label_str:04X}\n")

        elif tnum == 3:
            out.write(f"# globals[3] -- base=0x{base:08X}  stride=10  count={len(db.tables[3])}\n")
            out.write("idx\tvar_id\taddr\toffset\tflags\tflags_str\t"
                      "notify_handler\tlinked_var_id\tformat_str_id\tmax_length\n")
            for e in db.tables[3]:
                off = e.addr - base
                out.write(f"0x{e.idx:03X}\t0x{e.var_id:04X}\t0x{e.addr:08X}\t0x{off:04X}\t"
                          f"0x{e.flags:04X}\t{decode_flags(e.flags)}\t"
                          f"{e.notify_handler}\t0x{e.linked_var_id & 0xFFFF:04X}\t"
                          f"0x{e.format_str_id & 0xFFFF:04X}\t{e.max_length}\n")

        elif tnum == 9:
            out.write(f"# globals[9] -- base=0x{base:08X}  stride=0x18  count={len(db.tables[9])}\n")
            out.write("idx\tvar_id\taddr\toffset\tflags\tflags_str\t"
                      "linked\tname_str_id\tname\t"
                      "default\tnum_options\tperm_mask\t"
                      "base_str_id\tmin\tmax\tstep\n")
            for e in db.tables[9]:
                off = e.addr - base
                nstr = s(e.name_str_id) if e.name_str_id not in (0xFFFF, 0xDE) else ""
                out.write(f"0x{e.idx:03X}\t0x{e.var_id:04X}\t0x{e.addr:08X}\t0x{off:04X}\t"
                          f"0x{e.flags:04X}\t{decode_flags(e.flags)}\t"
                          f"0x{e.linked_var:04X}\t"
                          f"0x{e.name_str_id:04X}\t{nstr}\t"
                          f"{e.default_byte}\t{e.num_options}\t"
                          f"0x{e.perm_bitmask:08X}\t"
                          f"0x{e.base_str_id:04X}\t"
                          f"{e.min_value}\t{e.max_value}\t{e.step_size}\n")

        elif tnum == 10:
            out.write(f"# globals[10] -- base=0x{base:08X}  stride=0x24  count={len(db.tables[10])}\n")
            out.write("idx\taddr\toffset\tflags\tflags_str\t"
                      "callback\tname_str_id\tname\t"
                      "default\tmax\tmin\tstep\tscale\tdp\t"
                      "default_fmt\tmax_fmt\tmin_fmt\tstep_fmt\trange\t"
                      "units_str_id\tunits\t"
                      "ram_base\tram_count\n")
            for e in db.tables[10]:
                off = e.addr - base
                out.write(f"0x{e.idx:03X}\t0x{e.addr:08X}\t0x{off:04X}\t"
                          f"0x{e.flags:04X}\t{decode_flags(e.flags)}\t"
                          f"{e.callback_id}\t"
                          f"0x{e.name_str_id:04X}\t{s(e.name_str_id)}\t"
                          f"{e.default_value}\t{e.max_value}\t{e.min_value}\t"
                          f"{e.step_size}\t{e.scale_factor}\t{e.decimal_places}\t"
                          f"{e._fmt(e.default_value)}\t{e._fmt(e.max_value)}\t"
                          f"{e._fmt(e.min_value)}\t{e._fmt(e.step_size)}\t"
                          f"{e.range_str()}\t"
                          f"0x{e.units_str_id:04X}\t{s(e.units_str_id)}\t"
                          f"{e.ram_base_index}\t{e.ram_count}\n")

        out.write("\n")

    # New tables (not keyed by tnum)
    if db.streams:
        out.write("# globals[19] -- stream table\n")
        out.write("name\tcapacity\trec_size\tvar_id\tvar_name\tlast\n")
        for e in db.streams.entries:
            sn = e['var_name'] or ''
            out.write(f"{e['name']}\t{e['capacity']}\t{e['rec_size']}\t"
                      f"0x{e['var_id']:04X}\t{sn}\t0x{e['max_records']:04X}\n")
        out.write("\n")

    if db.timers and db.timers.entries:
        out.write(f"# globals[1] -- timer scale table ({len(db.timers.entries)} entries)\n")
        out.write("idx\tlevel\tticks\tmultiplier\tperiod_s\n")
        for e in db.timers.entries:
            out.write(f"{e['idx']}\t{e['level']}\t{e['ticks']}\t{e['multiplier']}\t{e['period']}\n")
        out.write("\n")

    if db.pdl and db.pdl.var_ids:
        out.write(f"# globals[20] -- {db.pdl.name} ({len(db.pdl.var_ids)} vars)\n")
        out.write("idx\tvar_id\tuart_name\n")
        for i, (vid, uart) in enumerate(db.pdl.var_ids):
            out.write(f"{i}\t0x{vid:04X}\t{uart or ''}\n")
        out.write("\n")

        out.write(f"# globals[20/21] -- {db.pdl.name} rules ({len(db.pdl.rules)} entries)\n")
        out.write("idx\tvar_id_a\tname_a\tvar_id_b\tname_b\ttype\tparam_a\tparam_b\n")
        for r in db.pdl.rules:
            pa = f"0x{r['param_a']:08X}" if r['param_a'] != 0xFFFFFFFF else ""
            pb = f"0x{r['param_b']:08X}" if r['param_b'] != 0xFFFFFFFF else ""
            out.write(f"{r['idx']}\t0x{r['vid_a']:04X}\t{r['name_a'] or ''}\t"
                      f"0x{r['vid_b']:04X}\t{r['name_b'] or ''}\t"
                      f"{(r['flags'] >> 16) & 0xFF}\t{pa}\t{pb}\n")
        out.write("\n")

    if db.modes and db.modes.entries:
        out.write(f"# globals[24] -- mode table ({len(db.modes.entries)} settings)\n")
        hdr = "idx\tvar_id\tuart_name\t" + "\t".join(str(i) for i in range(db.modes.num_flags))
        out.write(hdr + "\n")
        for e in db.modes.entries:
            fstr = "\t".join(str(f) for f in e['flags'])
            out.write(f"{e['idx']}\t0x{e['var_id']:04X}\t{e['uart'] or ''}\t{fstr}\n")
        out.write("\n")

    if db.names:
        out.write(f"# globals[23] -- UART name lookup ({len(db.names.by_name)} entries)\n")
        out.write("name\tvar_id\n")
        for name in sorted(db.names.by_name):
            out.write(f"{name}\t0x{db.names.by_name[name]:04X}\n")
        out.write("\n")

    if db.npd and db.npd.signals:
        out.write(f"# globals[14] -- NPD signal group ({len(db.npd.signals)} signals)\n")
        out.write("var_id\tuart_name\n")
        for vid, uart in db.npd.signals:
            out.write(f"0x{vid:04X}\t{uart or ''}\n")
        out.write("\n")

    if db.npa and db.npa.signals:
        out.write(f"# globals[15] -- NPA signal group ({len(db.npa.signals)} signals)\n")
        out.write("var_id\tuart_name\n")
        for vid, uart in db.npa.signals:
            out.write(f"0x{vid:04X}\t{uart or ''}\n")
        out.write("\n")

    if db.channels:
        out.write(f"# Signal channels ({len(db.channels)} channels)\n")
        out.write("channel\tfield_idx\tvar_id\tuart_name\tfield_name\tsamples_per_rec\n")
        for ch_name in sorted(db.channels):
            ch = db.channels[ch_name]
            for i, (vid, uart) in enumerate(ch.var_ids):
                fn = ch.field_names[i] if i < len(ch.field_names) and ch.field_names[i] else ''
                spr = ch.samples_per_rec[i] if i < len(ch.samples_per_rec) else ''
                out.write(f"{ch_name}\t{i}\t0x{vid:04X}\t{uart or ''}\t{fn}\t{spr}\n")
        out.write("\n")

    if outfile:
        out.close()
        print(f"[+] Wrote {outfile}")


def load_db(args):
    fl = Flash(args.firmware)
    print(f"[+] {len(fl.data)} bytes  0x{fl.base:08X}..0x{fl.end:08X}")

    ta = {}
    g2 = None
    globals_addr = None
    globals_values = None

    if args.globals:
        # User provided a flash address containing the pointer array
        ptrs = {i: fl.u32(args.globals + i * 4) for i in range(30)}
        globals_addr = args.globals
        globals_values = ptrs
        print(f"[+] globals[] @ 0x{args.globals:08X}:")
        for i in range(30):
            tag = f"  <- [{i}]" if i in (2,3,4,5,6,8,9,10) else ""
            if ptrs[i] and fl.is_flash_ptr(ptrs[i]):
                print(f"    [{i:2d}] 0x{ptrs[i]:08X}{tag}")
        for t in (3,4,6,8,9,10):
            if fl.is_flash_ptr(ptrs.get(t,0)): ta[f"table{t}"] = ptrs[t]
        if fl.is_flash_ptr(ptrs.get(1,0)): ta['timers'] = ptrs[1]
        if fl.is_flash_ptr(ptrs.get(5,0)): ta['globals5'] = ptrs[5]
        if fl.is_flash_ptr(ptrs.get(2,0)): g2 = ptrs[2]
        if fl.is_flash_ptr(ptrs.get(0,0)):  ta['device'] = ptrs[0]
        if fl.is_flash_ptr(ptrs.get(23,0)): ta['names'] = ptrs[23]
        if fl.is_flash_ptr(ptrs.get(16,0)): ta['vargroups'] = ptrs[16]
        if fl.is_flash_ptr(ptrs.get(20,0)): ta['pdl'] = ptrs[20]
        if fl.is_flash_ptr(ptrs.get(21,0)): ta['pdl_rules'] = ptrs[21]
        if fl.is_flash_ptr(ptrs.get(24,0)):
            ta['modes'] = ptrs[24]
            g25 = ptrs.get(25, 0)
            if 0 < g25 < 200:
                ta['modes_count'] = g25
        if fl.is_flash_ptr(ptrs.get(17,0)): ta['desc17'] = ptrs[17]
        if fl.is_flash_ptr(ptrs.get(18,0)): ta['desc18'] = ptrs[18]
        if fl.is_flash_ptr(ptrs.get(19,0)): ta['streams'] = ptrs[19]
        if fl.is_flash_ptr(ptrs.get(14,0)): ta['npd'] = ptrs[14]
        if fl.is_flash_ptr(ptrs.get(15,0)): ta['npa'] = ptrs[15]
        if fl.is_flash_ptr(ptrs.get(22,0)): ta['signals'] = ptrs[22]
        if fl.is_flash_ptr(ptrs.get(11,0)): ta['brp'] = ptrs[11]
        if fl.is_flash_ptr(ptrs.get(12,0)): ta['csl'] = ptrs[12]
        if fl.is_flash_ptr(ptrs.get(13,0)): ta['str_ch'] = ptrs[13]
        if fl.is_flash_ptr(ptrs.get(26,0)): ta['tce'] = ptrs[26]
        if fl.is_flash_ptr(ptrs.get(27,0)): ta['apn'] = ptrs[27]
        if fl.is_flash_ptr(ptrs.get(28,0)): ta['oxh'] = ptrs[28]
    else:
        # Auto-detect all tables by content signatures
        found = find_tables_direct(fl)
        globals_addr = found.pop('_globals_addr', None)
        globals_values = found.pop('_globals_values', None)
        for k, v in found.items():
            if k == 'globals2':
                if not g2: g2 = v
            else:
                ta[k] = v

    # globals[2] now found via globals[] array in auto-detect

    if not ta:
        raise ValueError("no descriptor tables found; use --globals 0xADDR if needed")

    return DB(fl, ta, g2, None, globals_addr, globals_values)


def _main():
    ap = build_main_parser()
    args = ap.parse_args()

    if args.interactive and args.command is not None:
        raise ValueError("--interactive cannot be combined with a command")

    if not os.path.isfile(args.firmware):
        raise FileNotFoundError(args.firmware)

    with contextlib.redirect_stdout(io.StringIO()):
        db = load_db(args)
    db.verbose = args.verbose

    if args.interactive:
        run_repl(db)
    else:
        run_command(db, args)
    return 0


def main():
    try:
        return _main()
    except BrokenPipeError:
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
ResMed AirSense UART Configuration Tool

Read, write, dump, and restore device configuration variables over UART.
Variables are organized into groups matching the SETTINGS/*.tgt files.

"""

import serial
import argparse
import time
import sys
import json


GROUPS = {
    'AGL': ['AFC', 'STU', 'MPI', 'MPA'],
    'BGL': ['CCS', 'CCP', 'PNA', 'SRN', 'PCD', 'PCB', 'SNB', 'SNZ', 'FLZ', 'FLG',
            'PZH', 'PSH'],
    'CGL': ['STP', 'IPC'],
    'DGL': ['BRE', 'VCS', 'VTS', 'ITN', 'ITX', 'ITT', 'RRT'],
    'EGL': ['EPX', 'EPA', 'EPT', 'EPR'],
    'IGL': ['EBE', 'RST', 'RSC', 'EPS', 'EPP', 'IPP'],
    'MGL': ['QFC', 'ACC', 'HME', 'SCF', 'TLF', 'ALV', 'NMF', 'SPX', 'APX', 'LMA',
            'HLE', 'ALR', 'SST', 'RMT', 'RMA'],
    'NGL': ['ATH'],
    'PGL': ['ABF', 'HTF', 'HTS', 'HTX', 'HMS', 'HMX', 'CCO', 'TBT', 'MSK'],
    'QXH': ['EAS', 'AXS', 'EAI', 'EAX', 'ANS'],
    'QXJ': ['IVS', 'WMV', 'IBR', 'WPM', 'WPA', 'EPI', 'PHI', 'PHT'],
    'RGL': ['RPF', 'RCF', 'RXF', 'RDF', 'RPW', 'RCW', 'RXW', 'RDW', 'RPH', 'RCH',
            'RXH', 'RDH', 'RPO', 'RCM', 'RXM', 'RDM'],
    'SGL': ['IHU', 'PRD', 'TMU', 'LAN', 'LNC', 'MOP'],
    'UGL': ['TUD'],
    'VGL': ['SPT', 'STV', 'MNE', 'MXI'],
    'XGL': ['STE', 'MNS', 'MXS', 'EEP'],
}

# Build reverse lookup: var name > group
VAR_TO_GROUP = {}
for grp, vars_list in GROUPS.items():
    for v in vars_list:
        VAR_TO_GROUP[v] = grp

ALL_VARS = [v for grp in sorted(GROUPS) for v in GROUPS[grp]]

GROUP_ALIASES = {
    'all': list(GROUPS.keys()),
}

INFO_VARS = ['BID', 'SID', 'CID', 'PCB', 'SRN', 'PCD', 'PNA']


BDD_RATES = {57600: '0000', 115200: '0001', 460800: '0002'}
BDD_RATES_ORDERED = [460800, 115200, 57600]
PROBE_RATES = [57600, 115200, 460800]


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc

def escape_payload(data: bytes) -> bytes:
    return data.replace(b'U', b'UU')

def build_frame(frame_type: str, payload: bytes) -> bytes:
    escaped = escape_payload(payload)
    frame_len = 1 + 1 + 3 + len(escaped) + 4
    pre_crc = b'U' + frame_type.encode() + f'{frame_len:03X}'.encode() + escaped
    crc = crc16_ccitt(pre_crc)
    return pre_crc + f'{crc:04X}'.encode()

def build_q_frame(cmd: str) -> bytes:
    return build_frame('Q', cmd.encode())

def parse_responses(data: bytes) -> list:
    responses = []
    i = 0
    while i < len(data):
        if data[i:i+1] == b'U' and i+1 < len(data) and data[i+1:i+2] != b'U':
            try:
                ft = chr(data[i+1])
                if ft in 'EFKLPQR':
                    length = int(data[i+2:i+5], 16)
                    if i + length <= len(data):
                        raw_payload = data[i+5:i+length-4]
                        payload = raw_payload.replace(b'UU', b'U')
                        responses.append({'type': ft, 'payload': payload})
                        i += length
                        continue
            except (ValueError, IndexError):
                pass
        i += 1
    return responses

def read_responses(ser, timeout=1.0):
    old_timeout = ser.timeout
    ser.timeout = 0.02
    data = b''
    deadline = time.time() + timeout
    while time.time() < deadline:
        chunk = ser.read(4096)
        if chunk:
            data += chunk
            trail_deadline = time.time() + 0.02
            while time.time() < trail_deadline:
                chunk = ser.read(4096)
                if chunk:
                    data += chunk
                    trail_deadline = time.time() + 0.02
            break
    ser.timeout = old_timeout
    return data, parse_responses(data)

def send_cmd(ser, cmd_str, timeout=0.5, quiet=False):
    ser.reset_input_buffer()
    ser.write(build_q_frame(cmd_str))
    ser.flush()
    raw, responses = read_responses(ser, timeout=timeout)
    if not quiet:
        for r in responses:
            print(f"  [{r['type']}] {r['payload'].decode('ascii', errors='replace')}")
    return raw, responses

def sync_uart(ser):
    ser.reset_input_buffer()
    ser.write(b'\x55' * 128)
    ser.flush()
    time.sleep(0.05)
    ser.reset_input_buffer()


def probe_baud(ser):
    for rate in PROBE_RATES:
        ser.baudrate = rate
        ser.reset_input_buffer()
        time.sleep(0.05)
        _, resp = send_cmd(ser, "G S #BID", timeout=0.3, quiet=True)
        if any(b'BID' in r['payload'] for r in resp):
            return rate
    return None

def switch_baud(ser, target, quiet=False):
    if target not in BDD_RATES or ser.baudrate == target:
        return ser.baudrate == target
    old = ser.baudrate
    if not quiet:
        print(f"[*] Switching baud: {old} -> {target} (BDD {BDD_RATES[target]})...")
    ser.reset_input_buffer()
    ser.write(build_q_frame(f"P S #BDD {BDD_RATES[target]}"))
    ser.flush()
    time.sleep(0.3)
    read_responses(ser, timeout=0.5)
    ser.baudrate = target
    sync_uart(ser)
    _, resp = send_cmd(ser, "G S #BID", timeout=0.5, quiet=True)
    if any(b'BID' in r['payload'] for r in resp):
        if not quiet:
            print(f"[+] Running at {target} baud")
        return True
    if not quiet:
        print(f"[!] No response at {target}, reverting")
    ser.baudrate = old
    sync_uart(ser)
    return False

def negotiate_best_baud(ser):
    for rate in BDD_RATES_ORDERED:
        if rate == ser.baudrate:
            return rate
        if switch_baud(ser, rate):
            return rate
    return ser.baudrate


def get_var(ser, name):
    """Read a single variable. Returns value string or None."""
    _, resp = send_cmd(ser, f"G S #{name}", timeout=0.5, quiet=True)
    for r in resp:
        payload = r['payload'].decode('ascii', errors='replace')
        # Parse "G S #XXX = VALUE"
        if '=' in payload:
            return payload.split('=', 1)[1].strip()
    return None

def set_var(ser, name, value):
    """Write a single variable. Returns True if ACK received."""
    _, resp = send_cmd(ser, f"P S #{name} {value}", timeout=0.5, quiet=True)
    for r in resp:
        payload = r['payload'].decode('ascii', errors='replace')
        if name in payload and '=' in payload:
            return True
    return False

def get_var_caps(ser, name):
    """Read capabilities/limits for a variable (G C # query). Returns value string or None."""
    _, resp = send_cmd(ser, f"G C #{name}", timeout=0.5, quiet=True)
    for r in resp:
        payload = r['payload'].decode('ascii', errors='replace')
        if '=' in payload:
            return payload.split('=', 1)[1].strip()
    return None


def resolve_groups(group_names):
    """Resolve group names/aliases to a list of variable names."""
    var_names = []
    for name in group_names:
        upper = name.upper()
        if upper in GROUP_ALIASES:
            for grp in GROUP_ALIASES[upper]:
                var_names.extend(GROUPS[grp])
        elif upper in GROUPS:
            var_names.extend(GROUPS[upper])
        elif upper in VAR_TO_GROUP:
            var_names.append(upper)
        else:
            print(f"[!] Unknown group or variable: {name}")
            return None
    return var_names

def exclude_vars(var_names, exclude_groups=None, exclude_vars_list=None):
    """Remove variables by group or individual name."""
    excluded = set()
    if exclude_groups:
        for grp in exclude_groups:
            upper = grp.upper()
            if upper in GROUPS:
                excluded.update(GROUPS[upper])
            else:
                print(f"[!] Unknown group: {grp}")
    if exclude_vars_list:
        excluded.update(v.upper() for v in exclude_vars_list)
    return [v for v in var_names if v not in excluded]


def cmd_info(ser):
    print("[*] Device info:")
    for var in INFO_VARS:
        val = get_var(ser, var)
        if val is not None:
            print(f"  {var:4s} = {val}")
        else:
            print(f"  {var:4s} = (no response)")

def cmd_get(ser, targets):
    """Get one or more variables/groups."""
    var_names = resolve_groups(targets)
    if var_names is None:
        return 1
    for name in var_names:
        val = get_var(ser, name)
        grp = VAR_TO_GROUP.get(name, '???')
        if val is not None:
            print(f"  [{grp}] {name:4s} = {val}")
        else:
            print(f"  [{grp}] {name:4s} = (no response)")
    return 0

def cmd_set(ser, var_name, value):
    """Set a single variable."""
    name = var_name.upper()
    if name not in VAR_TO_GROUP:
        print(f"[!] Unknown variable: {name}")
        return 1
    grp = VAR_TO_GROUP[name]
    old_val = get_var(ser, name)
    print(f"  [{grp}] {name} = {old_val} -> {value}")
    if set_var(ser, name, value):
        new_val = get_var(ser, name)
        print(f"  [{grp}] {name} = {new_val} (confirmed)")
        return 0
    else:
        print(f"  [!] Set failed for {name}")
        return 1

def cmd_dump(ser, groups=None, exclude_groups=None, exclude_vars_list=None):
    """Dump variables to dict. Returns {group: {var: value}}."""
    if groups:
        var_names = resolve_groups(groups)
    else:
        var_names = resolve_groups(['all'])
    if var_names is None:
        return None

    var_names = exclude_vars(var_names, exclude_groups, exclude_vars_list)

    result = {}
    total = len(var_names)
    for i, name in enumerate(var_names):
        grp = VAR_TO_GROUP.get(name, 'UNK')
        val = get_var(ser, name)
        if grp not in result:
            result[grp] = {}
        result[grp][name] = val
        sys.stdout.write(f"\r  Reading: {i+1}/{total} ({name})...")
        sys.stdout.flush()
    print(f"\r  Read {total} variables.              ")
    return result

def cmd_restore(ser, data, exclude_groups=None, exclude_vars_list=None, dry_run=False):
    """Restore variables from dump dict."""
    changes = []
    for grp in sorted(data.keys()):
        for name, value in sorted(data[grp].items()):
            if value is None:
                continue
            changes.append((grp, name, value))

    # exclusions
    excluded = set()
    if exclude_groups:
        for grp in exclude_groups:
            upper = grp.upper()
            if upper in GROUPS:
                excluded.update(GROUPS[upper])
    if exclude_vars_list:
        excluded.update(v.upper() for v in exclude_vars_list)

    changes = [(g, n, v) for g, n, v in changes if n not in excluded]

    if not changes:
        print("[!] No variables to restore.")
        return 1

    print(f"[*] Restoring {len(changes)} variables...")
    errors = 0
    for i, (grp, name, value) in enumerate(changes):
        current = get_var(ser, name)
        if current == value:
            sys.stdout.write(f"\r  {i+1}/{len(changes)} {name}: unchanged    ")
            sys.stdout.flush()
            continue

        if dry_run:
            print(f"\r  [DRY] [{grp}] {name}: {current} -> {value}")
            continue

        if set_var(ser, name, value):
            sys.stdout.write(f"\r  {i+1}/{len(changes)} {name}: {current} -> {value}    ")
            sys.stdout.flush()
        else:
            print(f"\r  [!] [{grp}] {name}: FAILED to set {value}")
            errors += 1

    print(f"\r  Restore complete. {len(changes)} variables, {errors} errors.          ")
    return 0 if errors == 0 else 1

def cmd_list(ser, groups=None):
    """List known variables with their groups and current caps."""
    if groups:
        group_list = []
        for g in groups:
            upper = g.upper()
            if upper in GROUPS:
                group_list.append(upper)
            else:
                print(f"[!] Unknown group: {g}")
                return 1
    else:
        group_list = sorted(GROUPS.keys())

    for grp in group_list:
        vars_list = GROUPS[grp]
        print(f"\n  {grp} ({len(vars_list)} vars):")
        for name in vars_list:
            val = get_var(ser, name)
            caps = get_var_caps(ser, name)
            val_str = val if val is not None else "(no response)"
            caps_str = f"  caps: {caps}" if caps else ""
            print(f"    {name:4s} = {val_str}{caps_str}")
    return 0


def connect(ser, baud_arg):
    """Connect and probe or set baud rate. Returns True on success."""
    if baud_arg == 'auto':
        print("[*] Probing device...")
        baud = probe_baud(ser)
        if not baud:
            print("[!] Device not responding at any known baud rate")
            return False
        print(f"[+] Device responding at {baud} baud")
        ser.baudrate = baud
    else:
        rate = int(baud_arg)
        ser.baudrate = rate
        _, resp = send_cmd(ser, "G S #BID", timeout=0.5, quiet=True)
        if not any(b'BID' in r['payload'] for r in resp):
            print(f"[!] No response at {rate} baud")
            return False
        print(f"[+] Device responding at {rate} baud")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='ResMed AirSense UART Configuration Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  info                          Show device identity
  get <var|group|all>           Read variables
  set <var> <value>             Write a variable
  dump                          Dump all variables to JSON
  restore                       Restore variables from JSON
  list                          List known variables and limits

Groups: """ + ', '.join(sorted(GROUPS.keys())) + """

Examples:
  %(prog)s -p /dev/ttyACM0 info
  %(prog)s -p /dev/ttyACM0 get MGL
  %(prog)s -p /dev/ttyACM0 get SPT
  %(prog)s -p /dev/ttyACM0 set SPT 0001
  %(prog)s -p /dev/ttyACM0 dump -o config.json
  %(prog)s -p /dev/ttyACM0 dump --groups MGL EGL -o therapy.json
  %(prog)s -p /dev/ttyACM0 restore -i config.json
  %(prog)s -p /dev/ttyACM0 restore -i config.json --exclude-groups BGL
  %(prog)s -p /dev/ttyACM0 list --groups MGL
""")

    parser.add_argument('-p', '--port', required=True, help='Serial port')
    parser.add_argument('--baud', default='auto', help='Baud rate: auto, 57600, 115200, 460800')

    sub = parser.add_subparsers(dest='command', help='Command')

    sub.add_parser('info', help='Show device identity')

    p_get = sub.add_parser('get', help='Read variables')
    p_get.add_argument('targets', nargs='+', help='Variable names, group names, or "all"')

    p_set = sub.add_parser('set', help='Write a variable')
    p_set.add_argument('var', help='Variable name (3 chars)')
    p_set.add_argument('value', help='Value to set (hex string)')

    p_dump = sub.add_parser('dump', help='Dump variables to JSON')
    p_dump.add_argument('-o', '--output', required=True, help='Output JSON file')
    p_dump.add_argument('--groups', nargs='+', help='Only dump these groups')
    p_dump.add_argument('--exclude-groups', nargs='+', help='Exclude these groups')
    p_dump.add_argument('--exclude-vars', nargs='+', help='Exclude these variables')

    p_restore = sub.add_parser('restore', help='Restore variables from JSON')
    p_restore.add_argument('-i', '--input', required=True, help='Input JSON file')
    p_restore.add_argument('--exclude-groups', nargs='+', help='Skip these groups')
    p_restore.add_argument('--exclude-vars', nargs='+', help='Skip these variables')
    p_restore.add_argument('--dry-run', action='store_true', help='Show changes without writing')

    p_raw = sub.add_parser('raw', help='Send raw command')
    p_raw.add_argument('cmd', nargs='+', help='Raw command string (e.g. "G S #BID")')

    p_list = sub.add_parser('list', help='List known variables and limits')
    p_list.add_argument('--groups', nargs='+', help='Only list these groups')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    ser = serial.Serial(args.port, 57600, timeout=1.0)

    try:
        if not connect(ser, args.baud):
            return 1

        if args.command == 'info':
            return cmd_info(ser)

        elif args.command == 'get':
            return cmd_get(ser, args.targets)

        elif args.command == 'set':
            return cmd_set(ser, args.var, args.value)

        elif args.command == 'dump':
            data = cmd_dump(ser, args.groups, args.exclude_groups, args.exclude_vars)
            if data is None:
                return 1
            with open(args.output, 'w') as f:
                json.dump(data, f, indent=2, sort_keys=True)
            print(f"[+] Saved to {args.output}")
            return 0

        elif args.command == 'restore':
            with open(args.input) as f:
                data = json.load(f)
            return cmd_restore(ser, data, args.exclude_groups, args.exclude_vars, args.dry_run)

        elif args.command == 'raw':
            cmd_str = ' '.join(args.cmd)
            send_cmd(ser, cmd_str, timeout=1.0)
            return 0

        elif args.command == 'list':
            return cmd_list(ser, args.groups)

    finally:
        ser.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())

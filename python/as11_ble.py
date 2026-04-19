#!/usr/bin/env python3
"""
AirSense 11 BLE client. Scan, pair (SRP), send JSON-RPC, stream, spool.

Usage:
    python3 as11_ble.py scan
    python3 as11_ble.py pair --passkey 123456
    python3 as11_ble.py rpc --method GetDateTime
    python3 as11_ble.py rpc --method Get --params '{"name":"SetPressure"}'
"""

import argparse
import asyncio
import base64
import binascii
import hashlib
import json
import logging
import os
import re
import struct
import sys
from pathlib import Path

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    sys.exit("bleak not installed. Run: pip install bleak")



# BLE GATT UUIDs
SERVICE_UUID = "0000fd56-0000-1000-8000-00805f9b34fb"
TX_CHAR_UUID = "a6220002-35f1-4b20-afae-cb089d2044aa"   # app -> device
RX_CHAR_UUID = "a6220003-35f1-4b20-afae-cb089d2044aa"   # device -> app

DEVICE_NAME_PREFIX = "ResMed"

# FIG protocol
FIG_SYNC       = 0xCAFEBABE
FIG_SYNC_BYTES = struct.pack('<I', FIG_SYNC)
FIG_HEADER_LEN = 12
FIG_VCID_RPC       = 0x0393  # plaintext, key exchange only
FIG_VCID_RPC_ENC   = 0x0397  # encrypted TX
FIG_VCID_RX_ENC    = 0x0396  # encrypted RX

log = logging.getLogger("as11_ble")

CRED_FILE = Path.home() / ".as11_ble.json"



from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, hmac

# ResMed SRP-6a (RFC 5054 2048-bit group, SHA-256, no identity).
# x = H(salt || H(passkey))
# M1 = H(H(N) xor H(g) || salt || pad(A) || pad(B) || K)  where K = H(S)
# session_key = SHA256(K || nonce) on successful ConfirmKeyExchange.

_SRP_N = int(
    "AC6BDB41324A9A9BF166DE5E1389582FAF72B6651987EE07FC3192943DB56050"
    "A37329CBB4A099ED8193E0757767A13DD52312AB4B03310DCD7F48A9DA04FD50"
    "E8083969EDB767B0CF6095179A163AB3661A05FBD5FAAAE82918A9962F0B93B"
    "855F97993EC975EEAA80D740ADBF4FF747359D041D5C33EA71D281E446B1477"
    "3BCA97B43A23FB801676BD207A436C6481F1D2B9078717461A5B9D32E688F87"
    "748544523B524B0D57D5EA77A2775D2ECFA032CFBDBF52FB3786160279004E5"
    "7AE6AF874E7303CE53299CCC041C7BC308D82A5698F3A8D0C38271AE35F8E9D"
    "BFBB694B5C803D89F7AE435DE236D525F54759B65E372FCD68EF20FA7111F9E"
    "4AFF73", 16)
_SRP_G = 2
_SRP_PAD_LEN = 256


def _srp_pad(n):
    return n.to_bytes(_SRP_PAD_LEN, "big")


def H(*args):
    """SHA-256 of concatenated byte arguments (ints are padded to 256 bytes BE)."""
    h = hashlib.sha256()
    for a in args:
        if isinstance(a, int):
            a = _srp_pad(a)
        h.update(a)
    return h.digest()


class SRPClient:
    def __init__(self, passkey):
        self.passkey = passkey
        self.a = int.from_bytes(os.urandom(32), "big")
        self.A = pow(_SRP_G, self.a, _SRP_N)
        self.S = None
        self.K = None
        self.M1 = None
        self.M2 = None

    @property
    def public_key_hex(self):
        return _srp_pad(self.A).hex().upper()

    def process(self, server_pk_hex, salt_hex):
        B = int(server_pk_hex, 16)
        if B % _SRP_N == 0:
            raise ValueError("invalid server public key (B mod N == 0)")

        k = int.from_bytes(H(_srp_pad(_SRP_N), _srp_pad(_SRP_G)), "big")
        salt = bytes.fromhex(salt_hex)
        x = int.from_bytes(H(salt, H(self.passkey.encode('ascii'))), "big")
        u = int.from_bytes(H(_srp_pad(self.A), _srp_pad(B)), "big")
        if u == 0:
            raise ValueError("invalid u (== 0)")

        self.S = pow(B - k * pow(_SRP_G, x, _SRP_N), self.a + u * x, _SRP_N) % _SRP_N
        self.K = H(_srp_pad(self.S))

        h_N = H(_srp_pad(_SRP_N))
        h_g = H(_srp_pad(_SRP_G))
        h_xor = bytes(a ^ b for a, b in zip(h_N, h_g))
        self.M1 = H(h_xor, salt, _srp_pad(self.A), _srp_pad(B), self.K)
        self.M2 = H(self.M1, h_xor)

    @property
    def client_proof_hex(self):
        return self.M1.hex().upper()

    @property
    def session_key_hex(self):
        return self.K.hex().upper()

    def derive_session_key(self, nonce_hex):
        """SHA256(K || nonce) - matches figlib SrpKeyExchange::GenerateSessionKey."""
        self.aes_key = H(self.K, bytes.fromhex(nonce_hex))
        return self.aes_key.hex().upper()

    def verify_server(self, server_proof_hex):
        if server_proof_hex.upper() != self.M2.hex().upper():
            raise ValueError("server proof mismatch")


class FigCodec:
    """FIG packet encoder/decoder.

    Frame: [4 SYNC] [2 VCID] [2 LEN] [4 PAYLOAD_CRC] [4 HEADER_CRC] [N PAYLOAD]
    All integers little-endian, CRC32 IEEE.
    """

    def __init__(self):
        self._rx_buf = bytearray()

    @staticmethod
    def crc32(data: bytes) -> int:
        return binascii.crc32(data) & 0xFFFFFFFF

    @staticmethod
    def encode(vcid: int, payload: bytes) -> bytes:
        payload_crc = FigCodec.crc32(payload)
        header = struct.pack('<HH I', vcid, len(payload), payload_crc)
        header_crc = FigCodec.crc32(header)
        return FIG_SYNC_BYTES + header + struct.pack('<I', header_crc) + payload

    def feed(self, data: bytes):
        self._rx_buf.extend(data)

    def decode(self) -> list:
        """Pop complete packets from RX buffer. Returns [(vcid, payload), ...]."""
        packets = []
        while True:
            idx = self._rx_buf.find(FIG_SYNC_BYTES)
            if idx < 0:
                # keep tail in case sync straddles a notification
                if len(self._rx_buf) > 3:
                    self._rx_buf = self._rx_buf[-3:]
                break

            if idx > 0:
                log.debug("discarding %d bytes before sync", idx)
                self._rx_buf = self._rx_buf[idx:]

            if len(self._rx_buf) < 4 + FIG_HEADER_LEN:
                break

            hdr = bytes(self._rx_buf[4:16])
            vcid, payload_len, payload_crc, header_crc = struct.unpack('<HH II', hdr)

            if FigCodec.crc32(hdr[:8]) != header_crc:
                log.warning("header CRC mismatch, skipping sync")
                self._rx_buf = self._rx_buf[4:]
                continue

            total = 4 + FIG_HEADER_LEN + payload_len
            if len(self._rx_buf) < total:
                break

            payload = bytes(self._rx_buf[16:16 + payload_len])

            if FigCodec.crc32(payload) != payload_crc:
                log.warning("payload CRC mismatch (vcid=%d len=%d)", vcid, payload_len)
                self._rx_buf = self._rx_buf[4:]
                continue

            packets.append((vcid, payload))
            self._rx_buf = self._rx_buf[total:]

        return packets


class As11Connection:
    def __init__(self, debug=False):
        self._client = None
        self._codec = FigCodec()
        self._rpc_id = 0
        self._response_event = asyncio.Event()
        self._response_data = None
        self._mtu = 244
        self._session_key = None
        self._notification_cb = None
        self.debug = debug

    def set_session_key(self, key_hex):
        """AES-256 session key from SHA256 output."""
        self._session_key = bytes.fromhex(key_hex[:64])
        log.info("session key set (%d bytes): %s...", len(self._session_key), key_hex[:16])

    def _aes_encrypt(self, plaintext, length_prefix=True):
        """AES-CBC(key, random IV). Wire: [IV][cipher([u16 len][payload][zero pad])]."""
        if length_prefix:
            framed = struct.pack('<H', len(plaintext)) + plaintext
        else:
            framed = plaintext
        pad_len = (16 - len(framed) % 16) % 16
        padded = framed + b'\x00' * pad_len
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(self._session_key), modes.CBC(iv))
        enc = cipher.encryptor()
        ct = enc.update(padded) + enc.finalize()
        return iv + ct

    def _aes_decrypt(self, data):
        iv = data[:16]
        ct = data[16:]
        cipher = Cipher(algorithms.AES(self._session_key), modes.CBC(iv))
        dec = cipher.decryptor()
        plaintext = dec.update(ct) + dec.finalize()
        # strip u16 LE length prefix
        if len(plaintext) >= 2:
            payload_len = struct.unpack_from('<H', plaintext, 0)[0]
            return plaintext[2:2 + payload_len]
        return plaintext.rstrip(b'\x00')

    @staticmethod
    async def scan(timeout=10.0):
        """Returns [(address, name, rssi), ...]."""
        devices = await BleakScanner.discover(
            timeout=timeout,
            service_uuids=[SERVICE_UUID],
            return_adv=True,
        )
        results = []
        for addr, (dev, adv) in devices.items():
            name = dev.name or adv.local_name or ""
            if name.startswith(DEVICE_NAME_PREFIX):
                results.append((dev.address, name, adv.rssi))
        return results

    async def connect(self, address: str):
        self._client = BleakClient(address, timeout=20.0)
        await self._client.connect()
        log.info("connected to %s", address)

        # device supports MTU 247, pull negotiated chunk size from the write char
        try:
            svcs = self._client.services
            for svc in svcs:
                for char in svc.characteristics:
                    if char.uuid == TX_CHAR_UUID:
                        self._mtu = char.max_write_without_response_size
                        break
        except Exception:
            pass
        if self._mtu < 244:
            self._mtu = 244
        log.info("write chunk size: %d", self._mtu)

        # Steehl chars - possible handshake requirement
        STEEHL_CHARS = [
            "3d5085ac-d8a2-4a56-8d2e-1dc7508e67bc",
            "1681c44f-2798-4bfa-b11a-65e9f55c2082",
            "e5e33ba4-c823-4a86-9b15-1bf2acb27a1c",
        ]
        for uuid in STEEHL_CHARS:
            try:
                val = await self._client.read_gatt_char(uuid)
                log.info("Steehl %s: %s", uuid[:8], val.hex())
            except Exception as e:
                log.debug("Steehl %s: %s", uuid[:8], e)

        # Service Changed indication must be enabled before FIG works
        SVC_CHANGED_UUID = "00002a05-0000-1000-8000-00805f9b34fb"
        try:
            await self._client.start_notify(SVC_CHANGED_UUID, lambda s, d:
                log.debug("Service Changed indication: %s", d.hex()))
            log.info("Service Changed indication enabled")
        except Exception as e:
            log.debug("Service Changed: %s", e)

        await self._client.start_notify(RX_CHAR_UUID, self._on_notify)
        log.info("RX notifications enabled")

        if self.debug:
            for svc in self._client.services:
                log.debug("Service: %s", svc.uuid)
                for char in svc.characteristics:
                    props = ",".join(char.properties)
                    log.debug("  Char: %s [%s]", char.uuid, props)
                    for desc in char.descriptors:
                        log.debug("    Desc: %s", desc.uuid)

    async def disconnect(self):
        if self._client and self._client.is_connected:
            await self._client.disconnect()
            log.info("disconnected")

    def _on_notify(self, sender, data: bytearray):
        if self.debug:
            log.debug("RX notify (%d bytes): %s", len(data), data.hex())
        self._codec.feed(bytes(data))

        for vcid, raw_payload in self._codec.decode():
            log.debug("FIG packet: vcid=%d len=%d", vcid, len(raw_payload))
            if self.debug:
                log.debug("  raw payload hex: %s", raw_payload.hex())

            # 0x0396 = Level 2 patient, 0x0394/0x0380 = possible Level 3 service
            if vcid in (FIG_VCID_RX_ENC, 0x0394, 0x0380) and self._session_key:
                try:
                    raw_payload = self._aes_decrypt(raw_payload)
                    if self.debug:
                        log.debug("  decrypted: %s", raw_payload[:100])
                except Exception as e:
                    log.warning("decrypt failed on vcid %d: %s", vcid, e)
                    continue

            payload = raw_payload
            try:
                text = payload.decode('utf-8')
                msg = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError):
                # retry stripping u16 LE length prefix
                if len(raw_payload) >= 2:
                    dg_len = struct.unpack_from('<H', raw_payload, 0)[0]
                    payload = raw_payload[2:2 + dg_len]
                try:
                    text = payload.decode('utf-8')
                    msg = json.loads(text)
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    log.warning("non-JSON payload on vcid %d: %r", vcid, raw_payload)
                    continue

            # notifications carry "method" but no "id"
            if "method" in msg and "id" not in msg:
                log.info("RX notification: %s(%s)",
                         msg["method"], json.dumps(msg.get("params", {}))[:100])
                if self._notification_cb:
                    self._notification_cb(msg)
                continue

            if self.debug:
                log.debug("  JSON response: %s", json.dumps(msg)[:300])
            self._response_data = msg
            self._response_event.set()

    async def _send_raw(self, data: bytes):
        chunk_size = max(self._mtu, 20)
        for offset in range(0, len(data), chunk_size):
            chunk = data[offset:offset + chunk_size]
            if self.debug:
                log.debug("TX chunk (%d/%d bytes): %s",
                          len(chunk), len(data), chunk.hex())
            await self._client.write_gatt_char(TX_CHAR_UUID, chunk, response=True)

    # RPC method -> version string carried in the "jsonrpc" field
    RPC_VERSIONS = {
        "GetDateTime": "1.0", "SetDateTime": "1.1", "GetVersion": "2.0",
        "StartStream": "1.0", "InitiateUpgrade": "1.0", "UpgradeDataBlock": "1.0",
        "CheckUpgradeFile": "1.0", "ApplyUpgrade": "1.1", "GetLedStatus": "1.0",
        "EnterStandby": "1.0", "EnterTherapy": "1.0", "SetNextPowerUpDateTime": "1.0",
        "SubscribeEvent": "1.0", "EraseData": "1.0", "ResetDevice": "1.0",
        "StoreSecurityData": "1.0", "EnterMaskFit": "2.0",
        "ApplyAuthenticatedUpgrade": "1.0", "Get": "1.0", "Set": "1.0",
        "VerifySecurityData": "1.0", "GenerateAuthCode": "1.1",
        "ClearAutoConnectList": "1.0", "DiscardPairKey": "1.0",
        "StartSpool": "1.0", "PullSpoolFragments": "1.0",
        "EnterTestDrive": "1.0", "EnableSecurity": "1.0",
    }

    async def send_rpc(self, method: str, params=None, timeout: float = 60.0,
                       encrypted: bool = False, vcid_override: int = None,
                       length_prefix: bool = True, hmac_key: bytes = None) -> dict:
        self._rpc_id += 1
        version = self.RPC_VERSIONS.get(method, "2.0")
        msg = {"id": self._rpc_id, "jsonrpc": version, "method": method}
        if params:
            msg["params"] = params

        json_bytes = json.dumps(msg, separators=(',', ':')).encode('utf-8')

        if encrypted and self._session_key:
            payload = self._aes_encrypt(json_bytes, length_prefix=length_prefix)
            if hmac_key:
                h = hmac.HMAC(hmac_key, hashes.SHA256())
                h.update(payload)
                payload = payload + h.finalize()
            vcid = vcid_override or FIG_VCID_RPC_ENC
        else:
            payload = json_bytes
            vcid = vcid_override or FIG_VCID_RPC

        packet = FigCodec.encode(vcid, payload)

        log.info("RPC >>> %s(%s)", method, json.dumps(params or {}))
        if self.debug:
            log.debug("TX packet (%d bytes): %s", len(packet), packet.hex())

        self._response_event.clear()
        self._response_data = None

        await self._send_raw(packet)

        # let the event loop process pending notifications
        await asyncio.sleep(0.1)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"no response to {method} within {timeout}s")

        resp = self._response_data
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(f"RPC error {err.get('code', '?')}: {err.get('message', '?')}")

        log.info("RPC <<< %s", json.dumps(resp.get("result", resp))[:200])
        return resp

    async def reconnect(self, client_id: str, master_pair_key: str) -> dict:
        """Re-establish encrypted session from stored credentials.

        RequestSession(clientId) -> {challenge, nonce}
        response = HMAC-SHA256(K, challenge)
        CheckSessionIntegrity(response)
        session_key = SHA256(K || nonce)

        K = masterPairKey = H(pad(S)) from the original SRP exchange.
        """
        log.info("reconnect: RequestSession clientId=%s...", client_id[:8])
        resp = await self.send_rpc_raw("RequestSession", {"clientId": client_id}, timeout=10.0)

        if not resp or "error" in resp:
            err = (resp or {}).get("error", {"message": "no response"})
            raise RuntimeError(f"RequestSession failed: {err}")

        result = resp.get("result", {})
        challenge_hex = result.get("challenge", "")
        nonce_hex = result.get("nonce", "")
        if not challenge_hex or not nonce_hex:
            raise RuntimeError("RequestSession: missing challenge/nonce")

        log.info("reconnect: challenge=%s... nonce=%s...", challenge_hex[:16], nonce_hex[:16])

        K_bytes = bytes.fromhex(master_pair_key)
        challenge_bytes = bytes.fromhex(challenge_hex)
        h = hmac.HMAC(K_bytes, hashes.SHA256())
        h.update(challenge_bytes)
        response_hex = h.finalize().hex().upper()
        log.info("reconnect: response=%s...", response_hex[:16])

        resp2 = await self.send_rpc_raw("CheckSessionIntegrity", {"response": response_hex}, timeout=10.0)
        if not resp2 or "error" in resp2:
            err = (resp2 or {}).get("error", {"message": "no response"})
            raise RuntimeError(f"CheckSessionIntegrity failed: {err}")

        log.info("reconnect: session verified")

        nonce_bytes = bytes.fromhex(nonce_hex)
        aes_key = H(K_bytes, nonce_bytes)
        aes_key_hex = aes_key.hex().upper()
        self.set_session_key(aes_key_hex)
        log.info("reconnect: AES key=%s...", aes_key_hex[:16])

        return {"clientId": client_id, "sessionKey": aes_key_hex[:32], "nonce": nonce_hex}

    async def send_rpc_raw(self, method: str, params: dict = None, timeout: float = 10.0) -> dict:
        """send_rpc without error-raising, returns raw response dict or None on timeout."""
        self._rpc_id += 1
        # "id" field first, matches myAir app packet layout
        msg = {"id": self._rpc_id, "jsonrpc": "2.0", "method": method}
        if params:
            msg["params"] = params

        payload = json.dumps(msg, separators=(',', ':')).encode('utf-8')
        packet = FigCodec.encode(FIG_VCID_RPC, payload)

        log.info("RPC >>> %s(%s)", method, json.dumps(params or {}))
        if self.debug:
            log.debug("TX packet (%d bytes): %s", len(packet), packet.hex())

        self._response_event.clear()
        self._response_data = None
        await self._send_raw(packet)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

        return self._response_data

    async def pair(self, passkey: str = None) -> dict:
        """SRP key exchange using the 4-digit passkey shown on the device screen.

        StartKeyExchange(A) -> {B, salt}
        ConfirmKeyExchange(M1) -> {M2, clientId, nonce}
        session_key = SHA256(K || nonce)
        """
        if passkey is None:
            passkey = input("Enter passkey shown on device screen: ").strip()
            if not passkey:
                raise RuntimeError("no passkey entered")

        log.info("SRP: generating keypair with passkey '%s'", passkey)
        srp = SRPClient(passkey)
        log.info("SRP: A = %s...", srp.public_key_hex[:32])

        resp = await self.send_rpc("StartKeyExchange", {"clientPk": srp.public_key_hex})
        if resp is None:
            raise RuntimeError("no response to StartKeyExchange")
        if "error" in resp:
            raise RuntimeError("StartKeyExchange error: %s" % resp["error"])

        result = resp.get("result", {})
        server_pk = result.get("serverPk", "")
        salt = result.get("salt", "")
        log.info("SRP: B = %s...", server_pk[:32])
        log.info("SRP: salt = %s", salt)

        srp.process(server_pk, salt)
        log.info("SRP: K = %s...", srp.session_key_hex[:32])
        log.info("SRP: M1 = %s...", srp.client_proof_hex[:32])

        resp2 = await self.send_rpc("ConfirmKeyExchange", {"clientConfirmation": srp.client_proof_hex})
        if resp2 is None:
            raise RuntimeError("no response to ConfirmKeyExchange")
        if "error" in resp2:
            raise RuntimeError("ConfirmKeyExchange error: %s" % resp2["error"])

        result2 = resp2.get("result", {})
        log.info("SRP: paired! result: %s", json.dumps(result2)[:200])

        nonce = result2.get("nonce", "")
        aes_key_hex = srp.derive_session_key(nonce)
        self.set_session_key(aes_key_hex)
        log.info("AES key: %s...", aes_key_hex[:32])

        return {
            "clientId": result2.get("clientId", ""),
            "masterPairKey": srp.session_key_hex,
            "sessionKey": aes_key_hex[:32],
            "serverPk": server_pk,
            "nonce": result2.get("nonce", ""),
            "serverConfirmation": result2.get("serverConfirmation", ""),
        }


MAC_RE  = re.compile(r'^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$')
UUID_RE = re.compile(r'^[0-9A-Fa-f]{8}-([0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}$')


def load_all_credentials() -> dict:
    if not CRED_FILE.exists():
        return {}
    return json.loads(CRED_FILE.read_text())

def save_all_credentials(all_creds: dict):
    CRED_FILE.write_text(json.dumps(all_creds, indent=2))

def save_credentials(address: str, creds: dict):
    all_creds = load_all_credentials()
    existing = all_creds.get(address, {})
    existing.update(creds)
    all_creds[address] = existing
    save_all_credentials(all_creds)
    log.info("credentials saved to %s", CRED_FILE)

def load_credentials(address: str) -> dict:
    return load_all_credentials().get(address, {})

def resolve_addr(arg: str = None) -> str:
    """MAC/UUID -> as-is (MAC uppercased). Alias -> looked up from credentials.
    None falls back to $AS11_ADDR."""
    if arg is None:
        arg = os.environ.get("AS11_ADDR")
    if not arg:
        raise SystemExit("no address: pass --addr or set AS11_ADDR")

    if MAC_RE.match(arg):
        return arg.upper()
    if UUID_RE.match(arg):
        return arg

    # alias lookup
    for addr, data in load_all_credentials().items():
        if data.get("alias") == arg:
            return addr
    raise SystemExit(f"no MAC/UUID/alias matched: {arg!r}")


async def cmd_scan(args):
    print("Scanning for AS11 devices...")
    devices = await As11Connection.scan(timeout=args.timeout)
    if not devices:
        print("No devices found.")
        return
    for addr, name, rssi in sorted(devices, key=lambda x: -x[2]):
        print(f"  {addr}  {name:<20s}  RSSI {rssi}")

async def cmd_pair(args):
    addr = resolve_addr(args.addr)
    conn = As11Connection(debug=args.debug)
    try:
        await conn.connect(addr)
        creds = await conn.pair()
        save_credentials(addr, creds)
        print("Paired successfully. Credentials saved.")
        print("  clientId:       %s" % creds['clientId'])
        print("  masterPairKey:  %s..." % creds['masterPairKey'][:16])
        print("  sessionKey:     %s..." % creds['sessionKey'][:16])

        # smoke-test the encrypted channel
        print("\nTesting encrypted GetVersion...")
        try:
            resp = await conn.send_rpc("GetVersion", encrypted=True)
            print("GetVersion: %s" % json.dumps(resp.get("result", resp))[:200])
        except Exception as e:
            print("GetVersion failed: %s" % e)

        print("\nTesting encrypted Get(SetPressure)...")
        try:
            resp = await conn.send_rpc("Get", {"name": "SetPressure"}, encrypted=True)
            print("SetPressure: %s" % json.dumps(resp.get("result", resp))[:200])
        except Exception as e:
            print("Get(SetPressure) failed: %s" % e)
    finally:
        await conn.disconnect()

async def cmd_rpc(args):
    addr = resolve_addr(args.addr)
    conn = As11Connection(debug=args.debug)
    try:
        await conn.connect(addr)

        creds = load_credentials(addr)
        if creds.get("clientId") and creds.get("masterPairKey"):
            try:
                new_creds = await conn.reconnect(creds["clientId"], creds["masterPairKey"])
                creds.update(new_creds)
                save_credentials(addr, creds)
            except Exception as e:
                print(f"Reconnect failed ({e}), need to re-pair.", file=sys.stderr)
                return
        else:
            print("No stored credentials. Run 'pair' first.", file=sys.stderr)
            return

        # raw hex: encrypted binary payload, bypasses JSON-RPC
        if getattr(args, 'raw_hex', None):
            raw = bytes.fromhex(args.raw_hex)
            payload = conn._aes_encrypt(raw)
            vcid = args.vcid or 0x0395

            if getattr(args, 'hmac_auth', False):
                K_bytes = bytes.fromhex(creds.get("masterPairKey", ""))
                h = hmac.HMAC(K_bytes, hashes.SHA256())
                h.update(payload)
                payload = payload + h.finalize()
            packet = FigCodec.encode(vcid, payload)
            log.info("TX raw %d bytes on vcid 0x%04x", len(raw), vcid)
            conn._response_event.clear()
            conn._response_data = None

            def on_raw(msg):
                print(json.dumps(msg, separators=(',', ':')), flush=True)
            conn._notification_cb = on_raw

            await conn._send_raw(packet)
            try:
                await asyncio.wait_for(conn._response_event.wait(), timeout=10.0)
                print(json.dumps(conn._response_data, indent=2))
            except asyncio.TimeoutError:
                # non-JSON response may have arrived on a different VCID
                await asyncio.sleep(2)
                print("No JSON response (check stderr for non-JSON payloads)", file=sys.stderr)
            return

        params = json.loads(args.params) if args.params else None
        encrypt = not getattr(args, 'no_encrypt', False)
        lp = not getattr(args, 'no_length_prefix', False)
        hk = bytes.fromhex(creds.get("masterPairKey", "")) if getattr(args, 'hmac', False) else None
        try:
            resp = await conn.send_rpc(args.method, params, encrypted=encrypt,
                                        vcid_override=args.vcid, length_prefix=lp, hmac_key=hk)
            print(json.dumps(resp.get("result", resp), indent=2))
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        except TimeoutError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
    finally:
        await conn.disconnect()


async def cmd_stream(args):
    addr = resolve_addr(args.addr)
    conn = As11Connection(debug=args.debug)
    try:
        await conn.connect(addr)
        creds = load_credentials(addr)
        if not (creds.get("clientId") and creds.get("masterPairKey")):
            print("No stored credentials. Run 'pair' first.", file=sys.stderr)
            return
        new_creds = await conn.reconnect(creds["clientId"], creds["masterPairKey"])
        creds.update(new_creds)
        save_credentials(addr, creds)

        # NDJSON to stdout, one notification per line
        def on_notify(msg):
            print(json.dumps(msg, separators=(',', ':')), flush=True)
        conn._notification_cb = on_notify

        data_ids = args.data_ids.split(",") if args.data_ids else [
            "InspiratoryPressure-50hz", "Leak-TwoSecond", "RemainingRampTime"
        ]

        resp = await conn.send_rpc("StartStream", {
            "dataIds": data_ids,
            "sampleIntervalMs": args.sample_ms,
            "reportIntervalMs": args.report_ms,
        }, encrypted=True)
        print(json.dumps(resp.get("result", resp)), file=sys.stderr)

        try:
            while conn._client and conn._client.is_connected:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
    except KeyboardInterrupt:
        pass
    finally:
        # stop stream on exit
        try:
            await conn.send_rpc("StartStream", {
                "dataIds": [],
                "sampleIntervalMs": args.sample_ms,
                "reportIntervalMs": args.report_ms,
            }, encrypted=True, timeout=5.0)
        except Exception:
            pass
        await conn.disconnect()


async def cmd_subscribe(args):
    addr = resolve_addr(args.addr)
    conn = As11Connection(debug=args.debug)
    try:
        await conn.connect(addr)
        creds = load_credentials(addr)
        if not (creds.get("clientId") and creds.get("masterPairKey")):
            print("No stored credentials. Run 'pair' first.", file=sys.stderr)
            return
        new_creds = await conn.reconnect(creds["clientId"], creds["masterPairKey"])
        creds.update(new_creds)
        save_credentials(addr, creds)

        def on_notify(msg):
            print(json.dumps(msg, separators=(',', ':')), flush=True)
        conn._notification_cb = on_notify

        data_ids = args.events.split(",") if args.events else []
        resp = await conn.send_rpc("SubscribeEvent", {
            "dataIds": data_ids,
        }, encrypted=True)
        print(json.dumps(resp.get("result", resp)), file=sys.stderr)

        try:
            while conn._client and conn._client.is_connected:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
    except KeyboardInterrupt:
        pass
    finally:
        await conn.disconnect()


SPOOL_TYPES = [
    # session & usage
    "Summary",
    "UsageEvents-TherapyStatusEvents",
    "TherapyEvents-RespiratoryEvents",
    "TherapyOneMinutePeriodic",
    "SettingProfilesCollection",
    "ConfigurationProfilesCollection",
    # system state / activity
    "SystemActivityEvents-FrequentActivityEvents",
    "SystemActivityEvents-SporadicActivityEvents",
    "SystemExceptionEvents-SystemErrors",
    "SystemExceptionEvents-RecoverableErrors",
    "SystemExceptionEvents-HumidifierErrors",
    "SystemExceptionEvents-HeatedTubeErrors",
    "DiagnosticExceptionEvents-AppErrors",
    "DiagnosticExceptionEvents-FatalErrors",
    "DiagnosticExceptionEvents-ResettableErrors",
    "DiagnosticExceptionEvents-AlarmAppErrors",
    "DiagnosticTenMinutePeriodic",
    # alarms
    "alarmEvents",
    "alarmDiagnosticEvents",
    # ui / survey / checks
    "GUIActivityEvents",
    "SurveyEvents",
    "SoundcheckVector",
    "AcousticSignatureV2",
    # metrics
    "MachineMetrics",
    "MemoryMetrics",
    "CellularActivityEvents",
    "CellularDataUsage",
    # high-rate / ambient signals
    "atmosphericPressure10min",
    "RespiratoryFlow6p25Hz",
    "MaskPressure6p25Hz",
    "InspiratoryPressure0p5Hz",
    "Leak0p5Hz",
]

STREAM_DATA_IDS = [
    "AmbientHumidity-Estimated", "AmbientTemperature-Estimated",
    "ApneaTreatmentPressure-50hz", "AutoSetTreatmentPressure-50hz",
    "BlowerFlow-100hz", "BlowerPressure-100hz", "BlowerPressure-OneMinute",
    "ExpiratoryPressure-50hz", "ExpiratoryPressure-TwoSecond",
    "FlowLimitation-50hz", "FlowLimitationTreatmentPressure-50hz",
    "InspiratoryPressure-50hz", "InspiratoryPressure-OneMinute",
    "InspiratoryPressure-TwoSecond",
    "Leak-50hz",
    "MaskPressure-100hz", "MaskPressure-OneMinute", "MaskPressure-TwoSecond",
    "MinuteVentilation-50hz", "PatientFlow-100hz",
    "RawLeak-50hz", "RemainingRampTime-50hz",
    "RespiratoryRate-50hz", "SetPressure-100hz",
    "SnoreIndex-50hz", "SnoreTreatmentPressure-50hz", "TidalVolume-50hz",
]

EVENT_IDS = [
    # mask / therapy lifecycle
    "MaskFitStart", "MaskFitStop", "MaskOn", "MaskOff",
    "MaskReminderAcknowledged",
    "PressureStart", "PressureStop",
    "RampDownStarted", "RampDownCompleted",
    # sensor / hardware anomalies
    "PressureStuckHigh", "PressureStuckLow", "PressureStuckMid",
    "PressureSensorDrift", "PressureSensorsPlausibility",
    "SensorFail",
    # alarm subsystem
    "AlarmImageRestored", "AlarmMuteState",
    "AlarmModuleCommunicationError", "AlarmSelfTestFailure",
    # upgrade lifecycle
    "AlarmUpgradeInitiated", "AlarmUpgradeSuccessful", "AlarmUpgradeFailed",
    "AlarmUpgradeFileTransferRequested",
    "AlarmUpgradeFileTransferCompleted", "AlarmUpgradeFileTransferFailed",
    "AlarmUpgradeFileSignatureMismatch",
    "UpgradePrepStarted",
    # device check
    "DeviceCheckInitiated", "DeviceCheckPassed", "DeviceCheckSystemError",
    "DeviceCheckNotificationDisplayed",
    # system errors
    "SystemErrorStarted",
    "SystemErrorCalibrationReset", "SystemErrorSettingsReset",
    "SystemErrorFastOverPressure", "SystemErrorSlowOverPressure",
    "SystemErrorOverTemperature", "SystemErrorOverVoltage",
    "SystemErrorImplausibleSupplyVoltage",
    "SystemErrorFaultyHWFaultDetectionCircuitry",
    "SystemErrorFlowSensorStuckHigh", "SystemErrorFlowSensorStuckLow",
    "SystemErrorNoFlowData",
    "SystemErrorPressureSensorDrift", "SystemErrorPressureSensorsPlausibility",
    "SystemErrorPressureStuckHigh", "SystemErrorPressureStuckLow",
    "SystemErrorPressureStuckMid",
    "SystemErrorMotorESD", "SystemErrorMotorFETs",
    "SystemErrorMotorHwFault", "SystemErrorMotorHwMitigationIC",
    "SystemErrorMotorStallHW", "SystemErrorMotorStallSW",
    "SystemErrorMotorSticky",
    # notifications observed on the wire
    "SpoolFragment",
]

VAR_NAMES = [
    ("ASV-MaxPressureSupport", "XC2"),
    ("ASV-MinPressureSupport", "XC3"),
    ("ASV-StartPressure", "XC0"),
    ("ASV-TargetExpiratoryPressure", "XC1"),
    ("ASVAuto-MaxExpiratoryPressure", "XD1"),
    ("ASVAuto-MaxPressureSupport", "XD3"),
    ("ASVAuto-MinExpiratoryPressure", "XD2"),
    ("ASVAuto-MinPressureSupport", "XD4"),
    ("ASVAuto-StartPressure", "XD0"),
    ("AccessPointName", "CLA"),
    ("ActiveAlarms", "AER"),
    ("ActiveTherapyProfile", "MOP"),
    ("AdcPressure", "PRS"),
    ("AdcPressureMonitoring", "PR2"),
    ("AlarmVolumeLevel", "AVQ"),
    ("AlveolarMinuteVentilation", "AAV"),
    ("AmbientHumidity-Estimated", "ABH"),
    ("AmbientLight", "ALS"),
    ("AmbientTemperature-Estimated", "HAT"),
    ("AntiBacterialFilter", "ABF"),
    ("ApneaAlarmEnable", "ANC"),
    ("ApneaAlarmThreshold", "APV"),
    ("ApneaTreatmentPressure-50hz", "AP5"),
    ("ApplicationData", "MAD"),
    ("ApplicationIdentifier", "SID"),
    ("AutoSet-MaxPressure", "MPA"),
    ("AutoSet-MinPressure", "MPI"),
    ("AutoSet-StartPressure", "STU"),
    ("AutoSetComfort", "AFC"),
    ("AutoSetTreatmentPressure-50hz", "AT5"),
    ("BlowerFlow-100hz", "BFT"),
    ("BlowerPressure-100hz", "BPT"),
    ("BlowerPressure-OneMinute", "BPA"),
    ("BlowerPressureMonitoring", "BPS"),
    ("BluetoothApplicationIdentifier", "BTV"),
    ("BluetoothBootloaderIdentifier", "BBV"),
    ("BluetoothName", "BTN"),
    ("BluetoothPassthrough", "BNP"),
    ("BluetoothProductModel", "BPM"),
    ("BluetoothProductProvider", "BPP"),
    ("BootloaderIdentifier", "BID"),
    ("ButtonRegMap", "KPT"),
    ("CALEnable", "MEN"),
    ("CALStatus", "CST"),
    ("CalManufacturingMode", "CMM"),
    ("CalibrationPressure", "CPR"),
    ("CamlData", "CMD"),
    ("CareCheckInAvailable", "CCA"),
    ("CareCheckToggle", "MAI"),
    ("CellularApplicationIdentifier", "CSI"),
    ("CellularDataPreamble", "CDP"),
    ("CellularProductModel", "CPM"),
    ("CellularProductProvider", "CPP"),
    ("CepstrumAverageCount", "EIC"),
    ("CepstrumStartDelay", "EST"),
    ("ClimateControl", "CCO"),
    ("ClinicalConfirmation", "CFC"),
    ("ConfigurationIdentifier", "CID"),
    ("ConfirmStopEnable", "SCF"),
    ("Cpap-SetPressure", "IPC"),
    ("Cpap-StartPressure", "STP"),
    ("Cpap-TriggerSensitivity", "C11"),
    ("CpapSetPressure", "CSP"),
    ("CurrentLEDState", "CLS"),
    ("CycleDisplayFormat", "SSY"),
    ("DataCollectAndSend", "DSS"),
    ("DataCollectAndSendAsync", "ADS"),
    ("DataMode", "CDM"),
    ("DataModelVersionIdentifier", "DMV"),
    ("DataVersionIdentifier", "PVD"),
    ("DeviceIdStatus", "DIS"),
    ("DisplayAHI", "DAH"),
    ("DownloadBytesDelta", "DDD"),
    ("EndCapDetection", "ECD"),
    ("EprEnable", "EPX"),
    ("EprEnablePatientAccess", "EPA"),
    ("EprPressure", "EPR"),
    ("EprType", "EPT"),
    ("EraseMediaSignature", "EMS"),
    ("ExpirationSetPressure", "ESP"),
    ("ExpiratoryDuration", "EXT"),
    ("ExpiratoryPressure", "EXP"),
    ("ExpiratoryPressure-50hz", "EP5"),
    ("ExpiratoryPressure-TwoSecond", "MKE"),
    ("ExternalHumidifier", "EXH"),
    ("FGState", "ZRM"),
    ("FdaUniqueDeviceIdentifier", "UDI"),
    ("FlightMode", "QFC"),
    ("FlowGain", "FLG"),
    ("FlowLimitation", "FFL"),
    ("FlowLimitation-50hz", "FF5"),
    ("FlowLimitationTreatmentPressure-50hz", "FL5"),
    ("FlowOffset", "FLZ"),
    ("HardwareIdentifier", "PCB"),
    ("HeartRate", "HRT"),
    ("HeatedTubeCurrent", "HTL"),
    ("HeatedTubeOutletTemperature", "HTT"),
    ("HeatedTubeOutletTemperatureMinuteAverage", "HTA"),
    ("HeatedTubePWM", "HBP"),
    ("HeatedTubePWMMinuteAverage", "ABP"),
    ("HeatedTubePower", "HTP"),
    ("HeatedTubeSettingEnable", "HTX"),
    ("HeatedTubeTemperature", "HTS"),
    ("HeightDisplayUnit", "IHU"),
    ("HerAuto-MaxPressure", "HMA"),
    ("HerAuto-MinPressure", "HMI"),
    ("HerAuto-StartPressure", "HSP"),
    ("HighLeakAlarmEnable", "HLA"),
    ("HumidifierConnected", "HCR"),
    ("HumidifierLevel", "HMS"),
    ("HumidifierPWM", "HUP"),
    ("HumidifierPWMMinuteAverage", "AHP"),
    ("HumidifierPlateCurrent", "HCL"),
    ("HumidifierPlateTemperature", "HPT"),
    ("HumidifierPlateTemperatureMinuteAverage", "HHT"),
    ("HumidifierPower", "HPW"),
    ("HumidifierSettingEnable", "HMX"),
    ("IMEI", "CIE"),
    ("IMSI", "CIM"),
    ("IeRatio", "IET"),
    ("InspirationSetPressure", "ISP"),
    ("InspiratoryDuration", "INT"),
    ("InspiratoryPressure", "INP"),
    ("InspiratoryPressure-50hz", "INH"),
    ("InspiratoryPressure-OneMinute", "AIP"),
    ("InspiratoryPressure-TwoSecond", "MKI"),
    ("IsFileSystemReady", "IRF"),
    ("IsRamping", "ZRP"),
    ("IsRampingDown", "RPD"),
    ("IsReadyForShipping", "IRS"),
    ("IsReadyForUpgrade", "IRU"),
    ("LCDConnector", "LCS"),
    ("LCDTouchStatus", "LTS"),
    ("Language", "LAN"),
    ("LanguageConfiguration", "LNC"),
    ("LanguageSelection", "SLS"),
    ("LastDataPostDateTime", "LDT"),
    ("LastEraseDataDateTime", "CED"),
    ("LastMachineServiceDateTime", "LMS"),
    ("LastTherapyUseDateTime", "CUD"),
    ("Leak", "LKF"),
    ("Leak-50hz", "LK5"),
    ("LearnMode", "TLM"),
    ("LearnTargetsExpiratoryPressure", "ZIE"),
    ("LearnTargetsPressureSupport", "ZLP"),
    ("LearnTargetsSetDuration", "ZIC"),
    ("LowMinuteVentAlarmEnable", "LMC"),
    ("LowMinuteVentAlarmThreshold", "LMT"),
    ("MachineRunMeter", "MHU"),
    ("MaskPressure", "MKP"),
    ("MaskPressure-100hz", "MK1"),
    ("MaskPressure-OneMinute", "MAP"),
    ("MaskPressure-TwoSecond", "MKF"),
    ("MaskSenseToggle", "MKD"),
    ("MaskType", "MSK"),
    ("MaxRampDownTime", "MRD"),
    ("MaxRampTime", "MRT"),
    ("MicrophoneEnabled", "MIC"),
    ("MinuteVentilation", "MV6"),
    ("MinuteVentilation-50hz", "MVH"),
    ("MotorCurrent", "CUR"),
    ("MotorFlowDrive", "CFL"),
    ("MotorRunMeter", "MHR"),
    ("MotorRunSinceLastServiceMeter", "MHS"),
    ("MotorSpeed", "SPD"),
    ("MotorType", "BMT"),
    ("MyAirScreens", "MAS"),
    ("NonVentedMaskAlarmEnable", "NMA"),
    ("OobxOnStartup", "SOS"),
    ("OtaUpgradeStatus", "OUS"),
    ("PAC-FallTime", "P12"),
    ("PAC-FallTimeEnable", "P11"),
    ("PAC-RiseTime", "PA4"),
    ("PAC-RiseTimeEnable", "PA3"),
    ("PAC-SetInspiratoryTime", "PA5"),
    ("PAC-SetRespiratoryRate", "PA6"),
    ("PAC-StartPressure", "PA0"),
    ("PAC-TargetExpiratoryPressure", "PA2"),
    ("PAC-TargetInspiratoryPressure", "PA1"),
    ("PAC-TriggerSensitivity", "PA7"),
    ("PatientFlow", "RFL"),
    ("PatientFlow-100hz", "RF5"),
    ("PatientView", "ACC"),
    ("PeriodicBrokerContactPeriod", "BCP"),
    ("PeripheralMsg", "PMS"),
    ("PhantomKey", "KEY"),
    ("PhantomTouch", "TCH"),
    ("PlatformIdentifier", "MID"),
    ("PowerSupplyCapacity", "PSC"),
    ("PowerSupplyType", "PSU"),
    ("PressureGain", "PSH"),
    ("PressureMonitorGain", "PS1"),
    ("PressureMonitorOffset", "PZ1"),
    ("PressureOffset", "PZH"),
    ("ProductCode", "PCD"),
    ("ProductGeographicIdentifier", "PGI"),
    ("ProductName", "PNA"),
    ("ProfileVariantIdentifier", "PVI"),
    ("RampDownEnable", "RDE"),
    ("RampDownEnablePatientAccess", "DPE"),
    ("RampDownTime", "SRT"),
    ("RampEnable", "RMA"),
    ("RampEnablePatientAccess", "RPE"),
    ("RampTime", "RMT"),
    ("RawAmbHumidity", "AHR"),
    ("RawAmbLight", "RAL"),
    ("RawAmbTemperature", "ATR"),
    ("RawFlow", "FLW"),
    ("RawLeak", "SFK"),
    ("RawLeak-50hz", "SF5"),
    ("RecoverableError", "RYS"),
    ("RegionIdentifier", "RID"),
    ("RemainingRampDownTime", "RDD"),
    ("RemainingRampTime", "ZRC"),
    ("RemainingRampTime-50hz", "ZR5"),
    ("ReminderFilterDate", "RTF"),
    ("ReminderFilterEnable", "RIF"),
    ("ReminderFilterPeriod", "RDF"),
    ("ReminderHumidifierDate", "RTH"),
    ("ReminderHumidifierEnable", "RIC"),
    ("ReminderHumidifierPeriod", "RDH"),
    ("ReminderMaskDate", "RTM"),
    ("ReminderMaskEnable", "RIM"),
    ("ReminderMaskPeriod", "RDM"),
    ("ReminderTubingDate", "RTT"),
    ("ReminderTubingEnable", "RIT"),
    ("ReminderTubingPeriod", "RDT"),
    ("RequestLCDColour", "RLC"),
    ("RequestLEDState", "RLS"),
    ("RequestSDCardTest", "RST"),
    ("RequestTestDriveState", "RTS"),
    ("RespiratoryEvent", "AET"),
    ("RespiratoryRate", "RR6"),
    ("RespiratoryRate-50hz", "RR5"),
    ("SDCardSocketStatus", "SSS"),
    ("SDCardTestStatus", "STS"),
    ("SIMID", "CCD"),
    ("ST-CycleSensitivity", "XAB"),
    ("ST-FallTime", "XAP"),
    ("ST-FallTimeEnable", "XAM"),
    ("ST-IntelligentBackupRateEnable", "XAC"),
    ("ST-RiseTime", "XAA"),
    ("ST-RiseTimeEnable", "XA9"),
    ("ST-SetMaxInspiratoryTime", "XA7"),
    ("ST-SetMinInspiratoryTime", "XA8"),
    ("ST-SetRespiratoryRate", "XA6"),
    ("ST-StartPressure", "XA3"),
    ("ST-TargetExpiratoryPressure", "XA2"),
    ("ST-TargetInspiratoryPressure", "XA1"),
    ("ST-TargetRespiratoryRate", "XAD"),
    ("ST-TriggerSensitivity", "ZU1"),
    ("SecurityStatus", "SBE"),
    ("SerialNumber", "SRN"),
    ("ServiceHost", "CLU"),
    ("ServicePort", "CLP"),
    ("SetMotorSpeed", "SSD"),
    ("SetPressure-100hz", "SPH"),
    ("SetPressureWithoutCAD", "OPP"),
    ("SettingsHistoryChangeCount", "SHC"),
    ("SmartStart", "SST"),
    ("SmartStop", "SSP"),
    ("SnoreIndex", "SNI"),
    ("SnoreIndex-50hz", "SN5"),
    ("SnoreTreatmentPressure-50hz", "SR5"),
    ("SoundDownloadAllowed", "DSA"),
    ("SoundcheckFeatureToggle", "SCO"),
    ("SoundcheckRunFrequency", "SCK"),
    ("SoundcheckStatus", "STT"),
    ("SoundcheckTestCount", "SSC"),
    ("SpO2", "SAO"),
    ("SplashScreenDisplaySelection", "SSE"),
    ("Spont-CycleSensitivity", "Z12"),
    ("Spont-EasyBreatheEnable", "ZZ4"),
    ("Spont-FallTime", "Z17"),
    ("Spont-FallTimeEnable", "Z16"),
    ("Spont-RespiratoryRateEnable", "ZZ5"),
    ("Spont-RiseTime", "Z10"),
    ("Spont-RiseTimeEnable", "ZZ9"),
    ("Spont-SetMaxInspiratoryTime", "ZZ7"),
    ("Spont-SetMinInspiratoryTime", "ZZ8"),
    ("Spont-StartPressure", "ZZ3"),
    ("Spont-TargetExpiratoryPressure", "ZZ2"),
    ("Spont-TargetInspiratoryPressure", "ZZ1"),
    ("Spont-TriggerSensitivity", "Z11"),
    ("StatusEvent", "THS"),
    ("StorageVersionId", "SVD"),
    ("Summary-AmbientHumidity-50", "AUM"),
    ("Summary-ApneaHypopneaIndex", "AHI"),
    ("Summary-ApneaIndex", "ASC"),
    ("Summary-BlowerFlow-50", "BFM"),
    ("Summary-BlowerPressure-5", "BP5"),
    ("Summary-BlowerPressure-95", "BP9"),
    ("Summary-CentralApneaIndex", "OSC"),
    ("Summary-ExpiratoryPressure-100", "PEA"),
    ("Summary-ExpiratoryPressure-50", "PEM"),
    ("Summary-ExpiratoryPressure-95", "PE9"),
    ("Summary-HeartRate-100", "HRX"),
    ("Summary-HeartRate-50", "HRM"),
    ("Summary-HeartRate-95", "HR9"),
    ("Summary-HeatedTubePower-50", "AHM"),
    ("Summary-HeatedTubeTemperature-50", "HTE"),
    ("Summary-HumidifierConnected", "HUC"),
    ("Summary-HumidifierPower-50", "APM"),
    ("Summary-HumidifierTemperature-50", "HHE"),
    ("Summary-HypopneaIndex", "HSC"),
    ("Summary-IeRatio-100", "IEA"),
    ("Summary-IeRatio-50", "IEM"),
    ("Summary-IeRatio-95", "IE9"),
    ("Summary-InspiratoryDuration-100", "ISA"),
    ("Summary-InspiratoryDuration-50", "ISM"),
    ("Summary-InspiratoryDuration-95", "IS9"),
    ("Summary-InspiratoryPressure-100", "PIA"),
    ("Summary-InspiratoryPressure-50", "PIM"),
    ("Summary-InspiratoryPressure-95", "PI9"),
    ("Summary-Leak-100", "LMX"),
    ("Summary-Leak-50", "LKM"),
    ("Summary-Leak-75", "LK7"),
    ("Summary-Leak-95", "LK9"),
    ("Summary-MeanMaskPressure-100", "PMA"),
    ("Summary-MeanMaskPressure-50", "MSP"),
    ("Summary-MeanMaskPressure-95", "PM9"),
    ("Summary-MinuteVentilation-100", "VTA"),
    ("Summary-MinuteVentilation-50", "VTM"),
    ("Summary-MinuteVentilation-95", "VT9"),
    ("Summary-ObstructiveApneaIndex", "CSC"),
    ("Summary-ReraIndex", "RCC"),
    ("Summary-RespiratoryFlow-5", "RFM"),
    ("Summary-RespiratoryFlow-95", "R95"),
    ("Summary-RespiratoryRate-100", "RRA"),
    ("Summary-RespiratoryRate-50", "RRM"),
    ("Summary-RespiratoryRate-95", "RR9"),
    ("Summary-SpO2-100", "SOX"),
    ("Summary-SpO2-50", "SOM"),
    ("Summary-SpO2-95", "SO9"),
    ("Summary-SpontCyclePercentage", "VCR"),
    ("Summary-SpontTriggerPercentage", "VSR"),
    ("Summary-TargetMinuteVentilation-100", "VAA"),
    ("Summary-TargetMinuteVentilation-50", "VAM"),
    ("Summary-TargetMinuteVentilation-95", "VA9"),
    ("Summary-TidalVolume-100", "TVA"),
    ("Summary-TidalVolume-50", "TVM"),
    ("Summary-TidalVolume-95", "TV9"),
    ("Summary-TubeConnected", "ZHT"),
    ("Summary-UnknownApneaIndex", "USC"),
    ("SystemError", "FSE"),
    ("TOTAL_USED_HOURS_NAME", "PHR"),
    ("TargetMinuteVentilation", "TVP"),
    ("TemperatureUnit", "TMU"),
    ("TestDrivePressure", "TDP"),
    ("TestDriveState", "TDS"),
    ("TestDriveType", "TDT"),
    ("TherapyLEDAlwaysOn", "TLF"),
    ("TherapyRunMeter", "PHM"),
    ("TidalVolume", "TID"),
    ("TidalVolume-50hz", "TI5"),
    ("TimeZoneOffset", "TZO"),
    ("Timed-FallTime", "XBA"),
    ("Timed-FallTimeEnable", "XB9"),
    ("Timed-RiseTime", "XB7"),
    ("Timed-RiseTimeEnable", "XB6"),
    ("Timed-SetInspiratoryTime", "XB5"),
    ("Timed-SetRespiratoryRate", "XB4"),
    ("Timed-StartPressure", "XB0"),
    ("Timed-TargetExpiratoryPressure", "XB2"),
    ("Timed-TargetInspiratoryPressure", "XB1"),
    ("TotalUsedHoursDisplayToggle", "TUD"),
    ("TriggerCycleEvent", "BTE"),
    ("TubeConnected", "ZHR"),
    ("TubeType", "TBT"),
    ("TxLink2Connected", "TXC"),
    ("UniversalIdentifier", "GUD"),
    ("UpgradeAbandonPeriod", "OAP"),
    ("UpgradeReportPeriod", "ORP"),
    ("UploadBytesDelta", "DUD"),
    ("VALOTriggerSeconds", "VTD"),
    ("VAuto-CycleSensitivity", "XE7"),
    ("VAuto-MaxInspiratoryPressure", "XE1"),
    ("VAuto-MinExpiratoryPressure", "XE2"),
    ("VAuto-SetMaxInspiratoryTime", "XE4"),
    ("VAuto-SetMinInspiratoryTime", "XE5"),
    ("VAuto-SetPressureSupport", "XE3"),
    ("VAuto-StartPressure", "XE0"),
    ("VAuto-TriggerSensitivity", "XE6"),
    ("VariantIdentifier", "VID"),
    ("iVAPS-AutoEPAPEnable", "IEU"),
    ("iVAPS-CycleSensitivity", "VCS"),
    ("iVAPS-FallTime", "IRL"),
    ("iVAPS-FallTimeEnable", "IRZ"),
    ("iVAPS-MaxExpiratoryPressure", "IMX"),
    ("iVAPS-MaxPressureSupport", "WPA"),
    ("iVAPS-MinExpiratoryPressure", "IMN"),
    ("iVAPS-MinPressureSupport", "WPM"),
    ("iVAPS-PatientHeight", "PHT"),
    ("iVAPS-RiseTime", "IRT"),
    ("iVAPS-RiseTimeEnable", "IRC"),
    ("iVAPS-SetMaxInspiratoryTime", "IVX"),
    ("iVAPS-SetMinInspiratoryTime", "IVN"),
    ("iVAPS-StartPressure", "IVS"),
    ("iVAPS-TargetAlveolarVentilation", "ITV"),
    ("iVAPS-TargetExpiratoryPressure", "EPI"),
    ("iVAPS-TargetRespiratoryRate", "IBR"),
    ("iVAPS-TriggerSensitivity", "VTS"),
]


REGISTRIES = {
    "vars":    (VAR_NAMES,       "variable names (for `get` / `set`)"),
    "streams": (STREAM_DATA_IDS, "stream data IDs (for `stream --data-ids`)"),
    "events":  (EVENT_IDS,       "event IDs (for `subscribe --events`)"),
    "spools":  (SPOOL_TYPES,     "spool types (for `spool`)"),
}

# Therapy-mode prefixes: `known vars cpap` -> Cpap-* (exact prefix match).
VAR_MODE_PREFIXES = {
    "cpap": "Cpap-", "autoset": "AutoSet-", "herauto": "HerAuto-",
    "asv": "ASV-", "asvauto": "ASVAuto-", "vauto": "VAuto-",
    "ivaps": "iVAPS-", "st": "ST-", "spont": "Spont-",
    "timed": "Timed-", "pac": "PAC-",
}

# Topic groups: `known vars summary` -> case-insensitive substring match.
VAR_TOPIC_KEYWORDS = {
    "summary":    ("summary",),
    "alarm":      ("alarm",),
    "ramp":       ("ramp",),
    "humidifier": ("humidifier",),
    "tube":       ("tube",),
    "reminder":   ("reminder",),
    "cellular":   ("cellular", "imei", "imsi", "sim", "accesspoint"),
    "bluetooth":  ("bluetooth",),
    "identifier": ("identifier", "serialnumber", "productcode", "productname"),
    "learn":      ("learn",),
    "streaming":  ("-50hz", "-100hz", "-twosecond", "-oneminute", "-estimated"),
}


def _filter_vars(pat):
    """Group-aware filtering over (name, tag) pairs. Falls back to substring."""
    key = pat.lower()
    if key in VAR_MODE_PREFIXES:
        prefix = VAR_MODE_PREFIXES[key]
        return [(n, t) for n, t in VAR_NAMES if n.startswith(prefix)]
    if key in VAR_TOPIC_KEYWORDS:
        keywords = VAR_TOPIC_KEYWORDS[key]
        return [(n, t) for n, t in VAR_NAMES if any(k in n.lower() for k in keywords)]
    # substring match against either the long name or the _TAG short form
    return [(n, t) for n, t in VAR_NAMES
            if key in n.lower() or key in f"_{t}".lower()]


def _var_groups_summary():
    """Print prefix/topic breakdown with counts."""
    print("therapy modes (exact prefix):")
    for key, prefix in sorted(VAR_MODE_PREFIXES.items()):
        n = sum(1 for name, _ in VAR_NAMES if name.startswith(prefix))
        print(f"  {key:<10}  {prefix:<10}  {n:3d}")
    print()
    print("topics (substring):")
    for key, keywords in sorted(VAR_TOPIC_KEYWORDS.items()):
        n = sum(1 for name, _ in VAR_NAMES if any(k in name.lower() for k in keywords))
        hint = ", ".join(keywords)
        print(f"  {key:<10}  {n:3d}  ({hint})")


def _print_var_pairs(pairs):
    """Two-column output: long name left, _TAG right."""
    if not pairs:
        return
    width = max(len(n) for n, _ in pairs)
    for name, tag in sorted(pairs):
        print(f"{name:<{width}}  _{tag}")


def cmd_known(args):
    action = args.known_action
    if not action:
        for name, (_, desc) in REGISTRIES.items():
            print(f"  {name:<8}  {desc}")
        print()
        print(f"  hint: `known vars groups` lists var subgroupings")
        return

    pat = args.pattern or ""

    # vars has rich filtering and tabular output
    if action == "vars":
        if pat.lower() == "groups":
            _var_groups_summary()
            return
        pairs = _filter_vars(pat) if pat else list(VAR_NAMES)
        _print_var_pairs(pairs)
        return

    items, _ = REGISTRIES[action]
    key = pat.lower()
    for item in sorted(items):
        if not key or key in item.lower():
            print(item)


TYPE_COERCE = {
    "str":   lambda v: v,
    "int":   int,
    "float": float,
    "bool":  lambda v: {"true": True, "1": True, "yes": True,
                        "false": False, "0": False, "no": False}[v.lower()],
    "json":  json.loads,
}

def parse_set_items(items):
    """Walk positional [Name Value (--type T)?]* into [(name, value_str, type)]."""
    pairs = []
    pending = None  # (name, value) awaiting optional --type
    i = 0
    while i < len(items):
        tok = items[i]
        if tok == "--type" or tok.startswith("--type="):
            if pending is None:
                raise SystemExit("--type must follow a name/value pair")
            if tok == "--type":
                if i + 1 >= len(items):
                    raise SystemExit("--type requires a type name")
                t = items[i + 1]
                i += 2
            else:
                t = tok.split("=", 1)[1]
                i += 1
            if t not in TYPE_COERCE:
                raise SystemExit(f"unknown type {t!r}, expected one of {list(TYPE_COERCE)}")
            pairs.append((*pending, t))
            pending = None
        else:
            if pending is not None:
                pairs.append((*pending, "str"))
            if i + 1 >= len(items):
                raise SystemExit(f"value missing for {tok!r}")
            pending = (tok, items[i + 1])
            i += 2
    if pending is not None:
        pairs.append((*pending, "str"))
    return pairs


async def cmd_get(args):
    addr = resolve_addr(args.addr)
    if not args.names:
        raise SystemExit("get: at least one name required")
    conn = As11Connection(debug=args.debug)
    try:
        await conn.connect(addr)
        creds = load_credentials(addr)
        if not (creds.get("clientId") and creds.get("masterPairKey")):
            raise SystemExit("No stored credentials. Run 'devices pair' first.")
        new_creds = await conn.reconnect(creds["clientId"], creds["masterPairKey"])
        creds.update(new_creds)
        save_credentials(addr, creds)
        resp = await conn.send_rpc("Get", list(args.names), encrypted=True)
        print(json.dumps(resp.get("result", resp), indent=2))
    finally:
        await conn.disconnect()


async def cmd_set(args):
    # validate args before touching BLE
    if args.json_payload:
        raw = sys.stdin.read() if args.json_payload == "-" else args.json_payload
        try:
            params = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"--json: invalid JSON ({e})")
        if not isinstance(params, dict):
            raise SystemExit("--json: must be a JSON object")
    else:
        pairs = parse_set_items(args.rest)
        if not pairs:
            raise SystemExit("set: at least one name/value pair required")
        params = {}
        for name, value, t in pairs:
            try:
                params[name] = TYPE_COERCE[t](value)
            except (ValueError, KeyError) as e:
                raise SystemExit(f"{name}: cannot coerce {value!r} as {t} ({e})")

    addr = resolve_addr(args.addr)
    conn = As11Connection(debug=args.debug)
    try:
        await conn.connect(addr)
        creds = load_credentials(addr)
        if not (creds.get("clientId") and creds.get("masterPairKey")):
            raise SystemExit("No stored credentials. Run 'devices pair' first.")
        new_creds = await conn.reconnect(creds["clientId"], creds["masterPairKey"])
        creds.update(new_creds)
        save_credentials(addr, creds)
        resp = await conn.send_rpc("Set", params, encrypted=True)
        print(json.dumps(resp.get("result", resp), indent=2))
    finally:
        await conn.disconnect()


def _proto_read_varint(data, i):
    v = 0; shift = 0
    while True:
        b = data[i]; i += 1
        v |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return v, i
        shift += 7


def _proto_decode(data):
    """Walk protobuf wire format. Returns list of (field, wire, value)."""
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


_PROTO_WIRE = {0: "varint", 1: "64-bit", 2: "bytes", 5: "32-bit"}


def _proto_pretty(data, indent=0, out=None):
    """Pretty-print protobuf blob with nested-message heuristic."""
    from datetime import datetime, timezone
    if out is None:
        out = sys.stdout
    pad = "  " * indent
    for field, wire, value in _proto_decode(data):
        if wire == 2:
            # try nested message
            try:
                sub = _proto_decode(value)
                if sub and all(0 < f < 2**29 for f, _, _ in sub):
                    print(f"{pad}{field} (msg, {len(value)}B):", file=out)
                    _proto_pretty(value, indent + 1, out)
                    continue
            except (ValueError, IndexError):
                pass
            # string vs bytes
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


# Spool-type-specific enum legends
_SPOOL_LEGENDS = {
    "TherapyEvents-RespiratoryEvents": {
        "event_types": {
            2: "Hypopnea", 3: "CentralApnea", 4: "ObstructiveApnea",
            5: "Apnea", 6: "Arousal",
        },
    },
}


# Summary protobuf field table.
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

# Percentile labels per (outer_field, inner_subfield).
_SUMMARY_SUBFIELDS = {
    # outer_f: { sub_f: (pct, multiplier) }
    14: {2: (50, 2.0), 3: (70, 2.0), 4: (95, 2.0), 5: (100, 2.0)},  # Leak (6-slot msg)
    15: {2: (50, 2.0), 3: (95, 2.0), 4: (100, 2.0)},                # InspiratoryPressure
    20: {2: (50, 2.0), 3: (95, 2.0), 4: (100, 2.0)},                # ExpiratoryPressure
    21: {2: (50, 2.0), 3: (95, 2.0), 4: (100, 2.0)},                # MeanMaskPressure
    22: {2: (50, 2.0), 3: (95, 2.0), 4: (100, 2.0)},                # TidalVolume
    23: {2: (50, 8.0), 3: (95, 8.0), 4: (100, 8.0)},                # MinuteVentilation
    24: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},                # TargetMinuteVentilation
    25: {2: (50, 5.0), 3: (95, 5.0), 4: (100, 5.0)},                # RespiratoryRate
    26: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},                # InspiratoryDuration
    27: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},                # IeRatio
    28: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},                # SpO2
    29: {2: (50, 10.0)},                                             # AmbientHumidity
    30: {2: (50, 10.0)},                                             # HumidifierTemperature
    31: {2: (50, 10.0)},                                             # HeatedTubeTemperature
    32: {2: (50, 10.0)},                                             # HumidifierPower
    33: {2: (50, 10.0)},                                             # HeatedTubePower
    36: {1: (5, 2.0),  3: (95, 2.0)},                                # BlowerPressure
    37: {1: (5, 0.2),  3: (95, 0.2)},                                # RespiratoryFlow
    38: {2: (50, 0.2)},                                              # BlowerFlow
    41: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},                # HeartRate
    42: {2: (50, 1.0), 3: (95, 1.0), 4: (100, 1.0)},                # AV*
}


def _summary_pretty(data, out=None):
    """Pretty-print the Summary protobuf using firmware-verified field names."""

    if out is None:
        out = sys.stdout
    # Unwrap spool envelope if present: a single wire-2 field containing the
    # actual Summary message.
    while True:
        try:
            top = _proto_decode(data)
        except (ValueError, IndexError):
            break
        if len(top) == 1 and top[0][1] == 2 and isinstance(top[0][2], (bytes, bytearray)):
            data = top[0][2]
            continue
        break
    for field, wire, value in _proto_decode(data):
        label = _SUMMARY_FIELDS.get(field, f"field_{field}")
        if wire == 2:
            try:
                subs = _proto_decode(value)
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
                    print(f"  sub_f{sf} ({_PROTO_WIRE.get(sw, sw)}): {sv}{tail}", file=out)
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


def _print_spool_legend(spool_type):
    legend = _SPOOL_LEGENDS.get(spool_type)
    if not legend:
        return
    et = legend.get("event_types")
    if et:
        print("# event record layout: field 1 = type, field 2 = start_ms, field 3 = end_ms, field 4 = duration_ms")
        parts = ", ".join(f"{k}={v}" for k, v in sorted(et.items()))
        print(f"# event types: {parts}")
        print()


def _spool_walk_events(data, depth=0):
    """Yield event records (field 1 innermost repeated) from a spool payload."""
    try:
        for field, wire, value in _proto_decode(data):
            if wire == 2:
                # the events are at depth 2 (wrapper -> collection -> event*)
                if depth < 2:
                    yield from _spool_walk_events(value, depth + 1)
                elif depth == 2 and field == 1:
                    yield value
    except (ValueError, IndexError):
        pass


def _print_spool_summary(spool_type, data):
    legend = _SPOOL_LEGENDS.get(spool_type)
    if not legend:
        return
    et = legend.get("event_types")
    if not et:
        return
    from collections import Counter
    counts = Counter()
    total = 0
    for ev in _spool_walk_events(data):
        total += 1
        try:
            for field, wire, value in _proto_decode(ev):
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


async def _spool_one_round(conn, spool_address, max_size):
    """Run a single StartSpool -> PullSpoolFragments cycle.

    Returns (data_bytes, status, next_spool_address, frag_count).
    Verifies per-round SHA256 against spoolHash.
    """
    fragments = []
    spool_done = asyncio.Event()
    state = {"status": "", "hash": "", "next": None}

    def on_notify(msg):
        method = msg.get("method", "")
        params = msg.get("params", {})
        if method != "SpoolFragment":
            return
        seq = params.get("seq", -1)
        data_b64 = params.get("data", "")
        status = params.get("status", "")
        if data_b64:
            fragments.append((seq, base64.b64decode(data_b64)))
        print(f"  fragment seq={seq} len={len(data_b64)} status={status}",
              file=sys.stderr, flush=True)
        state["status"] = status
        state["hash"] = params.get("spoolHash", "")
        state["next"] = params.get("nextSpoolAddress")
        if status != "SPOOL_INCOMPLETE":
            spool_done.set()

    conn._notification_cb = on_notify

    resp = await conn.send_rpc("StartSpool", {
        "spoolAddress": spool_address,
        "maxSpoolSize": max_size,
    }, encrypted=True)
    spool_id = resp.get("result", {}).get("spoolId", 0)
    print(f"StartSpool: spoolId={spool_id}", file=sys.stderr)
    if spool_id == 0:
        return b"", "", None, 0

    await conn.send_rpc("PullSpoolFragments", {
        "spoolId": spool_id, "maxFragmentSize": 2808, "maxNotifications": 0,
    }, encrypted=True, timeout=5.0)

    try:
        await asyncio.wait_for(spool_done.wait(), timeout=30.0)
    except asyncio.TimeoutError:
        print("  timeout waiting for fragments", file=sys.stderr)

    fragments.sort(key=lambda x: x[0])
    data = b"".join(f[1] for f in fragments)

    expected = state["hash"]
    if expected:
        actual = hashlib.sha256(data).hexdigest().upper()
        ok = "OK" if actual == expected.upper() else "MISMATCH"
        print(f"  SHA256: {ok} ({len(data)} bytes, {len(fragments)} fragments)",
              file=sys.stderr)

    return data, state["status"], state["next"], len(fragments)


async def cmd_spool(args):
    addr = resolve_addr(args.addr)
    conn = As11Connection(debug=args.debug)
    try:
        await conn.connect(addr)
        creds = load_credentials(addr)
        if not (creds.get("clientId") and creds.get("masterPairKey")):
            print("No stored credentials. Run 'pair' first.", file=sys.stderr)
            return
        new_creds = await conn.reconnect(creds["clientId"], creds["masterPairKey"])
        creds.update(new_creds)
        save_credentials(addr, creds)

        spool_type = args.spool_type
        from_dt = args.from_dt or "2000-01-01T00:00:00.000Z"

        # initial spoolAddress; subsequent rounds use nextSpoolAddress
        spool_address = {spool_type: {"fromDateTime": from_dt}}

        all_data = bytearray()
        total_fragments = 0
        round_num = 0
        final_status = ""
        last_next = None

        while True:
            round_num += 1
            if round_num > 1:
                print(f"--- round {round_num} (continuing from nextSpoolAddress) ---",
                      file=sys.stderr)
            data, status, nxt, n_frags = await _spool_one_round(
                conn, spool_address, args.max_size)
            all_data.extend(data)
            total_fragments += n_frags
            final_status = status
            last_next = nxt

            if args.no_follow:
                break
            if status != "SPOOL_COMPLETE_MORE_DATA_PENDING" or not nxt:
                break
            if round_num >= args.max_rounds:
                print(f"  stopping: hit --max-rounds {args.max_rounds}", file=sys.stderr)
                break
            spool_address = nxt

        data = bytes(all_data)

        # raw bytes to file (always, when -o)
        if args.output:
            with open(args.output, "wb") as f:
                f.write(data)
            print(f"Saved {len(data)} bytes to {args.output} "
                  f"({total_fragments} fragments, {round_num} rounds, "
                  f"status={final_status})", file=sys.stderr)
            if last_next and final_status == "SPOOL_COMPLETE_MORE_DATA_PENDING":
                print(f"  nextSpoolAddress: {json.dumps(last_next)}", file=sys.stderr)

        # decoded text to stdout
        if args.decode:
            _print_spool_legend(spool_type)
            if spool_type == "Summary":
                _summary_pretty(data)
            else:
                _proto_pretty(data)
            _print_spool_summary(spool_type, data)
            if last_next and final_status == "SPOOL_COMPLETE_MORE_DATA_PENDING":
                print(f"\n# status={final_status}", file=sys.stderr)
                print(f"# nextSpoolAddress: {json.dumps(last_next)}", file=sys.stderr)
            return

        # default JSON envelope (skip if we already saved to file)
        if args.output:
            return
        out = {
            "spoolType": spool_type,
            "fromDateTime": from_dt,
            "status": final_status,
            "rounds": round_num,
            "dataBase64": base64.b64encode(data).decode(),
            "dataLength": len(data),
            "fragments": total_fragments,
            "sha256": hashlib.sha256(data).hexdigest().upper(),
        }
        if last_next and final_status == "SPOOL_COMPLETE_MORE_DATA_PENDING":
            out["nextSpoolAddress"] = last_next
        print(json.dumps(out, indent=2))

    finally:
        await conn.disconnect()


def cmd_devices(args):
    all_creds = load_all_credentials()
    if not all_creds:
        print("No paired devices.")
        return
    print(f"{'address':<20}  {'alias':<15}  {'clientId':<12}")
    print(f"{'-'*20}  {'-'*15}  {'-'*12}")
    for addr, data in sorted(all_creds.items()):
        alias = data.get("alias", "")
        cid = data.get("clientId", "")[:12]
        print(f"{addr:<20}  {alias:<15}  {cid}")

def cmd_alias(args):
    addr = resolve_addr(args.target)
    all_creds = load_all_credentials()
    entry = all_creds.setdefault(addr, {})
    # reject name collision with another device
    for other_addr, data in all_creds.items():
        if other_addr != addr and data.get("alias") == args.name:
            raise SystemExit(f"alias {args.name!r} already used by {other_addr}")
    entry["alias"] = args.name
    save_all_credentials(all_creds)
    print(f"{addr} -> {args.name}")

def cmd_unalias(args):
    all_creds = load_all_credentials()
    for addr, data in all_creds.items():
        if data.get("alias") == args.name:
            del data["alias"]
            save_all_credentials(all_creds)
            print(f"removed alias {args.name!r} from {addr}")
            return
    raise SystemExit(f"no such alias: {args.name!r}")


def main():
    # restore default SIGPIPE so piping through head/less exits cleanly
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError):
        pass  # Windows

    examples = """addressing:
  --addr accepts a MAC, macOS UUID, or an alias. falls back to $AS11_ADDR.

  as11_ble.py --addr AA:BB:CC:DD:EE:FF rpc --method GetVersion
  as11_ble.py --addr bedroom rpc --method Get --params '["TherapyMode"]'
  AS11_ADDR=bedroom as11_ble.py stream --data-ids MaskPressure-50hz

see `<subcommand> --help` for per-command examples.
"""
    parser = argparse.ArgumentParser(
        description="AirSense 11 BLE Client",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--addr", default=None,
        help="BLE MAC address, macOS UUID, or alias. Falls back to $AS11_ADDR.")
    parser.add_argument("--debug", action="store_true", help="verbose packet logging")
    parser.add_argument("--verbose", "-v", action="store_true", help="info-level logging")
    sub = parser.add_subparsers(dest="command")

    raw_fmt = argparse.RawDescriptionHelpFormatter

    p_devices = sub.add_parser("devices",
        help="manage devices (scan/pair/list/alias/unalias)",
        epilog="""examples:
  scan for nearby devices:
      devices scan

  pair (addr required, passkey appears on device screen):
      --addr AA:BB:CC:DD:EE:FF devices pair

  list paired devices (also the default action):
      devices
      devices list

  give a device a friendly alias:
      devices alias AA:BB:CC:DD:EE:FF bedroom

  rename an existing alias:
      devices alias bedroom guestroom

  remove an alias:
      devices unalias bedroom
""",
        formatter_class=raw_fmt)
    dev_sub = p_devices.add_subparsers(dest="devices_action")

    p_scan = dev_sub.add_parser("scan", help="scan for AS11 devices")
    p_scan.add_argument("--timeout", type=float, default=10.0)

    dev_sub.add_parser("pair", help="pair with device",
        epilog="the passkey appears on the device screen; enter it when prompted.",
        formatter_class=raw_fmt)

    dev_sub.add_parser("list", help="list paired devices (default)")

    p_alias = dev_sub.add_parser("alias", help="assign alias to a paired device")
    p_alias.add_argument("target", help="MAC, UUID, or existing alias of the device")
    p_alias.add_argument("name", help="new alias")

    p_unalias = dev_sub.add_parser("unalias", help="remove an alias")
    p_unalias.add_argument("name", help="alias to remove")

    p_get = sub.add_parser("get", help="read one or more settings (Get RPC)",
        epilog="""examples:
  get TherapyMode
  get TherapyMode SetPressure SystemDateTime
""",
        formatter_class=raw_fmt)
    p_get.add_argument("names", nargs="+", help="setting names to read")

    p_set = sub.add_parser("set", help="write one or more settings (Set RPC)",
        epilog="""values default to string unless --type follows the pair.
supported types: str (default), int, float, bool, json.

examples:
  set TherapyMode AutoSet
  set SetPressure 10 --type int
  set SetPressure 10 --type int Mode AutoSet
  set RampEnable true --type bool AutoRampEnable false --type bool
  set --json '{"SetPressure":10,"TherapyMode":"AutoSet"}'
  set --json -                                         # read JSON from stdin
  echo '{"SetPressure":10}' | as11_ble.py set --json -
""",
        formatter_class=raw_fmt)
    p_set.add_argument("--json", dest="json_payload",
        help="params object as a JSON string; use '-' to read from stdin")
    p_set.add_argument("rest", nargs=argparse.REMAINDER,
        help="NAME VALUE [--type T] [NAME2 VALUE2 [--type T2]] ...")

    p_rpc = sub.add_parser("rpc", help="send JSON-RPC command",
        epilog="""examples:
  read one setting:
      rpc --method Get --params '["TherapyMode"]'

  read multiple settings:
      rpc --method Get --params '["TherapyMode","SetPressure","SystemDateTime"]'

  write a setting:
      rpc --method Set --params '{"SetPressure":10}'

  list firmware RPC versions:
      rpc --method GetVersion
""",
        formatter_class=raw_fmt)
    p_rpc.add_argument("--method", required=True, help="RPC method name")
    p_rpc.add_argument("--params", help="JSON params string")
    p_rpc.add_argument("--vcid", type=lambda x: int(x, 0), default=None,
        help="override TX VCID (hex, e.g. 0x0395)")
    p_rpc.add_argument("--no-encrypt", action="store_true",
        help="send plaintext (for non-standard VCIDs)")
    p_rpc.add_argument("--no-length-prefix", action="store_true",
        help="encrypt without 2-byte length prefix")
    p_rpc.add_argument("--raw-hex", default=None,
        help="send raw hex bytes (encrypted) instead of JSON-RPC")
    p_rpc.add_argument("--hmac", action="store_true",
        help="append HMAC-SHA256(K, payload) to encrypted data")

    p_stream = sub.add_parser("stream", help="start real-time data stream (NDJSON)",
        epilog="""examples:
  default streams at 1Hz:
      stream

  mask pressure at 50Hz (sample 20ms, report 100ms):
      stream --data-ids MaskPressure-50hz --sample-ms 20 --report-ms 100

  multiple signals:
      stream --data-ids InspiratoryPressure-50hz,Leak-TwoSecond

firmware constraint: reportIntervalMs must be <= sampleIntervalMs * 5.
stop with Ctrl-C; StartStream with empty dataIds is sent on exit.
""",
        formatter_class=raw_fmt)
    p_stream.add_argument("--data-ids", default=None,
        help="comma-separated stream IDs (default: InspiratoryPressure-50hz,Leak-TwoSecond,RemainingRampTime)")
    p_stream.add_argument("--sample-ms", type=int, default=200,
        help="sample interval ms (min 10, report must be <= sample*5)")
    p_stream.add_argument("--report-ms", type=int, default=1000, help="report interval ms")

    p_sub = sub.add_parser("subscribe", help="subscribe to device events (NDJSON)",
        epilog="stop with Ctrl-C.",
        formatter_class=raw_fmt)
    p_sub.add_argument("--events", default=None, help="comma-separated event IDs")

    p_spool = sub.add_parser("spool", help="download spool data",
        epilog="""types: """ + ", ".join(SPOOL_TYPES) + """

examples:
  human-readable session summary (auto-continues on MORE_DATA_PENDING):
      spool Summary --decode

  therapy events since a date:
      spool TherapyEvents-RespiratoryEvents --from-dt 2025-01-01T00:00:00.000Z --decode

  save raw protobuf + print decoded to stdout:
      spool Summary --decode -o summary.bin

  base64 envelope for further processing (default):
      spool Summary

  only one round (stops early; output JSON/stderr prints nextSpoolAddress):
      spool Summary --no-follow

`nextSpoolAddress` (shown when stopped early) is a ready-to-use spoolAddress
for a fresh StartSpool call to continue from where we left off.
""",
        formatter_class=raw_fmt)
    p_spool.add_argument("spool_type", help="spool type (e.g. Summary, TherapyEvents-RespiratoryEvents)")
    p_spool.add_argument("--from-dt", default=None, help="from datetime (ISO 8601)")
    p_spool.add_argument("--max-size", type=int, default=4096, help="max spool size per round")
    p_spool.add_argument("--no-follow", action="store_true",
        help="stop after one round even if status=SPOOL_COMPLETE_MORE_DATA_PENDING")
    p_spool.add_argument("--max-rounds", type=int, default=100,
        help="safety cap on auto-continuation rounds (default 100)")
    p_spool.add_argument("--decode", action="store_true",
        help="print human-readable protobuf tree to stdout (timestamps, nested fields)")
    p_spool.add_argument("-o", "--output", help="output file (binary). Can combine with --decode.")

    p_known = sub.add_parser("known",
        help="show known var/stream/event/spool names (discovered from firmware)",
        epilog="""examples:
  known                     registry overview
  known vars                all 402 variable names
  known vars groups         subgrouping breakdown (modes + topics)

  known vars cpap           therapy-mode prefix filter (Cpap-*)
  known vars ivaps
  known vars asvauto

  known vars summary        topic filter (Summary-*)
  known vars alarm
  known vars humidifier
  known vars reminder

  known vars Pressure       fall-through substring match
  known streams
  known events Alarm
  known spools

note: these lists are advisory; get/set/stream/subscribe/spool accept any string.
""",
        formatter_class=raw_fmt)
    p_known.add_argument("known_action", nargs="?", choices=list(REGISTRIES),
        help="which registry to list (omit for overview)")
    p_known.add_argument("pattern", nargs="?", default=None,
        help="case-insensitive substring filter")

    args = parser.parse_args()

    level = logging.DEBUG if getattr(args, 'debug', False) else logging.WARNING
    if getattr(args, 'verbose', False):
        level = logging.INFO
    logging.basicConfig(level=level, format="%(name)s: %(message)s")

    if args.command == "known":
        cmd_known(args)
    elif args.command == "get":
        asyncio.run(cmd_get(args))
    elif args.command == "set":
        asyncio.run(cmd_set(args))
    elif args.command == "rpc":
        asyncio.run(cmd_rpc(args))
    elif args.command == "stream":
        asyncio.run(cmd_stream(args))
    elif args.command == "subscribe":
        asyncio.run(cmd_subscribe(args))
    elif args.command == "spool":
        asyncio.run(cmd_spool(args))
    elif args.command == "devices":
        action = args.devices_action or "list"
        if action == "scan":
            asyncio.run(cmd_scan(args))
        elif action == "pair":
            asyncio.run(cmd_pair(args))
        elif action == "list":
            cmd_devices(args)
        elif action == "alias":
            cmd_alias(args)
        elif action == "unalias":
            cmd_unalias(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

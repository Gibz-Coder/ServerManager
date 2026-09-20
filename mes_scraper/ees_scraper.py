"""
EES Equipment Current Status Scraper
====================================
Scrapes the EES (Equipment Event System) EPT0103 screen:
  EPT -> Equipment Status -> Equipment Current Status (Visual Inspection)

Protocol:
  WCF net.tcp binary encoding over raw TCP socket
  Server: 107.105.195.140:8003/MesService
  Method: ExecQuery -> pr_EPT_EquipCurrentStatus (StoredProcedure)

Parameters:
  connectStringName : EES
  sqlList           : pr_EPT_EquipCurrentStatus
  commandType       : StoredProcedure
  inputParamList    : LanguageID=en-US, EquipmentID2='', EquipmentID='E1802217',...

Response format:
  WCF binary -> XML DataSet (diffgram) with Table0 rows containing:
    FactoryName, SegmentID, SegmentName, EquipmentClassID, EquipmentClassName,
    EquipmentID, EquipmentName, StartTime, NewState, EquipmentStateName,
    LotID, ProductID, FacilityID, OperatorID, RecipeName, ISUSABLE,
    EquipmentIP, TCMasterIP, TotalDisplaySequence, EquipmentType

Usage:
    python ees_scraper.py --once       # run once and exit
    python ees_scraper.py --offline    # parse existing debug_ees_current_status.bin
"""

import os
import re
import socket
import logging
import uuid
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

MANILA_TZ = timezone(timedelta(hours=8))

# -- EES Server Configuration --------------------------------------------------
EES_HOST = os.getenv("EES_HOST", "107.105.195.140")
EES_PORT = int(os.getenv("EES_PORT", "8003"))
EES_CONNECT_STRING = os.getenv("EES_CONNECT_STRING", "EES")

_HERE = os.path.dirname(__file__)
CAPTURED_REQUEST_FILE = os.path.join(_HERE, "ees_wcf_current_status_request.bin")
DEBUG_BIN = os.path.join(_HERE, "debug_ees_current_status.bin")

# -- Request Patching ----------------------------------------------------------

def patch_ees_current_status_request(template: bytes) -> bytes:
    """
    Patch the captured WCF binary request with a fresh GUID transaction ID.
    The template contains TID: 0a1bacad-b5b4-4f01-ad7b-598cef3e8ce5
    """
    old_guid = b"0a1bacad-b5b4-4f01-ad7b-598cef3e8ce5"
    new_guid = str(uuid.uuid4()).encode("ascii")
    if old_guid in template:
        data = template.replace(old_guid, new_guid, 1)
        log.info(f"  [ees patch] TID: {old_guid.decode()} -> {new_guid.decode()}")
        return data
    return template


# -- WCF net.tcp Transport -----------------------------------------------------

_PREAMBLE_ACK = 0x0b   # Server sends this after accepting the preamble

def _find_preamble_end(data: bytes) -> int:
    """
    Find the offset of the PreambleEnd record (0x05) in the WCF binary.
    """
    i = 0
    n = len(data)
    while i < n:
        rec = data[i]
        if rec == 0x00:          # VersionRecord
            i += 3
        elif rec == 0x01:        # ModeRecord
            i += 2
        elif rec == 0x02:        # ViaRecord - variable length
            i += 1
            length = 0; shift = 0
            while i < n:
                b = data[i]; i += 1
                length |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            i += length
        elif rec == 0x03:        # KnownEncodingRecord
            i += 2
        elif rec == 0x04:        # ExtensionEncodingRecord
            i += 1
        elif rec == 0x0c:        # UpgradeRequest
            i += 1
        elif rec == 0x05:        # PreambleEnd
            return i
        else:
            break
    return -1


def send_wcf_request(host: str, port: int, request_bytes: bytes,
                     timeout: int = 60) -> bytes:
    """
    Send a WCF net.tcp binary request and receive the full response.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        log.info(f"  [ees tcp] Connecting to {host}:{port}...")
        sock.connect((host, port))
        log.info("  [ees tcp] Connected.")

        preamble_end_pos = _find_preamble_end(request_bytes)

        if preamble_end_pos == -1:
            log.warning("  [ees tcp] No preamble end found - sending raw bytes")
            sock.sendall(request_bytes)
        else:
            preamble = request_bytes[:preamble_end_pos + 1]  # includes 0x05
            message  = request_bytes[preamble_end_pos + 1:]

            log.info(f"  [ees tcp] Sending preamble ({len(preamble)} bytes)...")
            sock.sendall(preamble)

            sock.settimeout(15)
            ack = b""
            while len(ack) < 1:
                chunk = sock.recv(16)
                if not chunk:
                    raise ConnectionError("Server closed connection before PreambleAck")
                ack += chunk

            log.info(f"  [ees tcp] Server response after preamble: {ack.hex()}")

            if ack[0] == 0x0d:
                log.info("  [ees tcp] UpgradeResponse - sending UpgradeRequest accepted (0x0e)...")
                sock.sendall(b'\x0e')
                ack = b""
                while len(ack) < 1:
                    chunk = sock.recv(16)
                    if not chunk:
                        raise ConnectionError("Server closed after UpgradeResponse")
                    ack += chunk
                log.info(f"  [ees tcp] Post-upgrade response: {ack.hex()}")

            if ack[0] != _PREAMBLE_ACK:
                raise ConnectionError(
                    f"Expected PreambleAck (0x0b), got 0x{ack[0]:02x}. "
                    f"Full ack bytes: {ack.hex()}"
                )
            log.info(f"  [ees tcp] PreambleAck received (0x{ack[0]:02x}) - sending message...")

            sock.settimeout(timeout)
            log.info(f"  [ees tcp] Sending message ({len(message)} bytes)...")
            sock.sendall(message)

        response = b""
        sock.settimeout(timeout)
        while True:
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response += chunk
            except socket.timeout:
                break

        log.info(f"  [ees tcp] Received {len(response)} bytes")
        return response

    finally:
        try:
            sock.sendall(b'\x07')  # End record - clean close
        except Exception:
            pass
        sock.close()


# -- Response Parsing ----------------------------------------------------------

FIELD_MAP = {
    'FactoryName':          'factory_name',
    'SegmentID':            'segment_id',
    'SegmentName':          'segment_name',
    'EquipmentClassID':      'equipment_class_id',
    'EquipmentClassName':    'equipment_class_name',
    'EquipmentID':          'equipment_code',
    'EquipmentName':        'equipment_name',
    'StartTime':            'start_time',
    'NewState':             'present_status_code',
    'EquipmentStateName':   'state_name',
    'LotID':                'lot_id',
    'ProductID':            'product_id',
    'FacilityID':           'facility_id',
    'OperatorID':           'operator_id',
    'RecipeName':           'recipe_name',
    'ISUSABLE':             'is_usable',
    'EquipmentIP':          'equipment_ip',
    'TCMasterIP':           'tc_master_ip',
    'TotalDisplaySequence': 'total_display_sequence',
    'EquipmentType':        'equipment_type',
}

def _extract_field_value(block: bytes, name: str) -> str:
    """Extract a single field string value from a WCF binary element block."""
    needle = name.encode('utf-8')
    pos = block.find(needle)
    if pos == -1:
        return ''
    
    val_start = pos + len(needle)
    p = val_start
    # WCF binary types: 0x98/0x99 (1-byte len), 0x9a/0x9b (2-byte len), 0x01/0x40 (empty)
    while p < len(block) and p < val_start + 5:
        tb = block[p]
        if tb in (0x98, 0x99):
            if p + 1 >= len(block):
                return ''
            length = block[p + 1]
            return block[p + 2:p + 2 + length].decode('utf-8', errors='replace')
        elif tb in (0x9a, 0x9b):
            if p + 2 >= len(block):
                return ''
            length = block[p + 1] | (block[p + 2] << 8)
            return block[p + 3:p + 3 + length].decode('utf-8', errors='replace')
        elif tb in (0x01, 0x40):
            return ''
        elif tb == 0x80:
            return '0'
        p += 1
    return ''


def parse_ees_current_status_response(raw: bytes) -> list[dict]:
    """
    Parse the WCF binary response for pr_EPT_EquipCurrentStatus into list of row dicts.
    """
    if not raw:
        log.warning("[ees parse] Empty response")
        return []

    # Find Table0 row markers in diffgram
    row_markers = [m.start() for m in re.finditer(rb'@\x06Table0\x05\x06diffgr', raw)]
    log.info(f"[ees parse] Found {len(row_markers)} equipment records")

    rows = []
    for i in range(len(row_markers)):
        start = row_markers[i]
        end = row_markers[i + 1] if i + 1 < len(row_markers) else len(raw)
        block = raw[start:end]

        row = {}
        for wcf_key, db_col in FIELD_MAP.items():
            val = _extract_field_value(block, wcf_key)
            row[db_col] = val.strip() if val else None

        if row.get('equipment_code'):
            rows.append(row)

    log.info(f"[ees parse] Successfully parsed {len(rows)} valid equipment status rows")
    return rows


# -- Main Fetch Function -------------------------------------------------------

def fetch_ees_current_status(offline: bool = False) -> list[dict]:
    """
    Fetch real-time EES Equipment Current Status for Visual Inspection machines.
    Returns a list of dicts with database column keys.
    """
    if offline:
        if not os.path.exists(DEBUG_BIN):
            log.warning(f"[ees] No debug binary found at {DEBUG_BIN}")
            return []
        with open(DEBUG_BIN, "rb") as f:
            raw = f.read()
        log.info(f"[ees] Offline mode: parsing {len(raw)} bytes from {DEBUG_BIN}")
    else:
        if not os.path.exists(CAPTURED_REQUEST_FILE):
            log.error(f"[ees] Captured request template not found: {CAPTURED_REQUEST_FILE}")
            return []

        with open(CAPTURED_REQUEST_FILE, "rb") as f:
            template = f.read()

        request = patch_ees_current_status_request(template)

        try:
            raw = send_wcf_request(EES_HOST, EES_PORT, request)
        except (socket.error, OSError) as e:
            log.error(f"[ees] TCP connection to {EES_HOST}:{EES_PORT} failed: {e}")
            return []

        with open(DEBUG_BIN, "wb") as f:
            f.write(raw)
        log.info(f"[ees] Raw response saved -> {DEBUG_BIN}")

    if not raw:
        log.warning("[ees] Empty response received")
        return []

    return parse_ees_current_status_response(raw)


if __name__ == "__main__":
    import sys
    offline_mode = "--offline" in sys.argv or "-o" in sys.argv

    results = fetch_ees_current_status(offline=offline_mode)
    print(f"\nTotal Equipment Status Rows: {len(results)}")
    if results:
        print("\nColumns:", list(results[0].keys()))
        print("\nFirst 3 rows:")
        for r in results[:3]:
            print(" ", r)
        print("\nLast 3 rows:")
        for r in results[-3:]:
            print(" ", r)

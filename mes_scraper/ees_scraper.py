"""
EES Equipment Detailed History Scraper
=======================================
Scrapes the EES (Equipment Event System) EPT0184 screen:
  EPT → Equipment Status → Equipment Detailed History (Status, Alarm, Event)

Protocol:
  WCF net.tcp binary encoding over raw TCP socket
  Server: 107.105.195.140:8003/MesService
  Method: ExecQuery → pr_EPT_HistoryByEQP_SearchData (StoredProcedure)

Parameters:
  connectStringName : EES
  sqlList           : pr_EPT_HistoryByEQP_SearchData
  commandType       : StoredProcedure
  inputParamList    : key-value pairs (EquipmentID2, SearchType, FrDate, ToDate, ...)

Response format:
  WCF binary → XML DataSet (diffgram) with Table0 rows containing:
    EquipmentCode, EquipmentName, StartTime, EndTime, ElapsedTime(M),
    OldStateName (FromState), NewStateName (PresentStatus),
    ProductID, LotID, Creator (Worker)

Usage:
    python ees_scraper.py --once       # run once and exit
    python ees_scraper.py              # run on schedule
    python ees_scraper.py --offline    # parse existing debug_ees_history.bin
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

# ── EES Server ────────────────────────────────────────────────────────────────
EES_HOST = os.getenv("EES_HOST", "107.105.195.140")
EES_PORT = int(os.getenv("EES_PORT", "8003"))
EES_CONNECT_STRING = os.getenv("EES_CONNECT_STRING", "EES")

# Path to the captured WCF binary request (template)
_HERE = os.path.dirname(__file__)
CAPTURED_REQUEST_FILE = os.path.join(_HERE, "ees_wcf_request_full.bin")
DEBUG_BIN = os.path.join(_HERE, "debug_ees_history.bin")

# ── WCF Binary Encoding Helpers ───────────────────────────────────────────────

def _patch_wcf_string(data: bytes, old_str: str, new_str: str) -> bytes:
    """
    Replace a WCF-encoded string in the binary payload.
    Handles the 0x99 [len] [data] encoding.
    """
    old_enc = old_str.encode("utf-8")
    new_enc = new_str.encode("utf-8")

    # Build old WCF encoding
    old_len = len(old_enc)
    old_len_bytes = bytearray()
    n = old_len
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            old_len_bytes.append(b | 0x80)
        else:
            old_len_bytes.append(b)
            break
    old_wcf = b'\x99' + bytes(old_len_bytes) + old_enc

    # Build new WCF encoding
    new_len = len(new_enc)
    new_len_bytes = bytearray()
    n = new_len
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            new_len_bytes.append(b | 0x80)
        else:
            new_len_bytes.append(b)
            break
    new_wcf = b'\x99' + bytes(new_len_bytes) + new_enc

    return data.replace(old_wcf, new_wcf, 1)


# ── Request Patching ──────────────────────────────────────────────────────────

def patch_ees_request(template: bytes, fr_date: str, to_date: str) -> bytes:
    """
    Patch the captured WCF binary request with new date range and a fresh GUID.

    The template contains:
      FrDate  = "2026-04-29 00:00"       (16 chars)
      ToDate  = "2026-04-30 00:00:00"    (19 chars)
      GUID    = "155944bc-23cb-40ea-a823-00a72161cd40"

    We replace these with the current date range and a new GUID.
    """
    data = template

    # Replace FrDate
    old_fr = "2026-04-29 00:00"
    data = _patch_wcf_string(data, old_fr, fr_date)
    log.info(f"  [ees patch] FrDate: {old_fr!r} -> {fr_date!r}")

    # Replace ToDate
    old_to = "2026-04-30 00:00:00"
    data = _patch_wcf_string(data, old_to, to_date)
    log.info(f"  [ees patch] ToDate: {old_to!r} -> {to_date!r}")

    # Replace GUID (plain ASCII in the binary, not WCF-encoded)
    old_guid = b"155944bc-23cb-40ea-a823-00a72161cd40"
    new_guid = str(uuid.uuid4()).encode("ascii")
    if old_guid in data:
        data = data.replace(old_guid, new_guid, 1)
        log.info(f"  [ees patch] GUID: {old_guid.decode()} -> {new_guid.decode()}")

    log.info(f"  [ees patch] Request: {len(template)} -> {len(data)} bytes")
    return data


def build_date_range() -> tuple[str, str]:
    """
    Return (FrDate, ToDate) for today's full day in Manila time.
    FrDate = "YYYY-MM-DD 00:00"
    ToDate = "YYYY-MM-DD 00:00:00"  (next day midnight)
    """
    now = datetime.now(MANILA_TZ)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    fr_date = f"{today} 00:00"
    to_date = f"{tomorrow} 00:00:00"
    return fr_date, to_date


def build_yesterday_date_range() -> tuple[str, str]:
    """
    Return (FrDate, ToDate) for YESTERDAY's full day in Manila time.
    Used for the daily snapshot — captures the previous day's completed data.
    FrDate = "YYYY-MM-DD 00:00"      (yesterday midnight)
    ToDate = "YYYY-MM-DD 00:00:00"   (today midnight)
    """
    now = datetime.now(MANILA_TZ)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    fr_date = f"{yesterday} 00:00"
    to_date = f"{today} 00:00:00"
    return fr_date, to_date


# ── WCF net.tcp Transport ─────────────────────────────────────────────────────

# WCF net.tcp framing record types (MC-NMF spec)
_PREAMBLE_END = b'\x05'
_PREAMBLE_ACK = 0x0b   # server sends this after accepting the preamble

def send_wcf_request(host: str, port: int, request_bytes: bytes,
                     timeout: int = 60) -> bytes:
    """
    Send a WCF net.tcp binary request and receive the full response.

    WCF net.tcp framing protocol (MC-NMF):
      1. Client sends preamble: Version + Mode + Via + KnownEncoding + PreambleEnd (0x05)
      2. Server responds with PreambleAck (0x0b)
      3. Client sends the SOAP message (sized envelope)
      4. Server responds with the result
      5. Client sends End record (0x07) to close

    The captured binary includes the full preamble + message.
    We split at PreambleEnd (0x05) and wait for PreambleAck before sending the message.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        log.info(f"  [ees tcp] Connecting to {host}:{port}...")
        sock.connect((host, port))
        log.info(f"  [ees tcp] Connected.")

        # Split the binary into preamble and message at the PreambleEnd (0x05) byte
        # The preamble ends with 0x05; everything after is the SOAP message
        preamble_end_pos = _find_preamble_end(request_bytes)

        if preamble_end_pos == -1:
            # No preamble found — send everything at once (fallback)
            log.warning("  [ees tcp] No preamble end found — sending raw bytes")
            sock.sendall(request_bytes)
        else:
            preamble = request_bytes[:preamble_end_pos + 1]  # includes 0x05
            message  = request_bytes[preamble_end_pos + 1:]

            # Step 1: Send preamble
            log.info(f"  [ees tcp] Sending preamble ({len(preamble)} bytes)...")
            sock.sendall(preamble)

            # Step 2: Wait for server response after preamble
            # The server may send:
            #   0x0b = PreambleAck (ready to receive message)
            #   0x0d = UpgradeResponse (server wants protocol upgrade)
            #          → reply with 0x0e (UpgradeRequest accepted) then wait again
            sock.settimeout(15)
            ack = b""
            while len(ack) < 1:
                chunk = sock.recv(16)
                if not chunk:
                    raise ConnectionError("Server closed connection before PreambleAck")
                ack += chunk

            log.info(f"  [ees tcp] Server response after preamble: {ack.hex()}")

            # Handle UpgradeResponse (0x0d)
            if ack[0] == 0x0d:
                log.info(f"  [ees tcp] UpgradeResponse — sending UpgradeRequest accepted (0x0e)...")
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
            log.info(f"  [ees tcp] PreambleAck received (0x{ack[0]:02x}) — sending message...")

            # Step 3: Send the SOAP message
            sock.settimeout(timeout)
            log.info(f"  [ees tcp] Sending message ({len(message)} bytes)...")
            sock.sendall(message)

        # Step 4: Receive response — use the full timeout, not a fixed 30s
        # Large historical responses can have gaps between TCP segments
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
            sock.sendall(b'\x07')  # End record — clean close
        except Exception:
            pass
        sock.close()


def _find_preamble_end(data: bytes) -> int:
    """
    Find the offset of the PreambleEnd record (0x05) in the WCF binary.

    Parses the preamble records sequentially to find the exact position:
      0x00 = VersionRecord    (3 bytes: type + major + minor)
      0x01 = ModeRecord       (2 bytes: type + mode)
      0x02 = ViaRecord        (1 + 7-bit-len + url bytes)
      0x03 = KnownEncoding    (2 bytes: type + encoding-id)
      0x05 = PreambleEnd      (1 byte)
    """
    i = 0
    n = len(data)
    while i < n:
        rec = data[i]
        if rec == 0x00:          # VersionRecord
            i += 3
        elif rec == 0x01:        # ModeRecord
            i += 2
        elif rec == 0x02:        # ViaRecord — variable length
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
        elif rec == 0x04:        # ExtensionEncodingRecord (variable — skip safely)
            i += 1
        elif rec == 0x0c:        # UpgradeRequest or similar — skip 1 byte
            i += 1
        elif rec == 0x05:        # PreambleEnd — this is what we want
            return i
        else:
            # Unknown record — stop scanning
            break
    return -1


# ── Response Parsing ──────────────────────────────────────────────────────────

def parse_ees_response(raw: bytes) -> list[dict]:
    """
    Parse the WCF binary response from pr_EPT_HistoryByEQP_SearchData.

    The response uses WCF binary XML encoding. Each data field is encoded as:
      [1-byte name-length] [field-name UTF-8] [value-type-byte] [value]

    Value type bytes:
      0x40        = ZeroText (empty string)
      0x98, 0x99  = Chars8Text[WithEndElement] — 1-byte length + UTF-8 data
      0xa8..0xaf  = Chars8Text variants (same encoding, different end-element flags)
      0x9a, 0x9b  = Chars16Text[WithEndElement] — 2-byte LE length + UTF-8 data

    False-match guard: we only accept a field name if the byte immediately
    before it equals len(field_name), which is the WCF name-length prefix.
    This filters out schema definitions, attribute records, and localized
    name variants (EquipmentName_K, EquipmentName_C, etc.).
    """
    if not raw:
        log.warning("[ees parse] Empty response")
        return []

    import re as _re

    # Known field names to extract
    field_names = [
        'rowOrder', 'EquipmentID', 'EquipmentName',
        'StartTime', 'EndTime', 'ElapsedTime',
        'OldState', 'OldStateName', 'NewState', 'NewStateName',
        'LotID', 'ProductID', 'SegmentID', 'EquipmentClassID', 'Creator',
    ]

    # WCF string value type bytes that carry actual text data
    # 0x98-0x9b: Chars8/16 Text with/without EndElement
    # 0xa8-0xaf, 0x87: these appear as 2-byte prefixes [type][0x03] before the real 0x99 string
    STRING_TYPES_1BYTE_LEN = {0x98, 0x99}
    STRING_TYPES_2BYTE_LEN = {0x9a, 0x9b}
    # These types are followed by 1 skip-byte then a real 0x98/0x99 string record
    STRING_TYPES_SKIP1 = {0x87, 0xa8, 0xa9, 0xaa, 0xab, 0xac, 0xad, 0xae, 0xaf}

    n = len(raw)
    all_fields: list[tuple[int, str, str]] = []

    for fname in field_names:
        fb = fname.encode('utf-8')
        fname_len = len(fb)

        for m in _re.finditer(_re.escape(fb), raw):
            pos = m.start()

            # Guard: byte before the name must equal the name length
            # This is the WCF name-length prefix byte in data rows.
            # Filters out schema/attribute/parameter false matches.
            if pos == 0 or raw[pos - 1] != fname_len:
                continue

            val_pos = pos + fname_len
            if val_pos >= n:
                continue

            vt = raw[val_pos]

            if vt == 0x40:
                # ZeroText — empty value
                val = ''

            elif vt in STRING_TYPES_1BYTE_LEN:
                # 1-byte length prefix
                if val_pos + 1 >= n:
                    continue
                vlen = raw[val_pos + 1]
                if val_pos + 2 + vlen > n:
                    continue
                val = raw[val_pos + 2:val_pos + 2 + vlen].decode('utf-8', 'replace')

            elif vt in STRING_TYPES_2BYTE_LEN:
                # 2-byte LE length prefix
                if val_pos + 2 >= n:
                    continue
                vlen = int.from_bytes(raw[val_pos + 1:val_pos + 3], 'little')
                if val_pos + 3 + vlen > n:
                    continue
                val = raw[val_pos + 3:val_pos + 3 + vlen].decode('utf-8', 'replace')

            elif vt in STRING_TYPES_SKIP1:
                # 2-byte prefix [type][skip], then real 0x98/0x99 string record
                skip = val_pos + 2
                if skip >= n:
                    continue
                vt2 = raw[skip]
                if vt2 not in STRING_TYPES_1BYTE_LEN:
                    continue
                if skip + 1 >= n:
                    continue
                vlen = raw[skip + 1]
                if skip + 2 + vlen > n:
                    continue
                val = raw[skip + 2:skip + 2 + vlen].decode('utf-8', 'replace')

            else:
                # Non-string type — skip
                continue

            all_fields.append((pos, fname, val))

    # Sort by byte position
    all_fields.sort(key=lambda x: x[0])
    log.info(f"[ees parse] Found {len(all_fields)} field occurrences")

    # Group into rows by 'rowOrder'
    # EquipmentName only appears on the first row per equipment group in the binary.
    # We carry it forward to all subsequent rows of the same equipment.
    rows: list[dict] = []
    current_row: dict = {}
    equip_name_map: dict[str, str] = {}  # equipment_code → equipment_name

    def _close_row(row: dict):
        """Finalize a row: fill missing EquipmentName from cache, update cache."""
        eq_id = row.get('EquipmentID', '')
        if eq_id:
            if 'EquipmentName' in row and row['EquipmentName']:
                equip_name_map[eq_id] = row['EquipmentName']
            elif eq_id in equip_name_map:
                row['EquipmentName'] = equip_name_map[eq_id]

    for _pos, fname, val in all_fields:
        if fname == 'rowOrder':
            if current_row and 'EquipmentID' in current_row:
                _close_row(current_row)
                rows.append(current_row)
            current_row = {'rowOrder': val}
        else:
            current_row[fname] = val

    if current_row and 'EquipmentID' in current_row:
        _close_row(current_row)
        rows.append(current_row)

    log.info(f"[ees parse] Parsed {len(rows)} rows")
    return rows


def parse_ees_response_v2(raw: bytes) -> list[dict]:
    """Alias for parse_ees_response (kept for compatibility)."""
    return parse_ees_response(raw)


# ── Column Remapping ──────────────────────────────────────────────────────────

# Map WCF binary field names → DB column names
# Verified against EES_0429_rawdata.txt headers and pcapng response structure
EES_COL_MAP = {
    # WCF binary field name → DB column name
    "EquipmentID":      "equipment_code",    # Equipment code (e.g. C0112056)
    "EquipmentName":    "equipment_name",    # Equipment name (e.g. VI324_Inspection...)
    "StartTime":        "start_time",        # State start timestamp
    "EndTime":          "end_time",          # State end timestamp
    "ElapsedTime":      "elapsed_time_m",    # Elapsed time in M:SS format
    "OldState":         "from_state_code",   # Previous state code (e.g. AA01)
    "OldStateName":     "from_state",        # Previous state name (e.g. RUN)
    "NewState":         "present_status_code",  # Current state code (e.g. LA01)
    "NewStateName":     "present_status",    # Current state name (e.g. Waiting for WIP)
    "LotID":            "lot_id",            # Lot ID
    "ProductID":        "product_id",        # Product/Model ID
    "SegmentID":        "segment_id",        # Segment ID
    "EquipmentClassID": "equipment_class_id",# Equipment class (e.g. VI)
    "Creator":          "worker",            # Worker/operator name
    # rowOrder is internal — not stored in DB
}


def remap_ees_row(row: dict) -> dict:
    """Rename WCF binary field names to DB column names. Skip rowOrder (internal)."""
    return {EES_COL_MAP[k]: v for k, v in row.items() if k in EES_COL_MAP}


# Valid equipment name patterns:
#   VI + 3-digit number + underscore  e.g. VI324_Inspection(SEMCO)_2Tr_4Sides_Color-G1
#   MAVI + 2-digit number + underscore  e.g. MAVI01_Inspection(SEMCO)
import re as _re
_VALID_EQUIP_NAME = _re.compile(r'^(VI\d{3}_|MAVI\d{2}_)')


def _clean_equipment_name(name: str) -> str:
    """
    Clean a WCF-decoded equipment_name value.

    The WCF binary sometimes prepends a 1-byte dictionary index to the string
    value (e.g. 0x2b = '+' before 'VI259_Inspection...'). This produces values
    like '+VI259_Inspection...' or '\\x03VI324_Inspection...'.

    Strategy:
      1. If the name already matches VI\\d{3}_ → return as-is
      2. Strip up to 3 leading non-VI bytes and retry
      3. If still no match → return empty string (will be filled from cache)
    """
    if not name:
        return ''
    # Already valid
    if _VALID_EQUIP_NAME.match(name):
        return name
    # Try stripping 1, 2, or 3 leading bytes
    for skip in range(1, 4):
        if len(name) > skip and _VALID_EQUIP_NAME.match(name[skip:]):
            return name[skip:]
    # Not recoverable — return empty so the cache fill-forward can handle it
    return ''


def clean_ees_rows(rows: list[dict]) -> list[dict]:
    """
    Post-process parsed rows:
    - Clean equipment_name (strip WCF dictionary index prefix bytes)
    - Re-apply equipment_name cache fill-forward after cleaning
    """
    equip_name_cache: dict[str, str] = {}

    for row in rows:
        code = row.get('equipment_code', '')
        name = row.get('equipment_name', '') or ''

        # Clean the name
        cleaned = _clean_equipment_name(name)

        if cleaned:
            row['equipment_name'] = cleaned
            if code:
                equip_name_cache[code] = cleaned
        elif code and code in equip_name_cache:
            # Fill from cache (covers nulls and unrecoverable garbage)
            row['equipment_name'] = equip_name_cache[code]
        else:
            row['equipment_name'] = None  # genuinely unknown

    return rows


def filter_ees_rows(rows: list[dict]) -> list[dict]:
    """Filter out rows without an equipment_code."""
    return [r for r in rows if r.get("equipment_code") not in (None, "")]


# ── Main Fetch Function ───────────────────────────────────────────────────────

def fetch_ees_history(offline: bool = False) -> list[dict]:
    """
    Fetch EES Equipment Detailed History for TODAY.
    Returns a list of dicts with keys matching the DB column names.
    """
    return _fetch_ees(offline=offline, date_range=build_date_range())


def fetch_ees_history_yesterday() -> list[dict]:
    """
    Fetch EES Equipment Detailed History for YESTERDAY.
    Used for the daily snapshot — mirrors RPT40120 snapshot behavior.
    Only called on run #3+ to allow EES reflection delay after midnight.
    """
    return _fetch_ees(offline=False, date_range=build_yesterday_date_range())


def _fetch_ees(offline: bool = False,
               date_range: tuple[str, str] | None = None) -> list[dict]:
    """
    Internal fetch — shared by today and yesterday variants.
    """
    if date_range is None:
        date_range = build_date_range()
    fr_date, to_date = date_range
    if offline:
        if not os.path.exists(DEBUG_BIN):
            log.warning(f"[ees] No debug bin at {DEBUG_BIN}")
            return []
        with open(DEBUG_BIN, "rb") as f:
            raw = f.read()
        log.info(f"[ees] Offline mode: parsing {len(raw)} bytes from {DEBUG_BIN}")
    else:
        # Load the captured request template
        if not os.path.exists(CAPTURED_REQUEST_FILE):
            log.error(f"[ees] Captured request not found: {CAPTURED_REQUEST_FILE}")
            log.error("[ees] Run the capture first: see ees_capture/ folder")
            return []

        with open(CAPTURED_REQUEST_FILE, "rb") as f:
            template = f.read()

        log.info(f"[ees] Date range: {fr_date} → {to_date}")

        # Patch the request
        request = patch_ees_request(template, fr_date, to_date)

        # Send over TCP
        try:
            raw = send_wcf_request(EES_HOST, EES_PORT, request)
        except (socket.error, OSError) as e:
            log.error(f"[ees] TCP connection failed: {e}")
            return []

        # Save debug binary
        with open(DEBUG_BIN, "wb") as f:
            f.write(raw)
        log.info(f"[ees] Raw response saved → {DEBUG_BIN}")

    if not raw:
        log.warning("[ees] Empty response")
        return []

    # Parse the response
    rows = parse_ees_response(raw)

    log.info(f"[ees] Parsed {len(rows)} raw rows")

    # Remap, clean, and filter
    rows = [remap_ees_row(r) for r in rows]
    rows = clean_ees_rows(rows)
    rows = filter_ees_rows(rows)
    log.info(f"[ees] {len(rows)} rows after clean+filter")

    return rows


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    offline = "--offline" in sys.argv

    rows = fetch_ees_history(offline=offline)
    print(f"\nTotal rows: {len(rows)}")
    if rows:
        print("Columns:", list(rows[0].keys()))
        print("\nFirst 3 rows:")
        for r in rows[:3]:
            print(" ", r)
        print("\nLast 3 rows:")
        for r in rows[-3:]:
            print(" ", r)

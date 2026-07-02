# MES Scraper — Developer Guide

Automated scraper for SEMPHIL MES (TOBESOFT XPlatform) reports.
Captures XPlatform binary traffic, decodes the proprietary binary format,
and stores data in MySQL.

---

## Currently Scraped Reports

| Report | Table | Snapshot Table | Port | Protocol/Method | Interval |
|---|---|---|---|---|---|
| RPT40281 — WIP Status | `wip_status` | `wip_status_snapshot` | 8080 | HTTP POST (XPlatform binary) | Every run |
| RPT40496 — Monthly Plan | `monthly_plan` | `monthly_plan_snapshot` | 8080 | HTTP POST (XPlatform binary) | Every run |
| RPT40120 — Process Result (Output) | `process_result` | `process_result_snapshot` | 8081 | HTTP POST (XPlatform binary) | Every run |
| RPT40120 — Process Trackout | `process_trackout` | `process_trackout_snapshot` | 8081 | HTTP POST (XPlatform binary) | Every run |
| EPT0184 — Equipment Detailed History | `eqp_detailed_history` | `eqp_detailed_history_snapshot` | 8003 | WCF net.tcp (binary encoding) | Every run |

---

## Architecture Overview

```
XPlatform.exe
  │
  ├─ TCP :8080 → POST /RptXPController.do      (RPT40281, RPT40496)
  └─ TCP :8081 → POST /RptXPController.do      (RPT40120 output + trackout)

Response format:
  ff ad [zlib-compressed XPlatform binary]
       └─ fe 10 blocks (datasets)
            └─ column definitions + row data

EES Service
  │
  └─ TCP :8003 → ExecQuery (pr_EPT_HistoryByEQP_SearchData)
```

### Key Files

```
mes_scraper/
  main.py                Entry point — scheduler, job runner, snapshot logic
  scraper_direct.py      HTTP replay, XP binary parser, column maps, patch functions
  ees_scraper.py         WCF net.tcp client for scraping Equipment Detailed History (EPT0184)
  db.py                  MySQL table definitions and INSERT logic
  xp_requests.json       Captured POST bodies for each RPT report
  ees_wcf_request_full.bin Captured WCF binary template for EES requests
  .env                   Credentials and config (synced from DB Orchestrator config)
  proxy_intercept.py     Proxy interceptor (for port 8080 reports only)
  backfill_snapshots.py  Utility to backfill historical snapshot data for target date ranges
  repair_equipment_names.py Repair utility to fix garbage values in equipment_name columns
```


---

## How the Scraper Works

### 1. Capture (one-time setup per report)

The scraper replays a captured HTTP POST request to get fresh data.
You capture the POST body once using either:

- **Proxy interceptor** — for port 8080 reports (RPT40281, RPT40496)
- **Wireshark** — for port 8081 reports (RPT40120) because XPlatform bypasses the Windows proxy for port 8081

The captured POST body is stored in `xp_requests.json`.

### 2. Patch (every run)

Before replaying, the scraper patches stale values inside the zlib-compressed POST body:

| Field | What it does |
|---|---|
| `StartDate` | Set to today 00:00:00 (or yesterday for snapshots) |
| `EndDate` | Set to tomorrow 00:00:00 (or today for snapshots) |
| `end_date` | Set to current datetime |
| `log_seq` | Set to current Unix timestamp |
| `JSESSIONID` | Replaced with fresh session ID (port 8081 only) |

### 3. Replay

The patched POST body is sent to the MES server.
The server returns an XPlatform binary response (`ff ad` + zlib).

### 4. Parse

The binary is decompressed and parsed:
- `fe 10` = block start marker
- Column definitions follow (name + type + max_size)
- Row data follows (2 slots per column — slot1 discarded, slot2 = real value)
- `fe 01` = block end marker
- Metadata blocks (`gv_logSeq`, `ErrorCode`, `ErrorMsg`) are skipped

### 5. Remap + Store

Binary di-codes (e.g. `di00000262`) are mapped to human-readable names
(e.g. `lot_no`) using the column map in `scraper_direct.py`.
Rows are inserted into MySQL.

---

## Realtime vs Snapshot Tables

| Table type | Behavior | Date range |
|---|---|---|
| Realtime | Truncated and refilled every run | Today 00:00 → Tomorrow 00:00 |
| Snapshot (RPT40281/40496) | Insert once per day, never deleted | Same as realtime |
| Snapshot (RPT40120 & EES) | Insert on 3rd run of the day, never deleted | Yesterday 00:00 → Today 00:00 |

**Why RPT40120 & EES snapshots use yesterday's data:**
RPT40120 is a production result report and EES tracks status transitions. Both snapshot runs are designed to capture the previous day's total production and events.
The 3rd-run delay (~10 min after midnight in a 5-minute interval cycle) accounts for the 10-15 min
MES reflection delay before all logs/lots appear in the systems.

---

## Adding a New RPT Report

### Step 1 — Identify the report

Open the MES UI, navigate to the report, apply your desired filters,
and load the data. Note:
- The report ID (e.g. `RPT40281`)
- Which port it uses (check Wireshark — most use 8080, some use 8081)
- The endpoint (`/RptXPController.do` or `/CommonXPController.do`)

### Step 2 — Capture the POST body

**For port 8080 reports** (proxy interceptor method):

```powershell
# Run as Administrator
cd C:\mes_scraper
python proxy_intercept.py
```

1. Open XPlatform, load the report with your desired filters
2. Wait for the grid to fully load
3. Press Ctrl+C
4. Check `xp_requests.json` — a new `rpt_capture_N` entry is added

**For port 8081 reports** (Wireshark method):

1. Open Wireshark, set filter: `host 107.105.195.34` (no port filter)
2. Start capture
3. Open XPlatform, load the report with your desired filters
4. Wait for the grid to fully load
5. Stop Wireshark, save as `.pcapng`
6. Run the extraction script:

```powershell
python mes_scraper/recapture_rpt40120.py path\to\capture.pcapng
```

This automatically updates `xp_requests.json`.

> **Important:** Use broad filters (avoid specific STEP_ID or date-specific
> filters) so the captured POST body works every day without recapturing.

### Step 3 — Add the column map

In `scraper_direct.py`, add a new column map dictionary:

```python
# ── RPT40XXX — Report Name ────────────────────────────────────────────────────
RPT40XXX_COL_MAP: dict[str, str] = {
    # Binary di-code → human-readable DB column name
    # Verify by decoding the pcapng response and comparing against Excel export
    "di00000262": "lot_no",
    "di00000265": "model_id",
    # ... add all columns
}
```

**How to find the column names:**

```powershell
# Decode the captured response to see all binary column names
python mes_scraper_v2/decode_xp.py path\to\response.bin --cols
```

Then compare against the Excel export from the MES UI to map
each di-code to its human-readable name.

Also add remap and filter functions:

```python
def remap_rpt40xxx_row(row: dict) -> dict:
    return {RPT40XXX_COL_MAP.get(k, k): v for k, v in row.items()}

def filter_rpt40xxx_rows(rows: list[dict]) -> list[dict]:
    # Skip SUM rows and rows without a key identifier
    return [r for r in rows if r.get("lot_no") not in (None, "")]
```

### Step 4 — Add date patching (if needed)

If the report uses date filters, add a patch function.
Check what date fields exist in the POST body:

```python
def _patch_rpt40xxx_post_body(post_data: bytes, jsessionid: str = "") -> bytes:
    # See _patch_rpt40120_post_body() as a reference
    # Patch: StartDate, EndDate, end_date, log_seq, JSESSIONID (port 8081 only)
    ...
```

Call it in `_do_fetch()`:

```python
if report_name in ("rpt40xxx_output",):
    jsessionid = session.cookies.get("JSESSIONID", "")
    post_data = _patch_rpt40xxx_post_body(post_data, jsessionid=jsessionid)
```

### Step 5 — Add the DB table

In `db.py`, add `CREATE TABLE` statements inside `init_db()`:

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS rpt40xxx (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        scraped_at  DATETIME NOT NULL,
        row_index   INT,
        lot_no      VARCHAR(64),
        model_id    VARCHAR(64),
        -- ... all columns from RPT40XXX_COL_MAP
        INDEX idx_scraped_at (scraped_at),
        INDEX idx_lot_no     (lot_no)
    ) ROW_FORMAT=DYNAMIC
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS rpt40xxx_snapshot LIKE rpt40xxx
""")
```

Also add the `INSERT INTO` logic in `insert_rows()`:

```python
elif table_name in ("rpt40xxx", "rpt40xxx_snapshot"):
    # Truncate realtime table
    if table_name == "rpt40xxx":
        cursor.execute("TRUNCATE TABLE rpt40xxx")
    # ... build cols list and data tuples
    # See process_result insert as a reference
```

### Step 6 — Wire into main.py

Add the table mapping:

```python
REPORT_TABLE_MAP = {
    ...
    "rpt40xxx": "rpt40xxx",   # key = xp_requests.json entry name
}
```

Add remap/filter/insert logic in `run_job()`:

```python
elif table == "rpt40xxx":
    rows = [remap_rpt40xxx_row(r) for r in rows]
    rows = filter_rpt40xxx_rows(rows)
    log.info(f"[{report_name}] rpt40xxx: {len(rows)} rows")

if rows:
    ...
    elif table == "rpt40xxx":
        insert_rows("rpt40xxx", rows)
        insert_rows("rpt40xxx_snapshot", rows)
```

### Step 7 — Test

```powershell
# Create the new tables
python -c "from db import init_db; init_db(force=False)"

# Run once and check the output
python main.py --once
```

---

## XPlatform Binary Format Reference

### Wire format

```
Bytes 0-1 : ff ad          (XPlatform magic header)
Bytes 2-N : zlib-compressed payload
```

### Decompressed payload

```
fe 10                      (block start, 2 bytes)
[2B dataset_id]
[2B b1]
[2B b2]
[2B col_count]

-- Column definitions (col_count times) --
[2B name_len][name UTF-8]
[1B type]
[4B max_size]
[1B extra]

-- Row data (until fe 01 end marker) --
  [6B row header]
  -- For each column: TWO value slots --
    slot1: always null/empty (discard)
    slot2: real value

-- Value types --
  0x00           → null
  0x15 / 0x28   → string  (1B type + 2B len + data)
  0x03           → int32   (1B type + 4B big-endian signed)
  0x04           → float64 (1B type + 8B big-endian double)
  0x01           → bool    (1B type + 1B value)

fe 01 [2B dataset_id] [4B ???]   (block end)
```

### Metadata block (always skip)

Every response starts with a metadata block containing:
- `gv_logSeq` — server log sequence
- `gv_ip_addr` — server IP
- `ErrorCode` — 0 = success
- `ErrorMsg` — "Operation succeeded." = success

---

## MES Server Endpoints

| Port | Endpoint | Used by |
|---|---|---|
| 8080 | `POST /RptXPController.do` | RPT40281, RPT40496 |
| 8080 | `POST /CommonXPController.do` | Login logging, session calls |
| 8080 | `POST /login.do` | XPlatform authentication |
| 8080 | `POST /system/xp/getsession.do` | Session setup |
| **8081** | `POST /RptXPController.do` | **RPT40120** |

> **Critical:** XPlatform does NOT use the Windows system proxy.
> Port 8080 traffic can be intercepted via `proxy_intercept.py` (netsh portproxy).
> Port 8081 traffic CANNOT be intercepted this way — use Wireshark instead.

---

## POST Body Structure

Every POST body is `ff ad` + zlib-compressed `fe 10` block with one row of parameters.

### Common fields in every RPT POST body

| Field | Description |
|---|---|
| `gv_menu_id` | Report ID (e.g. `RPT40120`) |
| `gv_emp_no` | Employee number |
| `gv_site_code` | Site code (e.g. `E502AA`) |
| `gv_div_code` | Division code (e.g. `PG04`) |
| `gv_endp_code` | Endpoint code (e.g. `LCR`) |
| `gv_language_code` | Language (e.g. `ENG`) |
| `gv_app_id` | App ID (e.g. `RPT`) |
| `log_seq` | Session sequence — **must patch** |
| `end_date` | Request timestamp — **must patch** |
| `sel_col_sql` | SQL column list mapping di-codes to DB columns |
| `JSESSIONID` | Session ID embedded in body — **must patch for port 8081** |

### Fields that MUST be patched before replaying

| Field | Format | Patch to |
|---|---|---|
| `StartDate` | `YYYYMMDD000000` | Today 00:00 |
| `EndDate` | `YYYYMMDD000000` | Tomorrow 00:00 |
| `end_date` | `YYYYMMDDHHmmss` | Current datetime |
| `log_seq` | 10-digit integer | Current Unix timestamp |
| `JSESSIONID` (in body) | XP string value | Fresh session ID |

---

## Login Flow

The scraper uses XPlatform native login (not web portal):

1. `GET /xp/frame/common/Login.xfdl` → get initial JSESSIONID cookie
2. `POST /login.do` with XP binary body:
   - Password: SHA-256 hashed, then Base64-encoded
   - Fields: `emp_no`, `user_pwd`, `gv_site_code`, `gv_div_code`, etc.
3. `POST /system/xp/getsession.do` → complete session setup

The resulting JSESSIONID works for both port 8080 and port 8081.

> Note: `/login.do` returns HTTP 500 but still creates a valid session.
> This is normal behavior for this MES server.

---

## Configuration (.env)

```env
MES_URL=http://107.105.195.34:8080
MES_HOST=107.105.195.34
MES_PORT=8080
LOCAL_IP=107.105.55.217

MES_USERNAME=21278703
MES_PASSWORD=semphil01*

DB_HOST=127.0.0.1
DB_PORT=15000
DB_NAME=mes_data
DB_USER=root
DB_PASSWORD=your_db_password

SCRAPE_INTERVAL_MINUTES=5
```

---

## Running the Scraper

```powershell
# First time setup — create all tables
python main.py --reset

# Run once (online sync test)
python main.py --once

# Run once (offline mock replay test)
python main.py --once --offline

# Run scheduler standalone (every 5 minutes)
python main.py

# Drop only RPT40120 tables and recreate
python -c "
from db import get_connection, init_db
conn = get_connection()
cur = conn.cursor()
for t in ['process_result','process_result_snapshot','process_trackout','process_trackout_snapshot']:
    cur.execute(f'DROP TABLE IF EXISTS {t}')
conn.commit(); cur.close(); conn.close()
init_db(force=False)
"
```

### Historical Backfills and Repair Utilities

```powershell
# Backfill snapshot tables for a range (e.g. Jan 1 to Apr 28, 2026)
python backfill_snapshots.py --from 2026-01-01 --to 2026-04-28

# Backfill only EES data
python backfill_snapshots.py --ees-only --from 2026-01-01 --to 2026-04-28

# Clean/repair corrupted equipment names in database (caches clean names and corrects garbage ones)
python repair_equipment_names.py

# Run repair dry-run to preview counts of corrupted entries
python repair_equipment_names.py --dry-run
```

---

## Troubleshooting

### 0 rows returned for RPT40120

**Cause 1:** Date filter mismatch — the STEP_ID or other filters in the
captured POST body don't match today's production.

**Fix:** Recapture with broader filters (clear STEP_ID, use "All"):
```powershell
# Capture with Wireshark (filter: host 107.105.195.34)
# Load RPT40120 with broad filters, wait for full load
# Save as .pcapng, then:
python mes_scraper/recapture_rpt40120.py path\to\capture.pcapng
```

**Cause 2:** No production data for today's date range yet.

**Fix:** Wait — data appears as lots finish throughout the day.

### Session expired / HTML response

The JSESSIONID cookie expired. The scraper auto-re-logins.
If it keeps failing, check `MES_USERNAME` and `MES_PASSWORD` in `.env`.

### Port 8081 returns error but port 8080 works

Port 8081 requires the JSESSIONID to also be embedded inside the POST body.
The `_patch_rpt40120_post_body()` function handles this automatically.

### proxy_intercept.py captures nothing for a new report

XPlatform may be connecting directly (bypassing the Windows proxy).
Use Wireshark instead with filter `host 107.105.195.34`.

---

## Report-Specific Notes

### RPT40281 — WIP Status

- Port 8080, no date filter needed
- Realtime snapshot: saves current WIP state once per day
- ~2200 rows, 225 columns

### RPT40496 — Monthly Plan

- Port 8080, date filter = current month (auto-patched)
- ~1445 rows, 49 columns

### RPT40120 — Process Result / Trackout

- Port **8081** — requires Wireshark capture
- Two separate POST bodies: output (MAIN_STEP_YN=Y) and trackout (MAIN_STEP_YN=N)
- Date filter: today → tomorrow (realtime), yesterday → today (snapshot)
- Snapshot fires on 3rd run of the day (~10 min after midnight)
- ~500 rows output, ~430 rows trackout, 234 columns each
- JSESSIONID must be patched inside the POST body (not just the cookie)

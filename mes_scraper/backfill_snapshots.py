"""
Backfill Snapshot Script
========================
One-time script to populate snapshot tables for historical dates.
Fetches ONE DAY per request — the server cannot handle wider ranges.

Fills:
  - process_result_snapshot       (RPT40120 Output)
  - process_trackout_snapshot     (RPT40120 Trackout)
  - eqp_detailed_history_snapshot (EES EPT0184)

Usage:
    # Full backfill Jan 1 → Apr 28 2026 (default)
    python backfill_snapshots.py

    # Custom range
    python backfill_snapshots.py --from 2026-03-01 --to 2026-04-28

    # One system only
    python backfill_snapshots.py --ees-only
    python backfill_snapshots.py --mes-only

    # Preview what would run (no DB writes, no network calls)
    python backfill_snapshots.py --dry-run

    # Resume after crash — already-filled dates are skipped automatically
    python backfill_snapshots.py

Safety features:
  - 1 day per request (server limit)
  - Skip dates already in the snapshot table (safe to re-run / resume)
  - Progress log file (backfill_progress.log) — shows exactly where we are
  - Retry on timeout (up to 3 attempts per day)
  - Configurable delay between requests (default 5s)
  - Timeout per request: 120s (large days can be slow)
"""

import sys
import os
import time
import logging
import argparse
import zlib
import re
import struct
from datetime import datetime, timezone, timedelta, date
from dotenv import load_dotenv

load_dotenv()

_HERE = os.path.dirname(__file__)

# ── Logging: console + progress file ─────────────────────────────────────────
PROGRESS_LOG = os.path.join(_HERE, "backfill_progress.log")

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROGRESS_LOG, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

MANILA_TZ = timezone(timedelta(hours=8))

REQUEST_TIMEOUT = 180   # seconds per request — historical dates have more data
MAX_RETRIES     = 3     # retry attempts per day on timeout/error
RETRY_DELAY     = 60    # seconds between retries — server needs time to recover


# ── Date helpers ──────────────────────────────────────────────────────────────

def date_range(start: date, end: date):
    """Yield each date from start to end inclusive."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


# ── DB helpers ────────────────────────────────────────────────────────────────

def _already_has_snapshot(table: str, target_date: date) -> int:
    """Return row count for target_date in the snapshot table. 0 = not yet filled."""
    from db import get_connection
    conn = get_connection()
    cur  = conn.cursor()
    day_start = target_date.strftime("%Y-%m-%d 00:00:00")
    day_end   = (target_date + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    cur.execute(
        f"SELECT COUNT(*) FROM {table} WHERE scraped_at >= %s AND scraped_at < %s",
        (day_start, day_end),
    )
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def _insert_with_date(table: str, rows: list[dict], target_date: date):
    """
    Insert rows into a snapshot table with scraped_at = target_date 12:00:00.
    Using noon makes backfill rows visually distinct from live midnight runs.
    """
    import db as db_module
    from db import insert_rows

    original_now = db_module._now_manila
    target_ts    = target_date.strftime("%Y-%m-%d 12:00:00")
    db_module._now_manila = lambda: target_ts
    try:
        insert_rows(table, rows)
    finally:
        db_module._now_manila = original_now


# ── RPT40120 (MES) backfill ───────────────────────────────────────────────────

def _patch_rpt40120_for_date(post_data: bytes, target_date: date,
                              jsid: str = "") -> bytes:
    """
    Patch a captured RPT40120 POST body for a specific calendar day.
    StartDate = target_date 00:00:00
    EndDate   = target_date + 1 day 00:00:00
    """
    start_bytes = (target_date.strftime("%Y%m%d") + "000000").encode()
    end_bytes   = ((target_date + timedelta(days=1)).strftime("%Y%m%d") + "000000").encode()

    dec = zlib.decompress(post_data[2:])

    # Replace StartDate and EndDate
    all_dates = re.findall(rb'20[2-9][0-9][0-1][0-9][0-3][0-9]000000', dec)
    if len(all_dates) >= 2:
        dec = dec.replace(all_dates[0], start_bytes, 1)
        all_dates2 = re.findall(rb'20[2-9][0-9][0-1][0-9][0-3][0-9]000000', dec)
        replaced = False
        for d in all_dates2:
            if d != start_bytes:
                dec = dec.replace(d, end_bytes, 1)
                replaced = True
                break
        if not replaced:
            # Both are start_bytes — replace second occurrence
            idx  = dec.find(start_bytes)
            idx2 = dec.find(start_bytes, idx + 1)
            if idx2 != -1:
                dec = dec[:idx2] + end_bytes + dec[idx2 + len(end_bytes):]
    elif len(all_dates) == 1:
        dec = dec.replace(all_dates[0], start_bytes, 1)

    # Patch log_seq
    log_seq  = str(int(time.time())).encode()
    log_seqs = re.findall(rb'[0-9]{10}', dec)
    for old_ls in log_seqs:
        if 8000000000 <= int(old_ls) <= 9999999999:
            dec = dec.replace(old_ls, log_seq, 1)
            break

    # Patch JSESSIONID (required for port 8081)
    if jsid:
        jsid_marker = b'JSESSIONID'
        idx = dec.find(jsid_marker)
        if idx != -1:
            p = idx + len(jsid_marker)
            if p < len(dec):
                vt = dec[p]; p += 1
                if vt in (0x15, 0x28) and p + 2 <= len(dec):
                    vl = struct.unpack_from('>H', dec, p)[0]; p += 2 + vl
            if p < len(dec):
                vt = dec[p]
                if vt in (0x15, 0x28) and p + 3 <= len(dec):
                    vl = struct.unpack_from('>H', dec, p + 1)[0]
                    old_jsid  = dec[p + 3:p + 3 + vl]
                    new_jsid  = jsid.encode('utf-8')
                    if old_jsid != new_jsid:
                        old_chunk = bytes([vt]) + struct.pack('>H', vl) + old_jsid
                        new_chunk = bytes([vt]) + struct.pack('>H', len(new_jsid)) + new_jsid
                        dec = dec[:p] + new_chunk + dec[p + len(old_chunk):]

    return b'\xff\xad' + zlib.compress(dec, level=6)


def backfill_rpt40120_day(target_date: date, session,
                           dry_run: bool = False) -> dict[str, int]:
    """
    Fetch and store RPT40120 output + trackout for one calendar day.
    Returns {'output': N, 'trackout': N}.
    """
    from scraper_direct import (
        load_captured_requests, parse_xplatform_binary,
        remap_rpt40120_row, filter_rpt40120_rows,
    )

    results = {'output': 0, 'trackout': 0}

    captured = load_captured_requests()

    for report_name, table_name, result_key in [
        ("rpt40120_output",   "process_result_snapshot",   "output"),
        ("rpt40120_trackout", "process_trackout_snapshot", "trackout"),
    ]:
        if report_name not in captured:
            log.warning(f"    {report_name} not in xp_requests.json — skipping")
            continue

        # Skip if already filled
        existing = _already_has_snapshot(table_name, target_date)
        if existing > 0:
            log.info(f"    {table_name} {target_date} — {existing} rows already exist — skipping")
            results[result_key] = existing
            continue

        if dry_run:
            log.info(f"    [DRY RUN] Would fetch {report_name} for {target_date}")
            continue

        entry     = captured[report_name][-1]
        post_data = bytes.fromhex(entry["post_data_hex"])
        jsid      = session.cookies.get("JSESSIONID", "")
        patched   = _patch_rpt40120_for_date(post_data, target_date, jsid)

        # Verify patched dates
        dec_check   = zlib.decompress(patched[2:])
        dates_found = re.findall(rb'20[2-9][0-9][0-1][0-9][0-3][0-9]000000', dec_check)
        log.info(f"    {report_name} dates: {[d.decode() for d in dates_found]}")

        headers = {
            k: v for k, v in entry.get("headers", {}).items()
            if k.lower() not in ("content-length", "host", "proxy-connection")
        }

        # Retry loop
        rows = []
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = session.post(
                    entry["url"], data=patched, headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
                raw  = resp.content
                log.info(f"    {report_name} → HTTP {resp.status_code}  {len(raw):,} bytes")
                rows = parse_xplatform_binary(raw)
                rows = [remap_rpt40120_row(r) for r in rows]
                rows = filter_rpt40120_rows(rows)
                log.info(f"    {report_name} → {len(rows)} rows")
                break
            except Exception as e:
                log.warning(f"    {report_name} attempt {attempt}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    log.error(f"    {report_name} all retries exhausted for {target_date}")

        if rows:
            _insert_with_date(table_name, rows, target_date)
            results[result_key] = len(rows)
        else:
            log.info(f"    {report_name} {target_date} — 0 rows (no production that day)")

    return results


# ── EES backfill ──────────────────────────────────────────────────────────────

def backfill_ees_day(target_date: date, dry_run: bool = False) -> int:
    """
    Fetch and store EES EPT0184 for one calendar day.
    Uses the same _fetch_ees() code path as main.py — guaranteed to work.
    Returns number of rows inserted (0 if already exists or no data).
    """
    from ees_scraper import _fetch_ees, clean_ees_rows

    table = "eqp_detailed_history_snapshot"

    # Skip if already filled
    existing = _already_has_snapshot(table, target_date)
    if existing > 0:
        log.info(f"    {table} {target_date} — {existing} rows already exist — skipping")
        return existing

    fr_date = target_date.strftime("%Y-%m-%d") + " 00:00"
    to_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00"
    log.info(f"    EES fetch: {fr_date} → {to_date}")

    if dry_run:
        log.info(f"    [DRY RUN] Would fetch EES for {target_date}")
        return 0

    # Retry loop — same backoff as before
    rows = []
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            rows = _fetch_ees(date_range=(fr_date, to_date))
            log.info(f"    EES → {len(rows)} rows")
            break
        except Exception as e:
            wait = RETRY_DELAY * attempt
            log.warning(f"    EES attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                log.info(f"    Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                log.error(f"    EES all retries exhausted for {target_date}")

    if rows:
        _insert_with_date(table, rows, target_date)
        return len(rows)
    else:
        log.info(f"    EES {target_date} — 0 rows (no equipment events that day)")
        return 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Backfill snapshot tables — 1 day per request"
    )
    parser.add_argument(
        "--from", dest="from_date", default="2026-01-01",
        help="Start date inclusive (YYYY-MM-DD)  default: 2026-01-01",
    )
    parser.add_argument(
        "--to", dest="to_date", default="2026-04-28",
        help="End date inclusive (YYYY-MM-DD)    default: 2026-04-28",
    )
    parser.add_argument("--ees-only", action="store_true",
                        help="Only backfill EES snapshots")
    parser.add_argument("--mes-only", action="store_true",
                        help="Only backfill RPT40120 snapshots")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Show plan only — no network calls, no DB writes")
    parser.add_argument(
        "--delay", type=float, default=10.0,
        help="Seconds to wait between days (default: 10)",
    )
    args = parser.parse_args()

    start  = parse_date(args.from_date)
    end    = parse_date(args.to_date)
    days   = list(date_range(start, end))
    do_mes = not args.ees_only
    do_ees = not args.mes_only

    log.info("=" * 65)
    log.info("  Snapshot Backfill")
    log.info(f"  Date range : {start} → {end}  ({len(days)} days)")
    log.info(f"  MES RPT40120 : {'YES' if do_mes else 'NO'}")
    log.info(f"  EES EPT0184  : {'YES' if do_ees else 'NO'}")
    log.info(f"  Dry run      : {'YES' if args.dry_run else 'NO'}")
    log.info(f"  Delay        : {args.delay}s between days")
    log.info(f"  Timeout      : {REQUEST_TIMEOUT}s per request")
    log.info(f"  Retries      : {MAX_RETRIES} per request")
    log.info(f"  Progress log : {PROGRESS_LOG}")
    log.info("=" * 65)

    # Estimate time
    requests_per_day = (2 if do_mes else 0) + (1 if do_ees else 0)
    est_seconds = len(days) * (requests_per_day * 15 + args.delay)
    log.info(f"  Estimated time: ~{est_seconds/60:.0f} min (assuming ~15s/request)")
    log.info("  Skips dates already in snapshot tables — safe to re-run.\n")

    # MES needs a session
    session = None
    if do_mes and not args.dry_run:
        from scraper_direct import get_session
        log.info("Logging into MES (needed for RPT40120 JSESSIONID)...")
        session = get_session()
        log.info("MES session ready.\n")

    # Counters
    total = {'output': 0, 'trackout': 0, 'ees': 0, 'errors': 0, 'skipped': 0}

    for i, d in enumerate(days, 1):
        log.info(f"[{i:3d}/{len(days)}] {d} ─────────────────────────────")

        if do_mes:
            try:
                r = backfill_rpt40120_day(d, session, dry_run=args.dry_run)
                total['output']   += r.get('output', 0)
                total['trackout'] += r.get('trackout', 0)
            except Exception as e:
                log.error(f"  MES {d} unexpected error: {e}")
                total['errors'] += 1
            if not args.dry_run:
                time.sleep(args.delay)

        if do_ees:
            try:
                n = backfill_ees_day(d, dry_run=args.dry_run)
                total['ees'] += n
            except Exception as e:
                log.error(f"  EES {d} unexpected error: {e}")
                total['errors'] += 1
            if not args.dry_run:
                time.sleep(args.delay)

    log.info("\n" + "=" * 65)
    log.info("  Backfill Complete")
    log.info(f"  Days processed : {len(days)}")
    if do_mes:
        log.info(f"  process_result_snapshot    : {total['output']:,} rows")
        log.info(f"  process_trackout_snapshot  : {total['trackout']:,} rows")
    if do_ees:
        log.info(f"  eqp_detailed_history_snapshot : {total['ees']:,} rows")
    if total['errors']:
        log.info(f"  Errors : {total['errors']}  (check {PROGRESS_LOG})")
    log.info("=" * 65)


if __name__ == "__main__":
    main()

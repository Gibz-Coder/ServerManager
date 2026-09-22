"""
MES scraper entry point.

Usage:
    python main.py          # run immediately then every N minutes (scheduled)
    python main.py --once   # run once and exit
"""

import sys
import time
import logging
import schedule
import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from db import init_db, insert_rows
from scraper_direct import (
    fetch_all, filter_wip_rows, filter_monthly_rows,
    remap_wip_row, remap_monthly_row,
    filter_rpt40120_rows, remap_rpt40120_row,
    _patch_rpt40120_post_body, parse_xplatform_binary,
    get_session, load_captured_requests,
)
from ees_scraper import fetch_ees_history, fetch_ees_history_yesterday

load_dotenv()

MANILA_TZ = timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.Formatter.converter = lambda *args: datetime.now(MANILA_TZ).timetuple()
log = logging.getLogger(__name__)

INTERVAL = int(os.getenv("SCRAPE_INTERVAL_MINUTES", 5))
REQUESTS_FILE = os.path.join(os.path.dirname(__file__), "xp_requests.json")

# Fixed mappings for named captures
REPORT_TABLE_MAP = {
    "wip_status":        "wip_status",
    "monthly_plan":      "monthly_plan",
    "rpt40120_output":   "process_result",
    "rpt40120_trackout": "process_trackout",
}

# Run counter — tracks how many times run_job has been called today
_run_counter: dict = {}   # key: date string "YYYY-MM-DD" → count


def _today_str():
    return datetime.now(MANILA_TZ).strftime("%Y-%m-%d")


def _increment_run_counter() -> int:
    """Increment and return today's run count."""
    today = _today_str()
    _run_counter[today] = _run_counter.get(today, 0) + 1
    # Clean up old dates
    for k in list(_run_counter.keys()):
        if k != today:
            del _run_counter[k]
    return _run_counter[today]


def _fetch_rpt40120_yesterday(session, report_name: str) -> list:
    """
    Fetch RPT40120 data for YESTERDAY (StartDate=yesterday, EndDate=today).
    Used for the daily snapshot — captures the previous day's completed production.
    Allows 10-15 min MES reflection delay by only running on 3rd+ scrape of the day.
    """
    import requests as req_lib
    try:
        captured = load_captured_requests()
        entry = captured[report_name][-1]
        post_data = bytes.fromhex(entry["post_data_hex"])

        # Patch with YESTERDAY's date range instead of today's
        now       = datetime.now(MANILA_TZ)
        yesterday = (now - timedelta(days=1)).strftime("%Y%m%d")
        today     = now.strftime("%Y%m%d")

        import zlib, re, struct, time as _time
        dec = zlib.decompress(post_data[2:])

        yesterday_start = (yesterday + "000000").encode()
        today_start     = (today     + "000000").encode()

        # Replace StartDate → yesterday, EndDate → today
        all_dates = re.findall(rb'20[2-9][0-9][0-1][0-9][0-3][0-9]000000', dec)
        if len(all_dates) >= 2:
            dec = dec.replace(all_dates[0], yesterday_start, 1)
            all_dates2 = re.findall(rb'20[2-9][0-9][0-1][0-9][0-3][0-9]000000', dec)
            for d in all_dates2:
                if d != yesterday_start:
                    dec = dec.replace(d, today_start, 1)
                    break
            else:
                # Both are yesterday_start — replace second occurrence
                idx  = dec.find(yesterday_start)
                idx2 = dec.find(yesterday_start, idx + 1)
                if idx2 != -1:
                    dec = dec[:idx2] + today_start + dec[idx2 + len(today_start):]

        # Patch log_seq and JSESSIONID
        log_seq = str(int(_time.time())).encode()
        log_seqs = re.findall(rb'[0-9]{10}', dec)
        for old_ls in log_seqs:
            if 8000000000 <= int(old_ls) <= 9999999999:
                dec = dec.replace(old_ls, log_seq, 1)
                break

        jsid = session.cookies.get("JSESSIONID", "")
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
                        old_jsid = dec[p + 3:p + 3 + vl]
                        new_jsid = jsid.encode('utf-8')
                        if old_jsid != new_jsid:
                            old_chunk = bytes([vt]) + struct.pack('>H', vl) + old_jsid
                            new_chunk = bytes([vt]) + struct.pack('>H', len(new_jsid)) + new_jsid
                            dec = dec[:p] + new_chunk + dec[p + len(old_chunk):]

        patched = b'\xff\xad' + zlib.compress(dec, level=6)

        # Verify dates
        dec_check = zlib.decompress(patched[2:])
        dates = re.findall(rb'20[2-9][0-9][0-1][0-9][0-3][0-9]000000', dec_check)
        log.info(f"  [snapshot] {report_name} yesterday range: {[d.decode() for d in dates]}")

        headers = {
            k: v for k, v in entry.get("headers", {}).items()
            if k.lower() not in ("content-length", "host", "proxy-connection")
        }
        resp = session.post(entry["url"], data=patched, headers=headers, timeout=60)
        raw  = resp.content
        log.info(f"  [snapshot] {report_name} → {resp.status_code}  {len(raw)} bytes")

        rows = parse_xplatform_binary(raw)
        rows = [remap_rpt40120_row(r) for r in rows]
        rows = filter_rpt40120_rows(rows)
        log.info(f"  [snapshot] {report_name} → {len(rows)} rows for yesterday")
        return rows

    except Exception as e:
        log.error(f"  [snapshot] {report_name} failed: {e}")
        return []


def _resolve_table_map():
    """
    Map rpt_capture_* entries to tables using referer URL or response size.
    RPT40496 referer contains 'MonResultRateView' → monthly_plan
    RPT40281 referer contains 'WipStatusView' or similar → wip_status
    Fallback: largest response → wip_status, second → monthly_plan
    """
    if not os.path.exists(REQUESTS_FILE):
        return {}
    with open(REQUESTS_FILE, encoding="utf-8") as f:
        captured = json.load(f)

    captures = {
        k: v for k, v in captured.items()
        if k.startswith("rpt_capture_")
    }
    if not captures:
        return {}

    mapping = {}
    for name, entries in captures.items():
        referer = entries[-1].get("headers", {}).get("referer", "").lower()
        if "monresultrate" in referer or "monthly" in referer:
            mapping[name] = "monthly_plan"
            log.info(f"Mapped {name} → monthly_plan (referer match)")
        elif "wip" in referer or "wipstatus" in referer or "reportbasicview" in referer:
            mapping[name] = "wip_status"
            log.info(f"Mapped {name} → wip_status (referer match)")

    # Fallback for anything not matched by referer
    unmatched = [k for k in captures if k not in mapping]
    if unmatched:
        sized = sorted(
            unmatched,
            key=lambda k: captures[k][-1].get("response_size", 0),
            reverse=True
        )
        tables_used = set(mapping.values())
        for k in sized:
            if "wip_status" not in tables_used:
                mapping[k] = "wip_status"
                tables_used.add("wip_status")
                log.info(f"Mapped {k} ({captures[k][-1].get('response_size',0)} bytes) → wip_status (size fallback)")
            elif "monthly_plan" not in tables_used:
                mapping[k] = "monthly_plan"
                tables_used.add("monthly_plan")
                log.info(f"Mapped {k} ({captures[k][-1].get('response_size',0)} bytes) → monthly_plan (size fallback)")

    return mapping


def run_job(offline: bool = False):
    log.info("=== Starting MES scrape job ===")

    run_count = _increment_run_counter()
    log.info(f"Run #{run_count} today ({_today_str()})")

    if not os.path.exists(REQUESTS_FILE):
        log.error(
            "xp_requests.json not found. "
            "Run the proxy interceptor first:  python proxy_intercept.py"
        )
        return

    # Merge fixed + auto-resolved table mappings
    table_map = {**REPORT_TABLE_MAP, **_resolve_table_map()}

    results = fetch_all(offline=offline)

    # Shared session for snapshot fetch (reuse from fetch_all if possible)
    _snapshot_session = None

    for report_name, rows in results.items():
        table = table_map.get(report_name)
        if not table:
            log.warning(f"[{report_name}] No table mapping — skipping.")
            continue
        if rows:
            if table == "wip_status":
                rows = [remap_wip_row(r) for r in rows]
                before = len(rows)
                rows = filter_wip_rows(rows)
                log.info(f"[{report_name}] wip_status: {before} → {len(rows)} rows after filter")
            elif table == "monthly_plan":
                log.info(f"[{report_name}] raw keys sample: {list(rows[0].keys())[:10]}")
                log.info(f"[{report_name}] raw values sample: {list(rows[0].values())[:10]}")
                rows = [remap_monthly_row(r) for r in rows]
                log.info(f"[{report_name}] remapped keys sample: {list(rows[0].keys())[:10]}")
                log.info(f"[{report_name}] remapped values sample: {list(rows[0].values())[:10]}")
                before = len(rows)
                rows = filter_monthly_rows(rows)
                log.info(f"[{report_name}] monthly_plan: {before} → {len(rows)} rows after filter")
            elif table in ("process_result", "process_trackout"):
                rows = [remap_rpt40120_row(r) for r in rows]
                before = len(rows)
                rows = filter_rpt40120_rows(rows)
                log.info(f"[{report_name}] {table}: {before} → {len(rows)} rows after filter")

            if rows:
                if table == "wip_status":
                    insert_rows("wip_status", rows)
                    insert_rows("wip_status_snapshot", rows)
                elif table == "monthly_plan":
                    insert_rows("monthly_plan", rows)
                    insert_rows("monthly_plan_snapshot", rows)
                elif table == "process_result":
                    # Realtime: today's data
                    insert_rows("process_result", rows)
                    # Snapshot: yesterday's completed data, only on 3rd+ run of the day
                    # (allows 10-15 min MES reflection delay after midnight)
                    if run_count >= 3:
                        if _snapshot_session is None:
                            _snapshot_session = get_session()
                        snap_rows = _fetch_rpt40120_yesterday(_snapshot_session, "rpt40120_output")
                        if snap_rows:
                            insert_rows("process_result_snapshot", snap_rows)
                        else:
                            log.info("[process_result_snapshot] 0 rows for yesterday — skipping snapshot")
                    else:
                        log.info(f"[process_result_snapshot] Run #{run_count} — waiting for run #3 before snapshot")
                elif table == "process_trackout":
                    # Realtime: today's data
                    insert_rows("process_trackout", rows)
                    # Snapshot: yesterday's completed data, only on 3rd+ run of the day
                    if run_count >= 3:
                        if _snapshot_session is None:
                            _snapshot_session = get_session()
                        snap_rows = _fetch_rpt40120_yesterday(_snapshot_session, "rpt40120_trackout")
                        if snap_rows:
                            insert_rows("process_trackout_snapshot", snap_rows)
                        else:
                            log.info("[process_trackout_snapshot] 0 rows for yesterday — skipping snapshot")
                    else:
                        log.info(f"[process_trackout_snapshot] Run #{run_count} — waiting for run #3 before snapshot")
            else:
                log.warning(f"[{report_name}] All rows filtered out.")
        else:
            log.warning(f"[{report_name}] No rows returned.")

    log.info("=== Scrape job complete ===")


def run_ees_job(offline: bool = False):
    """
    Fetch EES Equipment Detailed History and store in DB.

    Mirrors RPT40120 snapshot logic:
      - Realtime table (eqp_detailed_history):  truncated + refilled every run with TODAY's data
      - Snapshot table (eqp_detailed_history_snapshot): inserted once per day on run #3+
        using YESTERDAY's data, allowing ~10-15 min EES reflection delay after midnight
    """
    log.info("=== Starting EES scrape job ===")
    try:
        # ── Realtime: today's data ────────────────────────────────────────────
        rows = fetch_ees_history(offline=offline)
        if rows:
            log.info(f"[ees] {len(rows)} rows fetched for today")
            insert_rows("eqp_detailed_history", rows)
        else:
            log.warning("[ees] No rows returned from EES (today)")

        # ── Snapshot: yesterday's data, only on run #3+ ───────────────────────
        run_count = _run_counter.get(_today_str(), 1)
        if not offline:
            if run_count >= 3:
                log.info(f"[ees snapshot] Run #{run_count} — fetching yesterday's data...")
                snap_rows = fetch_ees_history_yesterday()
                if snap_rows:
                    insert_rows("eqp_detailed_history_snapshot", snap_rows)
                    log.info(f"[ees snapshot] {len(snap_rows)} rows saved for yesterday")
                else:
                    log.info("[ees snapshot] 0 rows for yesterday — skipping snapshot")
            else:
                log.info(f"[ees snapshot] Run #{run_count} — waiting for run #3 before snapshot")

    except Exception as e:
        log.error(f"[ees] Job failed: {e}")
    log.info("=== EES scrape job complete ===")


if __name__ == "__main__":
    once_mode = "--once" in sys.argv
    offline_mode = "--offline" in sys.argv

    init_db(force="--reset" in sys.argv)

    if once_mode or offline_mode:
        run_job(offline=offline_mode)
        run_ees_job(offline=offline_mode)
    else:
        log.info(f"Scheduler started — running every {INTERVAL} minutes.")
        run_job()
        run_ees_job()
        schedule.every(INTERVAL).minutes.do(run_job)
        schedule.every(INTERVAL).minutes.do(run_ees_job)
        while True:
            schedule.run_pending()
            time.sleep(30)

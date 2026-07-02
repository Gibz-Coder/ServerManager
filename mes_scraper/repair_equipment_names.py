"""
Repair equipment_name in eqp_detailed_history and eqp_detailed_history_snapshot.

Fixes three classes of bad values:
  1. Garbage prefix bytes  e.g. '+VI259_...' → 'VI259_...'
  2. Pure garbage          e.g. '\\xef\\xbf\\xbd+V' → NULL then filled from cache
  3. NULL / empty          → filled from the per-equipment cache built from good rows

Run once after backfill:
    python repair_equipment_names.py

Dry-run (shows counts, no writes):
    python repair_equipment_names.py --dry-run
"""

import sys
import re
import logging
import argparse
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

VALID_NAME = re.compile(r'^(VI\d{3}_|MAVI\d{2}_)')


def get_conn():
    import os
    # Use env vars if set, otherwise fall back to the local dump DB
    return mysql.connector.connect(
        host    = os.getenv("REPAIR_DB_HOST",     "127.0.0.1"),
        port    = int(os.getenv("REPAIR_DB_PORT", "3306")),
        database= os.getenv("REPAIR_DB_NAME",     "mes_data"),
        user    = os.getenv("REPAIR_DB_USER",     "root"),
        password= os.getenv("REPAIR_DB_PASSWORD", "LenoBert@21"),
    )


def clean_name(name: str) -> str:
    """
    Return a clean equipment_name or empty string if unrecoverable.
    Valid format: VI + 3 digits + underscore + rest
    """
    if not name:
        return ''
    if VALID_NAME.match(name):
        return name
    # Try stripping 1-3 leading garbage bytes
    for skip in range(1, 4):
        if len(name) > skip and VALID_NAME.match(name[skip:]):
            return name[skip:]
    return ''


def repair_table(table: str, dry_run: bool):
    log.info(f"\n{'='*55}")
    log.info(f"Repairing: {table}")
    log.info(f"{'='*55}")

    conn = get_conn()
    cur  = conn.cursor()

    # ── Step 1: Build equipment_code → correct_name cache from good rows ──────
    log.info("Building equipment name cache from valid rows...")
    cur.execute(f"""
        SELECT equipment_code, equipment_name
        FROM {table}
        WHERE equipment_name REGEXP '^(VI[0-9]{{3}}_|MAVI[0-9]{{2}}_)'
        GROUP BY equipment_code, equipment_name
        ORDER BY equipment_code, COUNT(*) DESC
    """)
    cache: dict[str, str] = {}
    for code, name in cur.fetchall():
        if code and code not in cache:   # keep the most-frequent name
            cache[code] = name
    log.info(f"  Cache built: {len(cache)} equipment codes with valid names")

    # ── Step 2: Find all rows needing repair ──────────────────────────────────
    log.info("Scanning for rows needing repair...")
    cur.execute(f"""
        SELECT id, equipment_code, equipment_name
        FROM {table}
        WHERE equipment_name IS NULL
           OR equipment_name = ''
           OR equipment_name NOT REGEXP '^(VI[0-9]{{3}}_|MAVI[0-9]{{2}}_)'
    """)
    bad_rows = cur.fetchall()
    log.info(f"  Found {len(bad_rows):,} rows needing repair")

    if not bad_rows:
        log.info("  Nothing to fix.")
        cur.close(); conn.close()
        return

    # ── Step 3: Categorize and prepare fixes ─────────────────────────────────
    fixable_clean   = []   # (id, new_name) — garbage prefix stripped
    fixable_cache   = []   # (id, new_name) — filled from cache
    unfixable       = []   # (id,)          — no good name available

    for row_id, code, name in bad_rows:
        # Try to clean the raw value first
        cleaned = clean_name(name or '')
        if cleaned:
            fixable_clean.append((row_id, cleaned))
            # Also update cache if this code wasn't there
            if code and code not in cache:
                cache[code] = cleaned
        elif code and code in cache:
            fixable_cache.append((row_id, cache[code]))
        else:
            unfixable.append(row_id)

    log.info(f"  Fixable by cleaning prefix : {len(fixable_clean):,}")
    log.info(f"  Fixable from cache         : {len(fixable_cache):,}")
    log.info(f"  Unfixable (no known name)  : {len(unfixable):,}")

    if dry_run:
        log.info("  [DRY RUN] No changes written.")
        cur.close(); conn.close()
        return

    # ── Step 4: Apply fixes in batches ────────────────────────────────────────
    BATCH = 1000

    all_fixes = fixable_clean + fixable_cache
    log.info(f"Applying {len(all_fixes):,} fixes in batches of {BATCH}...")

    updated = 0
    for i in range(0, len(all_fixes), BATCH):
        batch = all_fixes[i:i + BATCH]
        # Build CASE statement for batch update
        cases  = " ".join(f"WHEN {row_id} THEN %s" for row_id, _ in batch)
        ids    = ", ".join(str(row_id) for row_id, _ in batch)
        values = [name for _, name in batch]
        sql = f"""
            UPDATE {table}
            SET equipment_name = CASE id {cases} END
            WHERE id IN ({ids})
        """
        cur.execute(sql, values)
        updated += cur.rowcount
        if (i // BATCH + 1) % 10 == 0:
            conn.commit()
            log.info(f"  ... {updated:,} rows updated so far")

    conn.commit()
    log.info(f"  Done. {updated:,} rows updated.")

    if unfixable:
        log.info(f"  {len(unfixable):,} rows remain NULL (equipment codes not seen elsewhere)")

    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Repair equipment_name values")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show counts only, no DB writes")
    args = parser.parse_args()

    if args.dry_run:
        log.info("DRY RUN — no changes will be written\n")

    for table in ("eqp_detailed_history", "eqp_detailed_history_snapshot"):
        repair_table(table, dry_run=args.dry_run)

    log.info("\nRepair complete.")


if __name__ == "__main__":
    main()

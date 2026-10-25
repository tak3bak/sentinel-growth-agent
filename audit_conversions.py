#!/usr/bin/env python3
"""Nomadik Security Sentinel - Conversion & Engagement Auditor

Audits active dispatched leads, dynamically discovers schema columns,
and reports subscriptions, conversion rates, and stale follow-ups.
"""

import sqlite3
import sys

DB_PATH = "leads.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    print("=" * 60)
    print(" Nomadik Security Operations - Pipeline Metric Summary")
    print("=" * 60)

    # 1. Total leads breakdown
    c.execute("SELECT status, count(*) FROM leads GROUP BY status ORDER BY count(*) DESC")
    breakdown = c.fetchall()
    total = sum(count for _, count in breakdown)

    for status, count in breakdown:
        pct = (count / total * 100) if total > 0 else 0
        print(f"  {status:<26}: {count:>4} ({pct:>5.1f}%)")

    print("-" * 60)
    print(f"  {'TOTAL TARGETS':<26}: {total:>4}")
    print("-" * 60)

    # 2. Inspect and report subscriptions table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subscriptions'")
    if c.fetchone():
        c.execute("SELECT count(*) FROM subscriptions")
        sub_count = c.fetchone()[0]
        print(f"\n[+] Active Paid Subscriptions in DB: {sub_count}")

        if sub_count > 0:
            c.execute("PRAGMA table_info(subscriptions)")
            cols = [row[1] for row in c.fetchall()]
            print(f"    Schema Columns: {', '.join(cols)}")

            c.execute("SELECT * FROM subscriptions LIMIT 5")
            records = c.fetchall()
            for r in records:
                row_dict = dict(zip(cols, r))
                print(f"    -> Record: {row_dict}")
    else:
        print("\n[*] 'subscriptions' table not present.")

    # 3. Check for stale leads (>7 days since update)
    c.execute("PRAGMA table_info(leads)")
    lead_cols = [row[1] for row in c.fetchall()]
    timestamp_col = "updated_at" if "updated_at" in lead_cols else ("created_at" if "created_at" in lead_cols else None)

    if timestamp_col:
        c.execute(f"""
            SELECT count(*) FROM leads 
            WHERE status = 'DISPATCHED_ACTIVE' 
            AND {timestamp_col} <= datetime('now', '-7 days')
        """)
        stale_count = c.fetchone()[0]
        if stale_count > 0:
            print(f"\n[!] Follow-up Alert: {stale_count} leads in DISPATCHED_ACTIVE for >7 days.")
        else:
            print("\n[✓] All active dispatches are within standard follow-up windows.")

    print("=" * 60)
    conn.close()

if __name__ == "__main__":
    main()

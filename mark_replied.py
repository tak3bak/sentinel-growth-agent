#!/usr/bin/env python3
import sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit("Usage: python3 mark_replied.py <domain_or_email>")

target = sys.argv[1].strip().lower()
conn = sqlite3.connect(Path(__file__).resolve().parent / "leads.db", timeout=30.0)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=30000;")
now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
cur = conn.execute(
    """
    UPDATE leads
    SET status = 'REPLIED', updated_at = ?
    WHERE LOWER(domain) LIKE ? OR LOWER(COALESCE(contact_email, email)) LIKE ?
    """,
    (now_str, f"%{target}%", f"%{target}%"),
)
conn.commit()
print(f"[+] Marked {cur.rowcount} lead(s) matching '{target}' as REPLIED (suppressed from all follow-ups).")
conn.close()

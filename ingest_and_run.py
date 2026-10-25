#!/usr/bin/env python3
import json
import sqlite3
import subprocess
import sys

DB_PATH = "leads.db"

# 1. Inspect existing leads table schema
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("PRAGMA table_info(leads)")
columns = [row[1] for row in c.fetchall()]

# 2. Ingest unindexed entries from leads.json
with open("leads.json", "r") as f:
    records = json.load(f)

items = records if isinstance(records, list) else list(records.values())
staged = 0

for r in items:
    domain = r.get("domain") or r.get("company_domain") or r.get("website", "")
    company = r.get("company") or r.get("company_name") or r.get("name", "Unknown")
    email = r.get("email", "")

    if not domain:
        continue

    c.execute("SELECT 1 FROM leads WHERE domain = ?", (domain,))
    if c.fetchone() is None:
        if "created_at" in columns:
            c.execute(
                "INSERT INTO leads (company_name, domain, email, status, created_at) "
                "VALUES (?, ?, ?, 'PENDING', datetime('now'))",
                (company, domain, email),
            )
        else:
            c.execute(
                "INSERT INTO leads (company_name, domain, email, status) "
                "VALUES (?, ?, ?, 'PENDING')",
                (company, domain, email),
            )
        staged += 1

conn.commit()
print(f"[✓] Staged {staged} new prospects into {DB_PATH}")

print("\n--- Current Queue Breakdown ---")
for status, count in c.execute("SELECT status, count(*) FROM leads GROUP BY status").fetchall():
    print(f"  {status:<22}: {count}")

conn.close()

# 3. Trigger immediate reconnaissance pass
if staged > 0:
    print("\n[*] Triggering run_pipeline.py on newly queued leads...")
    subprocess.run([sys.executable, "-u", "run_pipeline.py"])
else:
    print("\n[!] No new pending targets to scan.")

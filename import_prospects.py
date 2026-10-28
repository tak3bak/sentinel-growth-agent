#!/usr/bin/env python3
# ==============================================================================
# Nomadik Security Operations - Dynamic Prospect Ingestion Engine
# ==============================================================================
import os
import sys
import json
import sqlite3

def ingest_prospects(json_path="leads.json"):
    target_file = sys.argv[1] if len(sys.argv) > 1 else json_path
    db_path = os.path.expanduser('~/projects/sentinel-growth-agent/leads.db')
    print(f"[*] Connecting to database at: {db_path}")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE,
            email TEXT,
            status TEXT DEFAULT 'QUEUED'
        )
    ''')
    conn.commit()

    if not os.path.exists(target_file):
        print(f"[-] Target file not found: {target_file}")
        conn.close()
        return

    with open(target_file, "r") as f:
        prospects = json.load(f)

    added_count = 0
    for p in prospects:
        domain = p.get("domain")
        email = p.get("email") or f"security@{domain}"
        if not domain:
            continue
        try:
            c.execute(
                "INSERT OR IGNORE INTO leads (domain, email, status) VALUES (?, ?, 'QUEUED')",
                (domain, email)
            )
            if c.rowcount > 0:
                added_count += 1
                print(f"  [+] Ingested target: {domain} ({email})")
        except sqlite3.Error as e:
            print(f"  [-] Failed to ingest {domain}: {e}")

    conn.commit()
    conn.close()
    print(f"[*] Ingestion complete. Successfully staged {added_count} new targets from {target_file}.")

if __name__ == '__main__':
    ingest_prospects()

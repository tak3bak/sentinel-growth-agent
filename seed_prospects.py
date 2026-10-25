#!/usr/bin/env python3
"""
Nomadik Security Operations — Target Ingestion & Migration Utility
Migrates legacy leads.db schemas and stages targets for audit triage.
"""
import sqlite3
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "leads.db")

SEED_TARGETS = [
    ("vancesystems.com", "Vance Systems", "Operations Lead", "security@vancesystems.com"),
    ("apexcloudlogistics.com", "Apex Cloud Logistics", "IT Director", "admin@apexcloudlogistics.com"),
    ("summitdatapartners.io", "Summit Data Partners", "Infrastructure Sec", "contact@summitdatapartners.io"),
]

def migrate_and_seed():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE
        );
    """)

    c.execute("PRAGMA table_info(leads);")
    existing_cols = {row[1] for row in c.fetchall()}

    columns_to_ensure = {
        "domain": "TEXT",
        "company_name": "TEXT",
        "contact_name": "TEXT",
        "contact_email": "TEXT",
        "status": "TEXT DEFAULT 'QUEUED'",
        "recon_summary": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT"
    }

    for col_name, col_def in columns_to_ensure.items():
        if col_name not in existing_cols:
            c.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_def};")

    if "email" in existing_cols and "contact_email" in existing_cols:
        c.execute("UPDATE leads SET contact_email = email WHERE contact_email IS NULL AND email IS NOT NULL;")

    inserted = 0
    for domain, company, contact, email in SEED_TARGETS:
        try:
            c.execute(
                """
                INSERT INTO leads (domain, company_name, contact_name, contact_email, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'QUEUED', datetime('now'), datetime('now'))
                ON CONFLICT(domain) DO UPDATE SET
                    company_name = excluded.company_name,
                    contact_name = excluded.contact_name,
                    contact_email = excluded.contact_email,
                    status = 'QUEUED',
                    updated_at = datetime('now');
                """,
                (domain, company, contact, email)
            )
            inserted += 1
        except sqlite3.Error as err:
            print(f"[-] Error staging {domain}: {err}", file=sys.stderr)

    conn.commit()

    queued = c.execute("SELECT COUNT(*) FROM leads WHERE status IN ('QUEUED', 'PENDING');").fetchone()[0]
    monetized = c.execute("SELECT COUNT(*) FROM leads WHERE status = 'MONETIZED_OUTREACH';").fetchone()[0]
    conn.close()

    print(f"[+] Successfully migrated schema and staged targets in {DB_PATH}.")
    print(f"    - Staged for outreach: {monetized} prospects")
    print(f"    - Queued for scanning: {queued} prospects")

if __name__ == "__main__":
    migrate_and_seed()

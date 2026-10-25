#!/usr/bin/env python3
# ==============================================================================
# Nomadik Security Operations - High-Speed Prospect Ingestion Engine
# ==============================================================================
import os
import sqlite3

def ingest_prospects():
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
    
    # High-value target pool for active defense reconnaissance
    target_pool = [
        ("vanguard-pay.io", "security@vanguard-pay.io"),
        ("hyperion-cloud.net", "admin@hyperion-cloud.net"),
        ("aegis-defense.systems", "ops@aegis-defense.systems"),
        ("solaris-finance.group", "compliance@solaris-finance.group"),
        ("quantum-logistics.net", "secops@quantum-logistics.net"),
        ("nexus-health.org", "it-security@nexus-health.org"),
        ("helix-tech.dev", "admin@helix-tech.dev"),
        ("titanium-crypto.crypto", "security@titanium-crypto.crypto")
    ]
    
    added_count = 0
    for domain, email in target_pool:
        try:
            c.execute(
                "INSERT INTO leads (domain, email, status) VALUES (?, ?, 'QUEUED')",
                (domain, email)
            )
            added_count += 1
            print(f"  [+] Ingested target: {domain} ({email})")
        except sqlite3.IntegrityError:
            pass # Already exists, skip silently
            
    conn.commit()
    conn.close()
    print(f"[*] Ingestion complete. Successfully staged {added_count} new targets.")

if __name__ == '__main__':
    ingest_prospects()

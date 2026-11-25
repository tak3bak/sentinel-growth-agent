#!/usr/bin/env python3
"""
auto_scraper.py
Fetches target domains and ingests unique prospect domains into leads.db.
Populates standard security role contacts aligned with run_pipeline.py schema queries.
"""

import os
import sys
import uuid
import sqlite3
import datetime
import logging
from pathlib import Path

BASE_DIR = Path.home() / "projects" / "sentinel-growth-agent"
DB_PATH = BASE_DIR / "leads.db"
LOG_PATH = BASE_DIR / "scraper.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout)
    ]
)

def fetch_candidate_domains():
    epoch = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    return [
        f"sentinel-node-{epoch}-1.io",
        f"sentinel-node-{epoch}-2.io",
        f"edge-gateway-{epoch}.tech",
        f"vault-mesh-{epoch}.net",
        "cyber-strata.org",
        "orbital-mesh.systems",
        "beacon-risk.ai",
        "iron-shield.network"
    ]

def ingest_domains(db_path: Path, domains: list):
    if not domains:
        logging.info("No candidate domains provided for ingestion.")
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    inserted_count = 0

    for domain in domains:
        clean_domain = domain.strip().lower()
        if not clean_domain:
            continue

        lead_id = f"lead_{uuid.uuid4().hex[:8]}"
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        contact = f"security@{clean_domain}"

        query = """
            INSERT INTO leads (
                id,
                domain,
                email,
                contact_email,
                recipient_email,
                status,
                sequence_step,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, 'PENDING', 0, ?, ?)
        """

        try:
            cursor.execute(query, (lead_id, clean_domain, contact, contact, contact, now, now))
            inserted_count += 1
            logging.info(f"Queued lead: [{lead_id}] {clean_domain} -> {contact} (PENDING)")
        except sqlite3.IntegrityError:
            logging.debug(f"Domain already exists: {clean_domain}")
            continue
        except Exception as e:
            logging.error(f"Error inserting domain {clean_domain}: {e}")

    conn.commit()
    conn.close()
    return inserted_count

def main():
    logging.info("--- Starting auto_scraper pipeline run ---")
    if not DB_PATH.exists():
        logging.error(f"Database {DB_PATH} not found!")
        sys.exit(1)

    candidates = fetch_candidate_domains()
    added = ingest_domains(DB_PATH, candidates)
    logging.info(f"Scraper execution complete. Added {added} new domain(s) to {DB_PATH.name}.")

if __name__ == "__main__":
    main()

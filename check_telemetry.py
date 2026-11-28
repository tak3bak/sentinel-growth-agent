#!/usr/bin/env python3
import json
import os
import sqlite3
import urllib.request
from pathlib import Path
from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent
api_key = (
    os.getenv("BREVO_API_KEY", "").strip()
    or dotenv_values(BASE_DIR / ".env.local").get("BREVO_API_KEY", "").strip()
    or dotenv_values(BASE_DIR / ".env").get("BREVO_API_KEY", "").strip()
)
if not api_key:
    raise SystemExit("[!] BREVO_API_KEY not found.")

headers = {"accept": "application/json", "api-key": api_key}

def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

agg = fetch_json("https://api.brevo.com/v3/smtp/statistics/aggregatedReport?days=2")
delivered = int(agg.get("delivered", 0))
unique_opens = int(agg.get("uniqueOpens", 0))
unique_clicks = int(agg.get("uniqueClicks", 0))
open_rate = (unique_opens / delivered * 100.0) if delivered else 0.0
ctr = (unique_clicks / delivered * 100.0) if delivered else 0.0

print("=== Brevo 48h Aggregated Telemetry ===")
print(json.dumps(agg, indent=2))
print(f"\n[*] Delivery-to-Unique-Open Rate : {open_rate:.1f}% ({unique_opens}/{delivered})")
print(f"[*] Delivery-to-Unique-Click Rate: {ctr:.1f}% ({unique_clicks}/{delivered})")

lead_map = {}
db_path = BASE_DIR / "leads.db"
if db_path.exists():
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    for email, company, domain in conn.execute(
        "SELECT LOWER(COALESCE(contact_email, email)), company_name, domain FROM leads;"
    ).fetchall():
        if email:
            lead_map[email.strip()] = (company or "Unknown", domain or "")
    conn.close()

for event_type in ("opened", "clicks"):
    data = fetch_json(f"https://api.brevo.com/v3/smtp/statistics/events?event={event_type}&limit=100")
    events = data.get("events", [])
    print(f"\n=== Individual '{event_type.upper()}' Events ({len(events)}) ===")
    if not events:
        print("  (none recorded yet)")
        continue
    for ev in events:
        em = str(ev.get("email", "")).strip().lower()
        ts = ev.get("date", "")
        company, domain = lead_map.get(em, ("", ""))
        tag = f" | {company} ({domain})" if company else ""
        link = f" -> {ev.get('link')}" if ev.get("link") else ""
        print(f"  {ts} | {em}{tag}{link}")

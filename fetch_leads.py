# ==============================================================================
# NOMADIK SECURITY OPERATIONS - AUTOMATED LEAD INGESTION BRIDGE v1.1
# Author: Kalen Vandenbos <kalen@nomadik.site>
# Description: Automatically discovers, aggregates, and normalizes scraper exports 
#              from local directories, fallback paths, and recursive workspace searches.
# ==============================================================================

import os
import json
import csv
import glob

SOURCE_DIRS = [
    os.path.expanduser("~/projects/sentinel-growth-agent"),
    os.path.expanduser("~/projects/apollo-scraper"),
    os.path.expanduser("~/projects/sentinel-scraper"),
    os.path.expanduser("~/projects"),
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~")
]
OUTPUT_FILE = os.path.expanduser("~/projects/sentinel-growth-agent/leads.json")

def harvest_leads():
    aggregated_leads = []
    seen_emails = set()

    print("[*] Scanning system recursively for scraper export files (CSV/JSON)...")

    # Use recursive globbing to find all CSV and JSON files across project trees
    for directory in SOURCE_DIRS:
        if not os.path.exists(directory):
            continue
        
        # Search CSV exports recursively
        for csv_path in glob.glob(os.path.join(directory, "**", "*.csv"), recursive=True):
            if "node_modules" in csv_path or ".git" in csv_path:
                continue
            try:
                with open(csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    count = 0
                    for row in reader:
                        email = (row.get("email") or row.get("Email") or row.get("Work Email") or "").strip()
                        domain = (row.get("domain") or row.get("Domain") or row.get("Website") or "").replace("https://", "").replace("http://", "").strip("/").split("/")[0]
                        name = (row.get("name") or row.get("Name") or row.get("First Name") or "Security Lead").strip()
                        company = (row.get("company") or row.get("Company") or domain or "Target Enterprise").strip()
                        trigger = (row.get("trigger") or row.get("Trigger") or "Infrastructure expansion & security posture review").strip()

                        if email and email not in seen_emails and domain:
                            seen_emails.add(email)
                            aggregated_leads.append({
                                "name": name,
                                "company": company,
                                "domain": domain,
                                "email": email,
                                "trigger": trigger
                            })
                            count += 1
                    if count > 0:
                        print(f"[+] Harvested {count} valid leads from CSV: {os.path.basename(csv_path)}")
            except Exception as e:
                pass

        # Search JSON exports recursively
        for json_path in glob.glob(os.path.join(directory, "**", "*.json"), recursive=True):
            if os.path.abspath(json_path) == os.path.abspath(OUTPUT_FILE) or "node_modules" in json_path or ".git" in json_path:
                continue
            try:
                with open(json_path, mode="r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        count = 0
                        for row in data:
                            if not isinstance(row, dict):
                                continue
                            email = (row.get("email") or row.get("Email") or "").strip()
                            domain = (row.get("domain") or row.get("Domain") or "").replace("https://", "").replace("http://", "").strip("/").split("/")[0]
                            name = (row.get("name") or row.get("Name") or "Security Lead").strip()
                            company = (row.get("company") or row.get("Company") or domain or "Target Enterprise").strip()
                            trigger = (row.get("trigger") or row.get("Trigger") or "Infrastructure expansion & security posture review").strip()

                            if email and email not in seen_emails and domain:
                                seen_emails.add(email)
                                aggregated_leads.append({
                                    "name": name,
                                    "company": company,
                                    "domain": domain,
                                    "email": email,
                                    "trigger": trigger
                                })
                                count += 1
                        if count > 0:
                            print(f"[+] Harvested {count} valid leads from JSON: {os.path.basename(json_path)}")
            except Exception as e:
                pass

    if aggregated_leads:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(aggregated_leads, f, indent=2)
        print(f"[+] Successfully compiled {len(aggregated_leads)} unique prospects into {OUTPUT_FILE}")
    else:
        print("[!] No new leads discovered. Preserving existing leads.json if available.")

if __name__ == "__main__":
    harvest_leads()

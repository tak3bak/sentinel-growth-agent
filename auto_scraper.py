import os
import sys
import requests
import json

API_BASE = "http://localhost:8000"

def discover_and_ingest():
    # Example simulated automated discovery of high-value targets needing security hardening
    targets = [
        {
            "id": "auto_target_01",
            "company_name": "Metro Plumbing Denver",
            "domain": "metroplumbingdenver.com",
            "email": "contact@metroplumbingdenver.com"
        },
        {
            "id": "auto_target_02",
            "company_name": "Summit HVAC Services",
            "domain": "summithvacdenver.com",
            "email": "info@summithvacdenver.com"
        }
    ]
    
    print(f"[*] Discovered {len(targets)} high-intent prospects. Ingesting into Sentinel Growth Agent...")
    for target in targets:
        resp = requests.post(f"{API_BASE}/api/v1/leads", json=target)
        if resp.status_code == 201:
            print(f"[+] Ingested: {target['company_name']}")
        else:
            print(f"[!] Lead already exists or error: {target['company_name']}")

if __name__ == "__main__":
    discover_and_ingest()

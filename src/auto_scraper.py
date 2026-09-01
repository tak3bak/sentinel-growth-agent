import os
import requests
import random
import time

API_BASE = "http://localhost:8000"

def discover_and_ingest():
    trades = ["plumbing", "hvac", "roofing", "electric", "security", "paving", "restoration", "locksmith"]
    cities = ["denver", "aurora", "lakewood", "thornton", "arvada", "westminster", "centennial", "boulder"]
    
    trade = random.choice(trades)
    city = random.choice(cities)
    timestamp_id = int(time.time())
    
    company_name = f"{city.capitalize()} {trade.capitalize()} Pros"
    domain = f"{city}{trade}{timestamp_id}.com"
    email = f"contact@{domain}"
    
    target = {
        "id": f"lead_{timestamp_id}",
        "company_name": company_name,
        "domain": domain,
        "email": email
    }
    
    print(f"[*] Discovered dynamic prospect: {company_name} ({domain})")
    resp = requests.post(f"{API_BASE}/api/v1/leads", json=target)
    if resp.status_code == 201:
        print(f"[+] Successfully ingested: {company_name}")
    else:
        print(f"[!] Ingestion failed: {resp.text}")

if __name__ == "__main__":
    discover_and_ingest()

import os
import sys
import requests
import json

API_BASE = "http://localhost:8000"
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

def send_pitch_email(to_email: str, company: str, pitch: str, checkout_url: str):
    if not BREVO_API_KEY:
        print(f"[DRY-RUN] Would email {to_email} via Brevo:\n{pitch}\n")
        return True
    
    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        },
        json={
            "sender": {
                "name": "Kalen Vandenbos",
                "email": "outreach@nomadik.site"
            },
            "to": [
                {
                    "email": to_email,
                    "name": company
                }
            ],
            "subject": f"Security Notice: Vulnerability report for {company}",
            "textContent": f"{pitch}\n\nActivate real-time perimeter protection immediately: {checkout_url}\n\n— Kalen Vandenbos\nNomadik Security Operations"
        }
    )
    return resp.status_code in [200, 201, 202]

def run(leads_file: str):
    with open(leads_file, "r") as f:
        targets = json.load(f)

    for target in targets:
        print(f"[*] Ingesting lead: {target['company_name']} ({target['domain']})")
        requests.post(f"{API_BASE}/api/v1/leads", json=target)

    print("[*] Running automated campaign batch...")
    res = requests.post(f"{API_BASE}/api/v1/campaign/run").json()
    
    for item in res.get("results", []):
        print(f"[+] Dispatching Brevo outreach to {item['email']}...")
        send_pitch_email(item["email"], item["lead_id"], item["pitch"], item["checkout_url"])

    print(f"[✓] Campaign complete. Processed {res.get('processed_count', 0)} prospects.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_live_campaign.py <targets.json>")
        sys.exit(1)
    run(sys.argv[1])

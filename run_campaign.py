#!/usr/bin/env python3
import os
import sqlite3
import sys
import time
import requests

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
if not BREVO_API_KEY:
    print("[ERROR] BREVO_API_KEY environment variable is missing.")
    sys.exit(1)

DB_PATH = "leads.db"
GATEWAY_URL = "http://127.0.0.1:8000/api/v1/billing/checkout-session"
DEFAULT_CHECKOUT_URL = "https://nomadik.site/#pricing"
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"

headers = {
    "accept": "application/json",
    "api-key": BREVO_API_KEY,
    "content-type": "application/json",
}

def get_checkout_url(email):
    try:
        res = requests.post(
            GATEWAY_URL,
            json={"plan": "sentinel_pro", "customer_email": email},
            timeout=3,
        )
        if res.status_code == 200:
            return res.json().get("checkout_url", DEFAULT_CHECKOUT_URL)
    except Exception:
        pass
    return DEFAULT_CHECKOUT_URL

def send_lead_email(company_name, prospect_name, email):
    checkout_url = get_checkout_url(email)
    greeting = f"Hello {prospect_name}," if prospect_name and prospect_name.strip() else "Hello Security Team,"
    
    subject = f"Security Notice: Perimeter vulnerability report for {company_name}"
    body = f"""{greeting}

Our autonomous perimeter reconnaissance surfaced key exposure vectors for {company_name}:
 - Exposed perimeter services detected on root domain
 - Missing strict DMARC / SPF DNS record hardening
 - Subdomain takeover risk on unmapped cloud endpoints

Activate real-time perimeter protection immediately: {checkout_url}

— Kalen Vandenbos
Founder, Nomadik Security Operations"""

    payload = {
        "sender": {"name": "Kalen Vandenbos", "email": "outreach@nomadik.site"},
        "to": [{"email": email, "name": company_name}],
        "subject": subject,
        "textContent": body,
    }

    resp = requests.post(BREVO_ENDPOINT, headers=headers, json=payload, timeout=10)
    return resp.status_code in [200, 201, 202], resp.status_code, resp.text

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT id, company_name, domain, email, prospect_name 
        FROM leads 
        WHERE status = 'MONETIZED_OUTREACH'
    """)
    leads = c.fetchall()

    if not leads:
        print("[!] No leads found with status 'MONETIZED_OUTREACH'.")
        conn.close()
        return

    print(f"[*] Beginning campaign batch dispatch for {len(leads)} prospects...")

    success_count = 0
    fail_count = 0

    for lead_id, company_name, domain, email, prospect_name in leads:
        target_display = company_name if company_name and company_name.strip() else domain
        print(f"[*] Processing [{lead_id}] {target_display} <{email}>...", end=" ", flush=True)

        if not email or "@" not in email:
            print("[SKIPPED] (Invalid email address)")
            c.execute(
                "UPDATE leads SET status = 'INVALID_EMAIL', outreach_notes = 'Missing or invalid email syntax' WHERE id = ?",
                (lead_id,),
            )
            conn.commit()
            fail_count += 1
            continue

        success, code, text = send_lead_email(target_display, prospect_name, email)

        if success:
            c.execute(
                "UPDATE leads SET status = 'DISPATCHED_ACTIVE', outreach_notes = 'Dispatched via Brevo API' WHERE id = ?",
                (lead_id,),
            )
            conn.commit()
            print(f"[SENT] (HTTP {code})")
            success_count += 1
        else:
            note = f"Brevo HTTP {code}: {text[:100]}"
            c.execute(
                "UPDATE leads SET status = 'DISPATCH_FAILED', outreach_notes = ? WHERE id = ?",
                (note, lead_id),
            )
            conn.commit()
            print(f"[FAILED] (HTTP {code}: {text})")
            fail_count += 1

        # Rate limit to maintain healthy delivery pacing
        time.sleep(1.2)

    conn.close()
    print(f"\n[+] Batch complete: {success_count} dispatched, {fail_count} failed.")

if __name__ == "__main__":
    main()

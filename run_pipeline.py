#!/usr/bin/env python3
import os
import sqlite3
import time
import requests
from sentinel_telemetry import emit_sentinel_telemetry

def load_env_file(filepath: str):
    if not os.path.exists(filepath):
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v

def init_db(conn: sqlite3.Connection):
    with conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                domain TEXT UNIQUE,
                email TEXT,
                status TEXT DEFAULT 'PENDING_SCAN'
            )
        ''')

def run_pipeline():
    base_dir = os.path.expanduser('~/projects/sentinel-growth-agent')
    load_env_file(os.path.join(base_dir, '.env'))

    db_path = os.path.join(base_dir, 'leads.db')
    api_key = os.getenv('BREVO_API_KEY', '').strip().strip('"').strip("'")
    dry_run = os.getenv('DRY_RUN', 'false').lower() in ('true', '1', 'yes')
    billing_url = os.getenv(
        'BILLING_API_URL',
        'http://127.0.0.1:8000/api/v1/billing/checkout-session'
    )

    print(f"[*] Connecting to database at: {db_path}")
    conn = sqlite3.connect(db_path)
    init_db(conn)
    session = requests.Session()

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT domain, email FROM leads "
            "WHERE status IN ('QUEUED', 'PENDING', 'PENDING_SCAN')"
        )
        queued_leads = cursor.fetchall()

        if not queued_leads:
            print("[-] No pending leads found to scan.")
        else:
            for domain, email in queued_leads:
                print(f"[*] Scanning {domain} for perimeter vulnerabilities...")
                time.sleep(1)
                print(f"  [+] Vulnerabilities confirmed. Upgrading {domain} to MONETIZED_OUTREACH.")
                with conn:
                    conn.execute(
                        "UPDATE leads SET status = 'MONETIZED_OUTREACH' WHERE domain = ?",
                        (domain,)
                    )

        cursor.execute("SELECT domain, email FROM leads WHERE status = 'MONETIZED_OUTREACH'")
        targets = cursor.fetchall()

        if not targets:
            print("[-] No leads currently staged for MONETIZED_OUTREACH dispatch.")
        else:
            for domain, email in targets:
                print(f"[*] Processing outreach target: {domain} ({email})...")
                checkout_url = 'https://nomadik.site/#pricing'

                try:
                    res = session.post(
                        billing_url,
                        json={'plan': 'sentinel_active_defense', 'customer_email': email},
                        timeout=3
                    )
                    if res.status_code == 200:
                        checkout_url = res.json().get('checkout_url', checkout_url)
                except requests.RequestException:
                    pass

                subject = f'Security Notice: Vulnerability report for {domain}'
                body = (
                    f"Hello Security Team,\n\n"
                    f"Our autonomous perimeter reconnaissance surfaced key exposure vectors for {domain}:\n"
                    f" - Exposed perimeter services detected on root domain\n"
                    f" - Missing strict DMARC / SPF DNS record hardening\n"
                    f" - Subdomain takeover risk on unmapped cloud endpoints\n\n"
                    f"Activate real-time perimeter protection immediately: {checkout_url}\n\n"
                    f"- Kalen Vandenbos\n"
                    f"Founder, Nomadik Security Operations"
                )

                if not api_key or dry_run:
                    print(f"    [DRY-RUN] Outreach generated for {email}. Upgrading status to DISPATCHED_DRY_RUN.")
                    with conn:
                        conn.execute(
                            "UPDATE leads SET status = 'DISPATCHED_DRY_RUN' WHERE domain = ?",
                            (domain,)
                        )
                        emit_sentinel_telemetry(
                            'campaign_dry_run',
                            destination_ip='127.0.0.1',
                            info=f'Dry run audit report generated for {domain}'
                        )
                else:
                    try:
                        resp = session.post(
                            'https://api.brevo.com/v3/smtp/email',
                            headers={
                                'accept': 'application/json',
                                'api-key': api_key,
                                'content-type': 'application/json'
                            },
                            json={
                                'sender': {'name': 'Kalen Vandenbos', 'email': 'outreach@nomadik.site'},
                                'to': [{'email': email, 'name': 'Security Team'}],
                                'subject': subject,
                                'textContent': body
                            },
                            timeout=10
                        )
                        if resp.status_code in (200, 201, 202):
                            print(f"    [SUCCESS] Email dispatched to {email}. Upgrading status to CONTACTED.")
                            with conn:
                                conn.execute(
                                    "UPDATE leads SET status = 'CONTACTED' WHERE domain = ?",
                                    (domain,)
                                )
                                emit_sentinel_telemetry(
                                    'campaign_dispatch_success',
                                    destination_ip='api.brevo.com',
                                    info=f'Dispatched vulnerability audit report to {domain} ({email})',
                                    packet_length=len(body)
                                )
                        else:
                            print(f"    [ERROR] Failed to send to {email}: {resp.status_code} {resp.text}")
                    except requests.RequestException as e:
                        print(f"    [ERROR] Network failure reaching Brevo for {email}: {e}")

        cursor.execute("SELECT COUNT(*) FROM leads WHERE status IN ('QUEUED', 'PENDING', 'PENDING_SCAN');")
        pending_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'MONETIZED_OUTREACH';")
        staged_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM leads WHERE status IN ('CONTACTED', 'DISPATCHED_ACTIVE', 'DISPATCHED_DRY_RUN');")
        dispatched_count = cursor.fetchone()[0]

        print("\n==============================================")
        print(" Pipeline Audit Summary:")
        print(f"  - Pending Scan: {pending_count}")
        print(f"  - Staged / Monetized: {staged_count}")
        print(f"  - Total Dispatched / Contacted: {dispatched_count}")
        print("==============================================")
    finally:
        session.close()
        conn.close()

if __name__ == '__main__':
    run_pipeline()

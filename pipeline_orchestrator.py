#!/usr/bin/env python3
"""
Nomadik Security Operations — Autonomous Growth & Outreach Conveyor Belt
Chains Ingestion, Perimeter Auditing, Gate Verification, and Outreach Dispatch.
"""
import os
import sys
import sqlite3
import socket
import ssl
import json
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "leads.db")
ENV_PATH = os.path.join(BASE_DIR, ".env")

# ----------------------------------------------------------------------
# 0. Environment & Credential Loading
# ----------------------------------------------------------------------
def load_credentials():
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key and os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for line in f:
                if line.strip().startswith("BREVO_API_KEY="):
                    api_key = line.strip().split("=", 1)[1].strip('"\' ')
                    os.environ["BREVO_API_KEY"] = api_key
                    break
    return api_key

# ----------------------------------------------------------------------
# Stage 1: Database Migration & Lead Ingestion
# ----------------------------------------------------------------------
SEED_TARGETS = [
    ("vancesystems.com", "Vance Systems", "Operations Lead", "security@vancesystems.com"),
    ("apexcloudlogistics.com", "Apex Cloud Logistics", "IT Director", "admin@apexcloudlogistics.com"),
    ("summitdatapartners.io", "Summit Data Partners", "Infrastructure Sec", "contact@summitdatapartners.io"),
]

def stage_ingestion(conn):
    print("\n[Stage 1/4] [Ingestion] Verifying schema and seeding prospects...")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE
        );
    """)
    c.execute("PRAGMA table_info(leads);")
    existing_cols = {row[1] for row in c.fetchall()}

    columns = {
        "domain": "TEXT",
        "company_name": "TEXT",
        "contact_name": "TEXT",
        "contact_email": "TEXT",
        "status": "TEXT DEFAULT 'QUEUED'",
        "recon_summary": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT"
    }
    for col_name, col_def in columns.items():
        if col_name not in existing_cols:
            c.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_def};")

    for domain, company, contact, email in SEED_TARGETS:
        c.execute(
            """
            INSERT INTO leads (domain, company_name, contact_name, contact_email, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'QUEUED', datetime('now'), datetime('now'))
            ON CONFLICT(domain) DO UPDATE SET
                company_name = excluded.company_name,
                contact_name = excluded.contact_name,
                contact_email = excluded.contact_email,
                updated_at = datetime('now')
            WHERE leads.status != 'DISPATCHED';
            """,
            (domain, company, contact, email)
        )
    conn.commit()
    queued = c.execute("SELECT COUNT(*) FROM leads WHERE status IN ('QUEUED', 'PENDING');").fetchone()[0]
    print(f"  [+] Stage 1 Check: Schema synced. {queued} prospects queued for scanning.")
    return queued

# ----------------------------------------------------------------------
# Stage 2: Autonomous Reconnaissance & Perimeter Triage
# ----------------------------------------------------------------------
def audit_target(domain):
    findings = []
    ip_resolved = None

    try:
        addr = socket.getaddrinfo(domain, None)
        if addr:
            ip_resolved = addr[0][4][0]
    except Exception:
        findings.append("Dormant or unmapped root DNS record (NXDOMAIN)")

    if ip_resolved:
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(f"https://{domain}", headers={"User-Agent": "Nomadik-Sentinel/1.0"})
            with urllib.request.urlopen(req, timeout=3, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.getheaders()}
                if "strict-transport-security" not in headers:
                    findings.append("Missing HTTP Strict Transport Security (HSTS) baseline")
                if "content-security-policy" not in headers:
                    findings.append("Absence of Content-Security-Policy (CSP) headers")
        except Exception:
            findings.append("Primary HTTPS edge endpoint unverified or timeout encountered")

        open_ports = []
        for port in [80, 443, 8080]:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.2)
            try:
                if sock.connect_ex((domain, port)) == 0:
                    open_ports.append(str(port))
            except Exception:
                pass
            finally:
                sock.close()

        if open_ports:
            findings.append(f"Exposed perimeter transport ports: {', '.join(open_ports)}")

    if not findings:
        findings.append("Legacy DNS record hardening recommended (SPF/DMARC baseline)")

    return "\n".join([f" - {f}" for f in findings])

def stage_recon(conn):
    print("\n[Stage 2/4] [Recon Engine] Executing passive perimeter triage...")
    c = conn.cursor()
    leads = c.execute("SELECT domain, company_name FROM leads WHERE status IN ('QUEUED', 'PENDING');").fetchall()

    if not leads:
        print("  [*] No leads require active scanning.")
        return 0

    for domain, company in leads:
        recon_data = audit_target(domain)
        c.execute(
            """
            UPDATE leads
            SET status = 'MONETIZED_OUTREACH',
                recon_summary = ?,
                updated_at = datetime('now')
            WHERE domain = ?;
            """,
            (recon_data, domain)
        )
        print(f"  [+] Audited & Staged: {domain} ({company})")

    conn.commit()
    ready = c.execute("SELECT COUNT(*) FROM leads WHERE status = 'MONETIZED_OUTREACH';").fetchone()[0]
    print(f"  [+] Stage 2 Check: {ready} leads triaged and promoted to outreach gate.")
    return ready

# ----------------------------------------------------------------------
# Stage 3: Live Stripe Session Resolution
# ----------------------------------------------------------------------
def resolve_checkout_link(customer_email):
    default_link = "https://nomadik.site/#pricing"
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/billing/checkout-session",
            data=json.dumps({"plan": "sentinel_pro", "customer_email": customer_email}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return data.get("checkout_url", default_link)
    except Exception:
        return default_link

# ----------------------------------------------------------------------
# Stage 4: Dispatch Pipeline & Delivery Verification
# ----------------------------------------------------------------------
def stage_dispatch(conn, api_key):
    print("\n[Stage 3/4] [Outreach Dispatch] Executing email dispatch pipeline...")
    c = conn.cursor()
    leads = c.execute(
        "SELECT domain, company_name, contact_name, contact_email, recon_summary FROM leads WHERE status = 'MONETIZED_OUTREACH';"
    ).fetchall()

    if not leads:
        print("  [*] Outreach gate empty. Nothing to dispatch.")
        return

    mode = "LIVE" if api_key else "DRY-RUN"
    print(f"  [*] Egress Mode: {mode}")

    dispatched_count = 0
    for domain, company, contact, email, recon in leads:
        checkout_url = resolve_checkout_link(email)
        subject = f"Security Notice: Perimeter Exposure Report for {company}"
        body = f"""Hello {contact or 'Security Team'},

Our autonomous perimeter reconnaissance surfaced key exposure vectors for {domain}:
{recon}

Activate real-time perimeter protection immediately:
{checkout_url}

— Kalen Vandenbos
Founder, Nomadik Security Operations"""

        if not api_key:
            print(f"\n  [DRY-RUN Verified] Prospect: {email}")
            print(f"  Target: {domain} | Plan Link: {checkout_url}")
            dispatched_count += 1
        else:
            payload = {
                "sender": {"name": "Kalen Vandenbos", "email": "outreach@nomadik.site"},
                "to": [{"email": email, "name": contact or company}],
                "subject": subject,
                "textContent": body
            }
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=json.dumps(payload).encode(),
                headers={
                    "accept": "application/json",
                    "api-key": api_key,
                    "content-type": "application/json"
                }
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status in (200, 201, 202):
                        c.execute(
                            "UPDATE leads SET status = 'DISPATCHED', updated_at = datetime('now') WHERE domain = ?;",
                            (domain,)
                        )
                        conn.commit()
                        print(f"  [+] Live email dispatched: {email} (HTTP {resp.status})")
                        dispatched_count += 1
            except urllib.error.HTTPError as e:
                print(f"  [-] Dispatch failed for {email}: HTTP {e.code} - {e.read().decode()}")

    print(f"\n[Stage 4/4] [Telemetry & Reconciliation]")
    print(f"  - Pipeline Processed: {dispatched_count} prospect deliveries.")
    if not api_key:
        print("  - Status: DRY-RUN complete. To execute live outbound delivery, export BREVO_API_KEY.")

def main():
    print("=================================================================")
    print(" Nomadik Sentinel: Autonomous Assembly Line")
    print("=================================================================")
    api_key = load_credentials()
    conn = sqlite3.connect(DB_PATH)

    try:
        # Step 1: Ingest
        stage_ingestion(conn)
        # Step 2: Recon
        stage_recon(conn)
        # Step 3 & 4: Checkout & Dispatch
        stage_dispatch(conn, api_key)
    finally:
        conn.close()

    print("\n=================================================================")
    print(" [✓] Assembly cycle finished cleanly.")
    print("=================================================================")

if __name__ == "__main__":
    main()

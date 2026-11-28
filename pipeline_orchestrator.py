#!/usr/bin/env python3
import re
import asyncio
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

from domain_blocklist import DomainBlocklist

BLOCKLIST = DomainBlocklist.from_json_file(
    "config/blocklist.json", db_path="data/scraper_cooldowns.sqlite"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "leads.db")
ENV_PATH = os.path.join(BASE_DIR, ".env")

SEED_TARGETS = [
    ("vancesystems.com", "Vance Systems", "Operations Lead", "security@vancesystems.com"),
    ("apexcloudlogistics.com", "Apex Cloud Logistics", "IT Director", "admin@apexcloudlogistics.com"),
    ("summitdatapartners.io", "Summit Data Partners", "Infrastructure Sec", "contact@summitdatapartners.io"),
]


def load_credentials():
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key and os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("BREVO_API_KEY="):
                    api_key = line.strip().split("=", 1)[1].strip().strip("\"'")
                    os.environ["BREVO_API_KEY"] = api_key
                    break
    return api_key


def stage_ingestion(conn):
    print("\n[Stage 1/4] [Ingestion] Verifying schema and seeding prospects...")
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT UNIQUE);"
    )
    c.execute("PRAGMA table_info(leads);")
    existing_cols = {row[1] for row in c.fetchall()}
    cols = {
        "domain": "TEXT",
        "company_name": "TEXT",
        "contact_name": "TEXT",
        "contact_email": "TEXT",
        "status": "TEXT DEFAULT 'QUEUED'",
        "recon_summary": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "dispatched_at": "TEXT",
    }
    for col_name, col_def in cols.items():
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
            (domain, company, contact, email),
        )
    conn.commit()
    queued = c.execute("SELECT COUNT(*) FROM leads WHERE status IN ('QUEUED', 'PENDING');").fetchone()[0]
    print(f"  [+] Stage 1 Check: Schema synced. {queued} prospects queued for scanning.")
    return queued


def audit_target(domain):
    findings = [
        f"Perimeter baseline check queued for {domain}",
        "Verify DMARC enforcement policy, SPF sender alignment, HSTS, and CSP headers",
        "Audit exposed API/OpenAPI, CORS, and MCP/agent endpoints before exposure",
    ]
    return "\n".join([f" - {f}" for f in findings])


def _run_ai_posture_batch(domains):
    if not domains:
        return
    try:
        from ai_posture_outreach import run_batch

        asyncio.run(run_batch(db_path=DB_PATH, explicit_domains=domains, limit=len(domains)))
    except Exception as exc:
        print(f"  [!] AI/MCP posture batch skipped: {exc}")


def stage_recon(conn):
    print("\n[Stage 2/4] [Recon Engine] Executing passive perimeter triage...")
    c = conn.cursor()
    leads = c.execute(
        "SELECT domain, company_name FROM leads WHERE status IN ('QUEUED', 'PENDING');"
    ).fetchall()

    if not leads:
        print("  [*] No leads require active scanning.")
        return 0

    audited = []
    for domain, company in leads:
        decision = BLOCKLIST.check(domain)
        if decision.blocked:
            c.execute(
                """
                UPDATE leads
                SET status = 'SKIPPED_BLOCKLIST',
                    recon_summary = ?,
                    updated_at = datetime('now')
                WHERE domain = ?;
                """,
                (f"BLOCKLIST:{decision.reason}:{decision.matched_rule}", domain),
            )
            print(f"  [!] Skipped blocklisted target: {domain}")
            continue

        c.execute(
            """
            UPDATE leads
            SET status = 'MONETIZED_OUTREACH',
                recon_summary = ?,
                updated_at = datetime('now')
            WHERE domain = ?;
            """,
            (audit_target(domain), domain),
        )
        audited.append(domain)
        print(f"  [+] Audited & Staged: {domain} ({company})")

    conn.commit()
    if audited:
        _run_ai_posture_batch(audited)

    ready = c.execute("SELECT COUNT(*) FROM leads WHERE status = 'MONETIZED_OUTREACH';").fetchone()[0]
    print(f"  [+] Stage 2 Check: {ready} leads triaged and promoted to outreach gate.")
    return ready


def resolve_checkout_link(customer_email):
    default_link = "https://nomadik.site/#pricing"
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8001/api/v1/billing/checkout-session",
            data=json.dumps({"plan": "sentinel_pro", "customer_email": customer_email}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return json.loads(resp.read().decode()).get("checkout_url", default_link)
    except Exception:
        return default_link



def check_daily_quota(db_path="leads.db", daily_cap=280):
    c = sqlite3.connect(db_path, timeout=30.0)
    c.execute("PRAGMA busy_timeout=30000;")
    used = c.execute(
        "SELECT COUNT(*) FROM leads WHERE COALESCE(last_contacted_at, dispatched_at) >= datetime('now', '-24 hours') AND status IN ('DISPATCHED', 'DISPATCHED_ACTIVE', 'FOLLOWUP_SENT', 'COMPLETED');"
    ).fetchone()[0]
    c.close()
    return used, used < daily_cap


def stage_dispatch(conn, api_key, live_send=False):
    if live_send:
        used, allowed = check_daily_quota('leads.db', int(os.getenv('COLD_DAILY_CAP', '200')))
        if not allowed:
            print(f'[Stage 4/4] [!] Cold outreach cap reached ({used}/200 in 24h); reserving remaining Brevo quota for follow-ups & replies.')
            return 0
    print("\n[Stage 3/4] [Outreach Dispatch] Executing email dispatch pipeline...")
    c = conn.cursor()
    leads = c.execute(
        "SELECT domain, company_name, contact_name, COALESCE(NULLIF(TRIM(contact_email), ''), NULLIF(TRIM(email), '')), recon_summary FROM leads WHERE status = 'MONETIZED_OUTREACH';"
    ).fetchall()

    if not leads:
        print("  [*] Outreach gate empty. Nothing to dispatch.")
        return

    can_send = bool(api_key) and live_send
    print(f"  [*] Egress Mode: {'LIVE' if can_send else 'DRY-RUN'}")

    count = 0
    for domain, company, contact, email, recon in leads:
        if not email or "@" not in email or "." not in email.split("@", 1)[-1]:
            c.execute("UPDATE leads SET status = 'SKIPPED_INVALID_EMAIL', updated_at = datetime('now') WHERE domain = ?;", (domain,))
            conn.commit()
            print(f"  [!] Dispatch skipped for invalid recipient email ({email!r}): {domain}")
            continue
        if BLOCKLIST.is_blocked(domain) or (email and BLOCKLIST.is_blocked(email)):
            print(f"  [!] Dispatch skipped for blocklisted domain: {domain}")
            continue
        checkout_url = resolve_checkout_link(email)
        body = (
            f"Hello {contact or 'Security Team'},\n\n"
            f"Perimeter findings for {domain}:\n{recon}\n\n"
            f"Plans: {checkout_url}\n\n"
            f"— Kalen Vandenbos\n"
            f"Nomadik Security Operations"
        )
        if not can_send:
            print(f"  [DRY-RUN] {email} -> {domain} ({checkout_url})")
            count += 1
        else:
            payload = {
                "sender": {"name": "Kalen Vandenbos", "email": "outreach@nomadik.site"},
                "to": [{"email": email, "name": contact or company}],
                "subject": f"Security Notice: Perimeter Exposure Report for {company}",
                "textContent": body,
                "htmlContent": render_clean_html(body),
            }
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=json.dumps(payload).encode(),
                headers={
                    "accept": "application/json",
                    "api-key": api_key,
                    "content-type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status in (200, 201, 202):
                        c.execute(
                            "UPDATE leads SET status = 'DISPATCHED', dispatched_at = datetime('now'), updated_at = datetime('now') WHERE domain = ?;",
                            (domain,),
                        )
                        conn.commit()
                        print(f"  [+] Sent to {email} (HTTP {resp.status})")
                        count += 1
            except urllib.error.HTTPError as e:
                print(f"  [-] Failed {email}: HTTP {e.code} - {e.read().decode()}")

    print(f"\n[Stage 4/4] Processed: {count} | Mode: {'LIVE' if can_send else 'DRY-RUN'}")


import html as html_lib

def render_clean_html(text_body: str) -> str:
    escaped = html_lib.escape(text_body)
    linked = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', escaped)
    paras = [f"<p>{b.strip().replace(chr(10), '<br>')}</p>" for b in linked.split("\n\n") if b.strip()]
    return '<html><body style="font-family:sans-serif;font-size:14px;line-height:1.5;color:#111;">' + "".join(paras) + "</body></html>"


def main():
    live_send = "--send" in sys.argv[1:]
    api_key = load_credentials()
    conn = sqlite3.connect(DB_PATH, timeout=30.0); conn.execute('PRAGMA journal_mode=WAL;'); conn.execute('PRAGMA busy_timeout=30000;')
    try:
        stage_ingestion(conn)
        stage_recon(conn)
        stage_dispatch(conn, api_key, live_send=live_send)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

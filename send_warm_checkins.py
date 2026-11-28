#!/usr/bin/env python3
from datetime import datetime, timezone
from followup_engine import DB_PATH, _connect_db, send_brevo_email, upgrade_db_schema

LEADS = [
    ("milehighlocksmith.com", "service@milehighlocksmith.com", "Mile High Locksmith\u00ae", "Mile High Locksmith", "stops third parties from spoofing your dispatch domain and keeps customer booking emails landing cleanly in inboxes"),
    ("foothillsgaragedoor.com", "hello@foothillsgaragedoor.com", "Foothills Garage Door Service", "Foothills Garage Door Service", "prevents estimate and invoice emails from getting flagged or spoofed, with zero interruption to your website or phones"),
    ("englewooddental.com", "info@englewooddental.com", "Englewood Dental", "Englewood Dental", "protects patient appointment communications from domain spoofing with zero disruption to your front desk"),
]

upgrade_db_schema(DB_PATH)
conn = _connect_db(DB_PATH)
cur = conn.cursor()
now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

for domain, email, subj_co, greet_co, benefit in LEADS:
    subj = f"Re: Security Notice: Perimeter Exposure Report for {subj_co}"
    body = (
        f"Hi {greet_co} Team,\n\n"
        f"Quick follow-up on the perimeter report I sent over for {domain}\u2014wanted to make sure the DMARC/SPF alignment and exposed web-header notes made sense on your end.\n\n"
        f"Hardening those records {benefit}. We can deploy the full fix this week with zero downtime: https://nomadik.site/#pricing\n\n"
        "Reply here if you'd like me to walk through the specific DNS records first.\n\n"
        "Best regards,\nKalen Vandenbos\nNomadik Security Operations\noutreach@nomadik.site"
    )
    if send_brevo_email(email, subj, body):
        cur.execute(
            "UPDATE leads SET sequence_step=1, status='FOLLOWUP_SENT', last_contacted_at=?, updated_at=? WHERE LOWER(domain)=? OR LOWER(COALESCE(contact_email,email))=?",
            (now_str, now_str, domain, email),
        )
        conn.commit()
        print(f"[+] Sent & updated sequence_step=1 -> {email} ({cur.rowcount} row)")
    else:
        print(f"[!] Failed -> {email}")
conn.close()

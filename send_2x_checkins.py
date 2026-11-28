#!/usr/bin/env python3
from datetime import datetime, timezone
from followup_engine import DB_PATH, _connect_db, send_brevo_email, upgrade_db_schema

LEADS = [
    ("foothillsaccounting.com", "administration@foothillsaccounting.com", "Foothills Accounting & Tax", "Foothills Accounting & Tax Team", "protects tax and client communications from domain spoofing ahead of filing season"),
    ("peakconstruction.com", "info@peakconstruction.com", "Peak Construction", "Peak Construction Team", "keeps bid submissions, subcontractor agreements, and invoice threads from being spoofed or flagged"),
    ("peakwindows.com", "bids@peakwindows.com", "Peak Windows", "Peak Windows Team", "ensures quote and bid emails land directly in customer inboxes without spoofing risk"),
    ("flatironsplumbing.com", "service@flatironsplumbing.com", "Flatirons Plumbing", "Flatirons Plumbing Team", "keeps service dispatch confirmations and customer invoices landing cleanly in inboxes"),
    ("firestonebuilders.com", "info@firestonebuilders.com", "Firestone Builders", "Firestone Builders Team", "prevents third parties from spoofing your project and vendor correspondence"),
    ("frontrangepainting.com", "peter@frontrangepainting.com", "Front Range Painting", "Peter", "protects estimate approvals and customer scheduling threads from domain spoofing"),
    ("dcps.com", "info@dcps.com", "DCPS", "DCPS Team", "locks down commercial property communications and web headers without touching active operations"),
    ("tectaamerica.com", "service@tectaamerica.com", "Tecta America", "Tecta America Team", "keeps commercial service dispatches and client records authenticated across spam filters"),
    ("brothersplumbing.com", "service@brothersplumbing.com", "Brothers Plumbing, Heating, & Electric", "Brothers Plumbing, Heating, & Electric Team", "stops domain spoofing on dispatch alerts and keeps customer booking emails out of spam"),
]
upgrade_db_schema(DB_PATH)
conn = _connect_db(DB_PATH)
cur = conn.cursor()
now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
for domain, email, subj_co, greet, benefit in LEADS:
    subj = f"Re: Security Notice: Perimeter Exposure Report for {subj_co}"
    body = f"Hi {greet},\n\nQuick follow-up on the perimeter report I sent over for {domain}\u2014wanted to make sure the DMARC/SPF alignment and exposed web-header notes made sense on your end.\n\nHardening those records {benefit}. We can deploy the full fix this week with zero downtime: https://nomadik.site/#pricing\n\nReply here if you'd like me to walk through the specific DNS records first.\n\nBest regards,\nKalen Vandenbos\nNomadik Security Operations\noutreach@nomadik.site"
    if send_brevo_email(email, subj, body):
        cur.execute("UPDATE leads SET sequence_step=1, status='FOLLOWUP_SENT', last_contacted_at=?, updated_at=? WHERE LOWER(domain)=? OR LOWER(COALESCE(contact_email,email))=?", (now_str, now_str, domain, email))
        conn.commit()
        print(f"[+] Sent & updated sequence_step=1 -> {email} ({cur.rowcount} row)")
conn.close()

#!/usr/bin/env python3
import os
import csv
import json
import argparse
from datetime import datetime, timezone
import urllib.request
import urllib.error

def load_leads(csv_path):
    leads = []
    if not os.path.isfile(csv_path):
        print(f"[-] Lead file not found: {csv_path}")
        return leads
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('email') and '@' in row.get('email', ''):
                leads.append(row)
    return leads

def clean_tier_name(tier_str):
    if not tier_str:
        return "Founder Tier"
    cleaned = tier_str.split('(')[0].strip()
    if cleaned and not cleaned.lower().endswith(('tier', 'plan', 'bundle', 'cohort')):
        cleaned = f"{cleaned} Plan"
    return cleaned if cleaned else "Founder Tier"

DEFAULT_TEXT = """Hi {first_name},

Saw your work as {title} at {company}. Most teams face significant friction around {pain_point}.

We built Nomadik Security Sentinel to solve this directly: {hook_angle}. It deploys as a local-first, zero-telemetry daemon with automated remediation loops.

We have onboarding open for our {tier_plan}.

Are you open to reviewing a quick automated audit breakdown for {company} this week?

Best,
Kalen Vandenbos
Founder & Systems Architect, Nomadik Security Operations
https://nomadik.site
"""

def generate_pitch(lead):
    first_name = lead.get('first_name', 'there').strip().capitalize()
    company = lead.get('company', 'Your Team').strip()
    title = lead.get('title', 'Engineer').strip()
    pain_point = lead.get('pain_point', 'security vulnerabilities').strip().lower()
    hook_angle = lead.get('hook_angle', 'Nomadik Security Sentinel autonomous hardening').strip()
    raw_tier = lead.get('payment_link_tier', 'Founder Tier')
    tier_plan = clean_tier_name(raw_tier)
    
    subject = f"Nomadik Sentinel // Streamlining security for {company}"
    body = DEFAULT_TEXT.format(
        first_name=first_name,
        title=title,
        company=company,
        pain_point=pain_point,
        hook_angle=hook_angle,
        tier_plan=tier_plan
    )
    return subject, body

def send_resend_email(api_key, to_email, subject, body):
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Nomadik-Sentinel-Agent/1.0"
    }
    payload = {
        "from": "Kalen Vandenbos <onboarding@resend.dev>", "reply_to": "kalen.vandenbos@gmail.com",
        "to": [to_email],
        "subject": subject,
        "text": body
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return True, data.get("id")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        return False, f"HTTP {e.code}: {err_msg}"
    except Exception as e:
        return False, str(e)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--leads', required=True)
    parser.add_argument('--outbox', required=True)
    parser.add_argument('--reports', required=True)
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args()

    os.makedirs(args.outbox, exist_ok=True)
    os.makedirs(args.reports, exist_ok=True)

    api_key = os.environ.get('RESEND_API_KEY', '').strip()
    leads = load_leads(args.leads)
    print(f"[*] Loaded {len(leads)} valid lead records from {args.leads}")

    dispatched = []
    for lead in leads:
        lead_id = lead.get('lead_id', 'UNKNOWN')
        email = lead.get('email', '').strip()
        company_raw = lead.get('company', 'Company')
        company = company_raw.replace(' ', '_')
        first_name = lead.get('first_name', 'Lead')

        subject, body = generate_pitch(lead)
        outbox_filename = os.path.join(args.outbox, f"{lead_id}_{company}_{first_name}.txt")
        with open(outbox_filename, 'w', encoding='utf-8') as f:
            f.write(f"To: {email}\nSubject: {subject}\n" + "-"*40 + f"\n\n{body}")

        status = 'QUEUED_LOCAL'
        if args.send:
            if not api_key or 're_your_actual' in api_key:
                status = 'SKIPPED_NO_API_KEY'
            else:
                success, resp = send_resend_email(api_key, email, subject, body)
                status = 'SENT_LIVE' if success else f'FAILED: {resp}'
                print(f"[+] {email} -> {status}")

        dispatched.append({
            'lead_id': lead_id,
            'email': email,
            'company': lead.get('company'),
            'file': outbox_filename,
            'status': status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    report_file = os.path.join(args.reports, f"dispatch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(dispatched, f, indent=2)

    print(f"[+] Successfully generated {len(dispatched)} personalized outbox pitches.")
    print(f"[+] Dispatch log recorded: {report_file}")

if __name__ == '__main__':
    main()

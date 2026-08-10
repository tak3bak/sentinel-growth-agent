import os
import sys
import argparse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv(".env.local", override=True)
load_dotenv(".env", override=False)

def build_emergency_outreach(company_name: str, prospect_name: str) -> dict:
    subject = f"Urgent: Incident Response & Perimeter Defense for {company_name}"
    body = f"""Hi {prospect_name},

If {company_name} is currently dealing with an active security breach, ransomware threat, or urgent compliance audit gap, Nomadik Security Operations provides 4-hour rapid emergency response and threat remediation.

Our deployment team provides:
- Immediate behavioral threat detection & perimeter isolation
- Incident containment & active audit gap defense
- Direct 4-hour SLA dispatch

You can dispatch our rapid response team directly here:
https://nomadik.site/api/checkout?priceId=price_1TwgHMD5LVILsj0FdCUQpuWt

Best regards,

Kalen Vandenbos
Founder, Nomadik Security Operations
https://nomadik.site"""

    return {
        "to_company": company_name,
        "subject": subject,
        "body": body
    }

def send_email(to_email: str, subject: str, body: str) -> bool:
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    raw_password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("DEFAULT_FROM_EMAIL", "kalen@nomadik.site")

    smtp_password = raw_password.replace(" ", "").replace("\n", "").replace("\r", "").strip("\"'")

    if not smtp_user or not smtp_password:
        print("[X] SMTP credentials missing in environment.")
        return False

    msg = MIMEMultipart()
    msg["From"] = f"Kalen Vandenbos <{from_email}>"
    msg["To"] = to_email
    msg["Reply-To"] = from_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"[+] Dispatched email to {to_email} as {from_email}")
        return True
    except Exception as e:
        print(f"[X] Failed to send email to {to_email}: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel Growth Agent Outreach Dispatcher")
    parser.add_argument("--to", type=str, help="Recipient email address to dispatch live email to")
    parser.add_argument("--company", type=str, default="Acme Financial", help="Target company name")
    parser.add_argument("--name", type=str, default="Alex", help="Target contact name")

    args = parser.parse_args()
    payload = build_emergency_outreach(args.company, args.name)

    if args.to:
        print(f"\n[*] Dispatching live outreach email to: {args.to}...")
        send_email(args.to, payload["subject"], payload["body"])
    else:
        print("\n[i] Preview Mode: Pass '--to recipient@example.com' to send live email via SMTP.")

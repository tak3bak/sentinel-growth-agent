import os
import json
import sqlite3
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import requests
from dotenv import load_dotenv

load_dotenv(".env.local", override=True)
load_dotenv(".env", override=False)

try:
    from outreach_agent import send_email
except ImportError:
    send_email = None

DB_PATH = os.getenv("DB_PATH", "growth_agent.db")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:latest")
RECIPIENT_OVERRIDE = os.getenv("TEST_RECIPIENT", "tak3bak@gmail.com")
SENDER_NAME = os.getenv("SENDER_NAME", "Kalen Vandenbos")
SENDER_ORG = os.getenv("SENDER_ORG", "Nomadik Security Operations")


def upgrade_db_schema(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(leads);")
    columns = [col[1] for col in cursor.fetchall()]

    if "recipient_email" not in columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN recipient_email TEXT;")
    if "sequence_step" not in columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN sequence_step INTEGER DEFAULT 0;")
    if "last_contacted_at" not in columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN last_contacted_at TIMESTAMP;")
        cursor.execute(
            "UPDATE leads SET last_contacted_at = created_at WHERE last_contacted_at IS NULL;"
        )

    conn.commit()
    conn.close()


class FollowUpGenerator:
    @classmethod
    def generate_followup(
        cls,
        prospect_name: str,
        company_name: str,
        domain: str,
        step: int,
        original_subject: str,
    ) -> Dict[str, str]:
        if step == 1:
            # Day 2: Light touch / context reminder
            system_prompt = f"""
You are a cybersecurity consultant at {SENDER_ORG}.
Draft a short 2-3 sentence follow-up email (under 60 words).
Rules:
1. Re-reference the security hygiene check on {domain}.
2. Low-pressure call to action (e.g., "Would a 2-minute summary report be helpful to review?").
3. Sign off exactly as: {SENDER_NAME}\n{SENDER_ORG}
"""
            user_prompt = f"Prospect: {prospect_name}, Company: {company_name}, Domain: {domain}. Subject should start with 'Re: {original_subject}'."
        else:
            # Day 4: Polite close-out / breakup email
            system_prompt = f"""
You are a cybersecurity consultant at {SENDER_ORG}.
Draft a polite, professional 2-sentence close-out email (under 45 words).
Rules:
1. State you assume cybersecurity monitoring is handled or not a priority right now.
2. Offer to be a resource down the line if needs change.
3. Sign off exactly as: {SENDER_NAME}\n{SENDER_ORG}
"""
            user_prompt = f"Prospect: {prospect_name}, Company: {company_name}. Subject should start with 'Re: {original_subject}'."

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"num_predict": 200, "temperature": 0.6},
        }

        try:
            res = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
            res.raise_for_status()
            raw = res.json().get("message", {}).get("content", "").strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            clean_json = match.group(0) if match else raw
            return json.loads(clean_json)
        except Exception as e:
            print(f"[!] Inference fallback triggered: {e}")
            if step == 1:
                return {
                    "subject_line": f"Re: {original_subject}",
                    "email_body": (
                        f"Hi {prospect_name},\n\n"
                        f"Following up briefly on my earlier note regarding the external security surface scan on {domain}.\n\n"
                        f"Would a 2-minute summary report be helpful for your team to review?\n\n"
                        f"Best regards,\n{SENDER_NAME}\n{SENDER_ORG}"
                    ),
                }
            else:
                return {
                    "subject_line": f"Re: {original_subject}",
                    "email_body": (
                        f"Hi {prospect_name},\n\n"
                        f"I assume security endpoint monitoring and surface hygiene are fully dialed in right now, so I won't follow up further.\n\n"
                        f"Feel free to reach out if you ever want a quick audit of {domain} down the line.\n\n"
                        f"Best regards,\n{SENDER_NAME}\n{SENDER_ORG}"
                    ),
                }


def process_followups(dry_run: bool = False):
    upgrade_db_schema()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find leads ready for Day 2 (step 0 -> 1 after >= 2 days) or Day 4 (step 1 -> 2 after >= 2 days)
    cursor.execute("""
        SELECT * FROM leads 
        WHERE status IN ('DISPATCHED', 'FOLLOWUP_SENT') 
          AND sequence_step < 2
        """)
    leads = cursor.fetchall()
    print(f"[*] Found {len(leads)} active lead(s) in the sequence queue.")

    for lead in leads:
        lead_id = lead["id"]
        name = lead["prospect_name"]
        company = lead["company_name"]
        domain = lead["domain"]
        step = lead["sequence_step"] or 0
        last_contact = lead["last_contacted_at"] or lead["created_at"]
        target_email = lead["recipient_email"] or RECIPIENT_OVERRIDE
        subject_orig = lead["subject_line"] or f"security surface audit: {domain}"

        # Parse timestamp
        try:
            last_dt = datetime.strptime(last_contact, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            last_dt = datetime.utcnow()

        days_elapsed = (datetime.utcnow() - last_dt).days

        # Delay check: Step 0 needs 2 days for Step 1; Step 1 needs 2 days for Step 2
        required_days = 2
        if days_elapsed < required_days and not dry_run:
            print(
                f"[-] Lead #{lead_id} ({name} @ {company}): {days_elapsed}/{required_days} days elapsed. Skipping."
            )
            continue

        next_step = step + 1
        print(f"\n[*] Processing Sequence Step {next_step} for {name} ({company})...")

        pitch = FollowUpGenerator.generate_followup(
            name, company, domain, next_step, subject_orig
        )
        sub = pitch.get("subject_line", f"Re: {subject_orig}")
        body = pitch.get("email_body", "")

        if dry_run:
            print("[DRY RUN] Generated Email:")
            print(f"To: {target_email}\nSubject: {sub}\n\n{body}\n")
            continue

        sent = False
        if send_email and target_email:
            try:
                sent = send_email(target_email, sub, body)
            except Exception as ex:
                print(f"[!] Send failed: {ex}")

        # Update Lead State
        status_update = "FOLLOWUP_SENT" if (sent or not send_email) else "FAILED"
        if next_step >= 2:
            status_update = "COMPLETED"

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            UPDATE leads 
            SET sequence_step = ?, last_contacted_at = ?, status = ?
            WHERE id = ?
            """,
            (next_step, now_str, status_update, lead_id),
        )
        conn.commit()
        print(f"[+] Lead #{lead_id} updated: Step {next_step} -> {status_update}")

    conn.close()


if __name__ == "__main__":
    import sys

    is_dry = "--dry-run" in sys.argv
    process_followups(dry_run=is_dry)

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.request
from dotenv import dotenv_values, load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env.local", override=True)
load_dotenv(BASE_DIR / ".env", override=False)

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "leads.db"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
if not OLLAMA_HOST.startswith(("http://", "https://")):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
SENDER_NAME = os.getenv("SENDER_NAME", "Kalen Vandenbos")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "outreach@nomadik.site")
SENDER_ORG = os.getenv("SENDER_ORG", "Nomadik Security Operations")
PRICING_URL = os.getenv("PRICING_URL", "https://nomadik.site/#pricing")
LIVE_CAMPAIGN_CUTOFF = os.getenv("LIVE_CAMPAIGN_CUTOFF", "2026-11-27 22:00:00")
MAX_FOLLOWUPS_PER_RUN = int(os.getenv("MAX_FOLLOWUPS_PER_RUN", "40"))
FOLLOWUP_DELAY_DAYS = int(os.getenv("FOLLOWUP_DELAY_DAYS", "2"))


def _connect_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def _get_brevo_api_key() -> str:
    return (
        os.getenv("BREVO_API_KEY", "").strip()
        or dotenv_values(BASE_DIR / ".env").get("BREVO_API_KEY", "").strip()
    )


import html as html_lib

def render_clean_html(text_body: str) -> str:
    escaped = html_lib.escape(text_body)
    linked = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', escaped)
    paras = [f"<p>{b.strip().replace(chr(10), '<br>')}</p>" for b in linked.split("\n\n") if b.strip()]
    return '<html><body style="font-family:sans-serif;font-size:14px;line-height:1.5;color:#111;">' + "".join(paras) + "</body></html>"



def check_daily_quota(db_path=DB_PATH, daily_cap=280):
    c = sqlite3.connect(db_path, timeout=30.0)
    c.execute("PRAGMA busy_timeout=30000;")
    used = c.execute(
        "SELECT COUNT(*) FROM leads WHERE COALESCE(last_contacted_at, dispatched_at) >= datetime('now', '-24 hours') AND status IN ('DISPATCHED', 'DISPATCHED_ACTIVE', 'FOLLOWUP_SENT', 'COMPLETED');"
    ).fetchone()[0]
    c.close()
    return used, used < daily_cap


def send_brevo_email(to_email: str, subject: str, text_body: str) -> bool:
    used, allowed = check_daily_quota(DB_PATH, int(os.getenv('BREVO_DAILY_CAP', '280')))
    if not allowed:
        print(f'[!] Total daily Brevo safety cap reached ({used}/280 in 24h); leaving 20 credits for manual replies.')
        return False
    api_key = _get_brevo_api_key()
    if not api_key:
        print("[!] BREVO_API_KEY missing; cannot send live follow-up.")
        return False

    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text_body,
        "htmlContent": render_clean_html(text_body),
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 201, 202)
    except Exception as exc:
        print(f"[!] Brevo send error for {to_email}: {exc}")
        return False


def upgrade_db_schema(db_path: Path = DB_PATH) -> None:
    conn = _connect_db(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(leads);")
    columns = [col[1] for col in cursor.fetchall()]

    if "recipient_email" not in columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN recipient_email TEXT;")
    if "sequence_step" not in columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN sequence_step INTEGER DEFAULT 0;")
    if "last_contacted_at" not in columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN last_contacted_at TIMESTAMP;")
        cursor.execute(
            "UPDATE leads SET last_contacted_at = COALESCE(dispatched_at, created_at) WHERE last_contacted_at IS NULL;"
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
            system_prompt = (
                f"You are a cybersecurity consultant at {SENDER_ORG}. "
                f"Draft a short 2-3 sentence follow-up email (under 65 words). "
                f"Rules: 1. Re-reference the external security perimeter report on {domain}. "
                f"2. Include a low-pressure CTA referencing {PRICING_URL}. "
                f"3. Sign off exactly as:\n{SENDER_NAME}\n{SENDER_ORG}"
            )
            user_prompt = (
                f"Prospect: {prospect_name}, Company: {company_name}, Domain: {domain}. "
                f"Subject must be: Re: {original_subject}"
            )
        else:
            system_prompt = (
                f"You are a cybersecurity consultant at {SENDER_ORG}. "
                f"Draft a polite 2-sentence close-out email (under 50 words). "
                f"Rules: 1. State you assume DMARC, TLS, and perimeter monitoring on {domain} are handled right now. "
                f"2. Leave {PRICING_URL} in case needs change. "
                f"3. Sign off exactly as:\n{SENDER_NAME}\n{SENDER_ORG}"
            )
            user_prompt = (
                f"Prospect: {prospect_name}, Company: {company_name}, Domain: {domain}. "
                f"Subject must be: Re: {original_subject}"
            )

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": {
                "type": "object",
                "properties": {
                    "subject_line": {"type": "string"},
                    "email_body": {"type": "string"},
                },
                "required": ["subject_line", "email_body"],
            },
            "stream": False,
            "options": {"num_predict": 200, "temperature": 0.5},
        }

        try:
            req = urllib.request.Request(
                f"{OLLAMA_HOST}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"content-type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                raw = json.loads(resp.read().decode("utf-8")).get("message", {}).get("content", "").strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            clean_json = match.group(0) if match else raw
            data = json.loads(clean_json)
            body = str(data.get("email_body", "")).replace("<br><br>", "\n\n").replace("<br>", "\n").strip()
            if not body or "[" in body:
                raise ValueError("invalid/placeholder email_body")
            data["subject_line"] = f"Re: {original_subject}"
            data["email_body"] = body
            return data
        except Exception:
            if step == 1:
                return {
                    "subject_line": f"Re: {original_subject}",
                    "email_body": (
                        f"Hi {prospect_name},\n\n"
                        f"Following up briefly on the external security perimeter report I sent over for {company_name} ({domain}).\n\n"
                        f"If you'd like us to lock down your DMARC/SPF alignment and exposed web headers, remediation tiers are outlined here: {PRICING_URL}\n\n"
                        f"Best regards,\n{SENDER_NAME}\n{SENDER_ORG}"
                    ),
                }
            return {
                "subject_line": f"Re: {original_subject}",
                "email_body": (
                    f"Hi {prospect_name},\n\n"
                    f"I assume perimeter monitoring and email authentication for {domain} are already covered, so I won't follow up further.\n\n"
                    f"If you ever want a quick security remediation pass down the line, you can reach us anytime at {PRICING_URL}\n\n"
                    f"Best regards,\n{SENDER_NAME}\n{SENDER_ORG}"
                ),
            }


def _parse_utc(ts_val: Any) -> datetime:
    cleaned = str(ts_val).replace("T", " ").split(".")[0].strip()
    return datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def process_followups(dry_run: bool = False, limit: int = MAX_FOLLOWUPS_PER_RUN) -> int:
    upgrade_db_schema()
    conn = _connect_db(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM leads
        WHERE status IN ('DISPATCHED', 'DISPATCHED_ACTIVE', 'FOLLOWUP_SENT')
          AND sequence_step < 2
          AND company_name IS NOT NULL
          AND TRIM(company_name) != ''
          AND COALESCE(dispatched_at, updated_at, created_at) >= ?
        ORDER BY COALESCE(last_contacted_at, dispatched_at, created_at) ASC
        """,
        (LIVE_CAMPAIGN_CUTOFF,),
    )
    leads = cursor.fetchall()
    print(f"[*] Found {len(leads)} eligible live-campaign lead(s) in the follow-up queue.")

    now_utc = datetime.now(timezone.utc)
    processed = 0

    for lead in leads:
        if processed >= limit:
            print(f"[*] Reached MAX_FOLLOWUPS_PER_RUN ({limit}); stopping batch.")
            break

        lead_id = lead["id"]
        company = str(lead["company_name"]).strip()
        domain = str(lead["domain"]).strip()
        keys = set(lead.keys())
        raw_name = lead["prospect_name"] if "prospect_name" in keys and lead["prospect_name"] else ""
        name = str(raw_name).strip() or f"{company} Team"
        step = int(lead["sequence_step"] or 0)
        last_contact = (
            (lead["last_contacted_at"] if "last_contacted_at" in keys and lead["last_contacted_at"] else None)
            or (lead["dispatched_at"] if "dispatched_at" in keys and lead["dispatched_at"] else None)
            or (lead["updated_at"] if "updated_at" in keys and lead["updated_at"] else None)
            or lead["created_at"]
        )
        target_email = (
            (lead["contact_email"] if "contact_email" in keys and lead["contact_email"] else None)
            or (lead["email"] if "email" in keys and lead["email"] else None)
            or (lead["recipient_email"] if "recipient_email" in keys and lead["recipient_email"] else None)
        )
        if not target_email:
            continue

        subject_orig = (
            str(lead["subject_line"]).strip()
            if "subject_line" in keys and lead["subject_line"]
            else f"Security Notice: Perimeter Exposure Report for {company}"
        )

        try:
            last_dt = _parse_utc(last_contact)
        except Exception:
            last_dt = now_utc

        elapsed_hours = (now_utc - last_dt).total_seconds() / 3600.0
        required_hours = FOLLOWUP_DELAY_DAYS * 24.0

        if elapsed_hours < required_hours and not dry_run:
            continue

        next_step = step + 1
        pitch = FollowUpGenerator.generate_followup(
            name, company, domain, next_step, subject_orig
        )
        sub = pitch.get("subject_line", f"Re: {subject_orig}")
        body = pitch.get("email_body", "")

        if dry_run:
            print(f"\n[DRY RUN] Step {next_step} -> {target_email} ({elapsed_hours:.1f}h elapsed)")
            print(f"Subject: {sub}\n{body}\n" + "-" * 50)
            processed += 1
            if processed >= 3:
                print(f"[DRY RUN] Previewed 3 of {len(leads)} eligible leads.")
                break
            continue

        sent = send_brevo_email(str(target_email).strip(), sub, body)
        if not sent:
            print(f"[!] Skipped DB update for {target_email} due to dispatch failure.")
            continue

        status_update = "COMPLETED" if next_step >= 2 else "FOLLOWUP_SENT"
        now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            UPDATE leads
            SET sequence_step = ?, last_contacted_at = ?, updated_at = ?, status = ?
            WHERE id = ?
            """,
            (next_step, now_str, now_str, status_update, lead_id),
        )
        conn.commit()
        processed += 1
        print(f"[+] Sent Step {next_step} to {target_email} -> {status_update}")

    conn.close()
    print(f"[*] Follow-up run complete. Processed: {processed}")
    return processed


if __name__ == "__main__":
    import sys

    is_dry = "--dry-run" in sys.argv
    process_followups(dry_run=is_dry)

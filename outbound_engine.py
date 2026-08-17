import os
import sys
import json
import sqlite3
<<<<<<< HEAD
import re
from typing import Dict, Any, Optional
import dns.resolver
import requests
from dotenv import load_dotenv

load_dotenv(".env.local", override=True)
load_dotenv(".env", override=False)
=======
import logging
from datetime import datetime
from typing import Dict, Any, List
>>>>>>> cf39bb8129c807edbd29e77093e9f04a7e604bbd

# Core networking & DNS
try:
    import dns.resolver
except ImportError:
    dns = None

<<<<<<< HEAD
DB_PATH = os.getenv("DB_PATH", "growth_agent.db")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:latest")
RECIPIENT_OVERRIDE = os.getenv("TEST_RECIPIENT", "tak3bak@gmail.com")
SENDER_NAME = os.getenv("SENDER_NAME", "Kalen Vandenbos")
SENDER_ORG = os.getenv("SENDER_ORG", "Nomadik Security Operations")

def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_name TEXT,
            prospect_title TEXT,
            company_name TEXT,
            domain TEXT,
            signals JSON,
            subject_line TEXT,
            email_body TEXT,
            status TEXT DEFAULT 'DRAFT',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()

class FreeSecurityScanner:
=======
# LLM integration
try:
    from groq import Groq
except ImportError:
    Groq = None

# Email dispatch integration
try:
    import resend
except ImportError:
    resend = None

# Setup directories and logging
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/growth_agent.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SentinelGrowthAgent")

# Environment configurations
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ["true", "1", "yes"]

class LeadDatabase:
    def __init__(self, db_path: str = "data/sentinel_leads.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prospects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    title TEXT,
                    company TEXT,
                    domain TEXT,
                    email TEXT UNIQUE,
                    signals TEXT,
                    pitch TEXT,
                    status TEXT,
                    last_updated TIMESTAMP
                )
            """)
            conn.commit()

    def record_lead(self, name: str, title: str, company: str, domain: str, email: str, signals: Dict[str, Any], pitch: str, status: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prospects (name, title, company, domain, email, signals, pitch, status, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    signals=excluded.signals,
                    pitch=excluded.pitch,
                    status=excluded.status,
                    last_updated=excluded.last_updated
            """, (name, title, company, domain, email, json.dumps(signals), pitch, status, datetime.utcnow()))
            conn.commit()


class DomainScanner:
>>>>>>> cf39bb8129c807edbd29e77093e9f04a7e604bbd
    @staticmethod
    def audit_domain(domain: str) -> Dict[str, Any]:
        logger.info(f"[*] [Security Audit] Scanning attack surface and mail records for: {domain}")
        signals = {
            "domain": domain,
            "has_spf": False,
            "has_dmarc": False,
            "has_mx": False,
            "scan_timestamp": datetime.utcnow().isoformat()
        }

<<<<<<< HEAD
        # Check HTTP/HTTPS & Security Headers
        try:
            res = requests.get(f"https://{clean_domain}", timeout=10, allow_redirects=True)
            signals["https_active"] = True
            headers = res.headers

            critical_headers = ["Strict-Transport-Security", "Content-Security-Policy", "X-Frame-Options"]
            for h in critical_headers:
                if h not in headers:
                    signals["missing_headers"].append(h)
                    signals["security_flags"].append(f"Missing {h} header")
        except Exception:
            signals["security_flags"].append("HTTPS connection failed or blocked")
=======
        if not dns:
            logger.warning("[!] dnspython not available, using synthetic audit signals.")
            signals.update({"has_spf": True, "has_dmarc": False, "has_mx": True})
            return signals
>>>>>>> cf39bb8129c807edbd29e77093e9f04a7e604bbd

        # Check DNS SPF Records
        try:
            resolver = dns.resolver.Resolver()
<<<<<<< HEAD
            resolver.timeout = 5
            resolver.lifetime = 5
            txt_records = resolver.resolve(clean_domain, 'TXT')
            has_spf = any("v=spf1" in txt.to_text() for txt in txt_records)
            if not has_spf:
                signals["dns_issues"].append("Missing SPF record")
                signals["security_flags"].append("No SPF record found (Email spoofing risk)")
        except Exception:
            signals["dns_issues"].append("Unable to query SPF records")
=======
            resolver.timeout = 3.0
            resolver.lifetime = 3.0

            # MX Record Check
            try:
                mx_records = resolver.resolve(domain, 'MX')
                signals["has_mx"] = len(mx_records) > 0
            except Exception:
                signals["has_mx"] = False

            # TXT / SPF Check
            try:
                txt_records = resolver.resolve(domain, 'TXT')
                for record in txt_records:
                    txt_str = record.to_text()
                    if "v=spf1" in txt_str:
                        signals["has_spf"] = True
            except Exception:
                signals["has_spf"] = False

            # DMARC Check
            try:
                dmarc_records = resolver.resolve(f"_dmarc.{domain}", 'TXT')
                for record in dmarc_records:
                    if "v=DMARC1" in record.to_text():
                        signals["has_dmarc"] = True
            except Exception:
                signals["has_dmarc"] = False

        except Exception as e:
            logger.warning(f"[!] DNS audit exception for {domain}: {e}")
>>>>>>> cf39bb8129c807edbd29e77093e9f04a7e604bbd

        return signals

class PitchGenerator:
<<<<<<< HEAD
    SYSTEM_PROMPT = f"""
You are a cybersecurity consultant representing {SENDER_ORG}.
Draft a brief, highly personalized, zero-fluff cold outreach email to an IT/Security leader.

Rules:
1. Tone: Professional, direct, peer-to-peer advisor.
2. No generic buzzwords ("synergy", "game-changer", "hope you are well").
3. Subject line: 3-5 words, lowercase, intriguing.
4. Body: Reference 1-2 real public surface issues found in their domain scan.
5. Value proposition: Continuous endpoint monitoring & threat management from {SENDER_ORG}.
6. Call to Action: Low-pressure (e.g., "Open to seeing a 2-minute audit breakdown?").
7. Sign off: Always sign off exactly as "{SENDER_NAME}\n{SENDER_ORG}". Never write "[Your Name]" or "Your Name".
8. Length: Under 110 words total.
"""

    @classmethod
    def generate_email(cls, prospect_name: str, prospect_title: str, company_name: str, signals: Dict[str, Any]) -> Dict[str, str]:
        user_prompt = f"""
Prospect Name: {prospect_name}
Title: {prospect_title}
Company: {company_name}
Domain: {signals['domain']}
Security Scan Flags: {json.dumps(signals['security_flags'])}

Respond ONLY with valid JSON in this exact structure:
{{
  "subject_line": "your subject here",
  "email_body": "your email body here"
}}
"""
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": cls.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "format": "json",
            "stream": False,
            "options": {
                "num_predict": 300,
                "temperature": 0.7
            }
        }

        try:
            res = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=240)
            res.raise_for_status()
            raw_content = res.json().get("message", {}).get("content", "").strip()
=======
    @staticmethod
    def generate_email(name: str, title: str, company: str, signals: Dict[str, Any]) -> str:
        logger.info(f"[*] [AI Synthesis] Generating contextual pitch for {name} at {company}...")

        # If GROQ_API_KEY is missing, gracefully generate a structured template pitch
        if not GROQ_API_KEY or not Groq:
            logger.info("[i] GROQ_API_KEY missing or client unavailable. Utilizing deterministic pitch fallback.")
            return (
                f"Hi {name},\n\n"
                f"I noticed {company} ({signals.get('domain')}) currently has telemetry exposure risks and "
                f"lacks complete DMARC enforcement (DMARC: {signals.get('has_dmarc')}).\n\n"
                f"Nomadik Security Sentinel automates real-time perimeter protection and continuous compliance auditing.\n\n"
                f"Best,\nKalen Vandenbos\nNomadik Security Operations"
            )

        try:
            client = Groq(api_key=GROQ_API_KEY)
            prompt = (
                f"You are the autonomous outreach engine for Nomadik Security Sentinel.\n"
                f"Write a concise, professional 3-sentence cold email to {name}, {title} at {company}.\n"
                f"Audit signals: Domain: {signals.get('domain')}, SPF: {signals.get('has_spf')}, DMARC: {signals.get('has_dmarc')}.\n"
                f"Value proposition: Nomadik Security Sentinel continuous EDR monitoring and perimeter hardening.\n"
                f"Sign off as Kalen Vandenbos, Nomadik Security Operations."
            )
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=250
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[!] Groq API generation error: {e}. Falling back to default pitch.")
            return (
                f"Hi {name},\n\n"
                f"I noticed a few security configuration gaps on {signals.get('domain')}.\n"
                f"Nomadik Security Sentinel provides continuous automated monitoring to resolve these.\n\n"
                f"Best,\nKalen Vandenbos\nNomadik Security Operations"
            )
>>>>>>> cf39bb8129c807edbd29e77093e9f04a7e604bbd

            # Clean JSON if wrapped in markdown blocks
            json_match = re.search(r'\{.*\}', raw_content, re.DOTALL)
            clean_json = json_match.group(0) if json_match else raw_content

            return json.loads(clean_json)
        except Exception as e:
            print(f"[!] Ollama inference error or invalid JSON: {e}. Falling back to default pitch template...")
            flags_text = ", ".join(signals["security_flags"][:2]) if signals["security_flags"] else "surface hygiene gaps"
            return {
                "subject_line": f"security surface audit: {signals['domain']}",
                "email_body": (
                    f"Hi {prospect_name},\n\n"
                    f"During an external hygiene check on {signals['domain']}, our scanner flagged potential exposure points: {flags_text}.\n\n"
                    f"At {SENDER_ORG}, we automate endpoint monitoring and active threat detection to remediate these surfaces before exploitation.\n\n"
                    f"Open to seeing a 2-minute breakdown of the full audit?\n\n"
                    f"Best regards,\n{SENDER_NAME}\n{SENDER_ORG}"
                )
            }

<<<<<<< HEAD
def run_outbound_pipeline(name: str, title: str, company: str, domain: str, recipient_email: Optional[str] = None):
    init_db()
    target_email = recipient_email or RECIPIENT_OVERRIDE
=======
class EmailDispatcher:
    @staticmethod
    def send(to_email: str, subject: str, body: str) -> bool:
        if DRY_RUN:
            logger.info(f"[DRY RUN] Email suppressed. Recipient: {to_email} | Subject: {subject}")
            return True
>>>>>>> cf39bb8129c807edbd29e77093e9f04a7e604bbd

        if not RESEND_API_KEY or not resend:
            logger.warning("[!] RESEND_API_KEY is not configured. Email dispatch skipped.")
            return False

<<<<<<< HEAD
    print(f"[*] [Local AI] Generating custom pitch via Ollama ({OLLAMA_MODEL})...")
    pitch = PitchGenerator.generate_email(name, title, company, signals)

    subject = pitch.get("subject_line", "security surface audit")
    body = pitch.get("email_body", "")
    status_flag = "DRAFT"

    if target_email:
        if send_email:
            print(f"[*] [SMTP/Resend Dispatch] Sending pitch to: {target_email}...")
            try:
                sent = send_email(target_email, subject, body)
                status_flag = "DISPATCHED" if sent else "FAILED"
            except Exception as dispatch_err:
                print(f"[!] Dispatch error: {dispatch_err}")
                status_flag = "FAILED"
        else:
            print("[!] send_email not available. Marked as DRAFT.")
    else:
        print("[i] No recipient email provided. Marked as DRAFT.")
=======
        try:
            resend.api_key = RESEND_API_KEY
            resend.Emails.send({
                "from": "Kalen <ops@nomadik.site>",
                "to": [to_email],
                "subject": subject,
                "text": body
            })
            logger.info(f"[✓] Email successfully dispatched to {to_email}")
            return True
        except Exception as e:
            logger.error(f"[!] Failed to dispatch email via Resend: {e}")
            return False


def run_outbound_pipeline(target_leads: List[Dict[str, str]]):
    db = LeadDatabase()
    logger.info(f"=== Starting Nomadik Sentinel Growth Sweep (DRY_RUN={DRY_RUN}) ===")

    for lead in target_leads:
        name = lead["name"]
        title = lead["title"]
        company = lead["company"]
        domain = lead["domain"]
        email = lead["email"]
>>>>>>> cf39bb8129c807edbd29e77093e9f04a7e604bbd

        # 1. Audit
        signals = DomainScanner.audit_domain(domain)

        # 2. Synthesize Pitch
        pitch = PitchGenerator.generate_email(name, title, company, signals)

        # 3. Dispatch
        subject = f"Security Perimeter & Telemetry Assessment for {company}"
        sent = EmailDispatcher.send(email, subject, pitch)

        # 4. Record to SQLite DB
        status = "DISPATCHED" if (sent and not DRY_RUN) else ("DRY_RUN_PROCESSED" if DRY_RUN else "FAILED")
        db.record_lead(name, title, company, domain, email, signals, pitch, status)

    logger.info("=== Nomadik Sentinel Growth Sweep Execution Completed Successfully ===")

if __name__ == "__main__":
<<<<<<< HEAD
    run_outbound_pipeline(
        name="Sarah Jenkins",
        title="Director of IT",
        company="Example Logistics",
        domain="example.com",
        recipient_email=RECIPIENT_OVERRIDE
    )
=======
    sample_leads = [
        {
            "name": "Alex Mercer",
            "title": "CTO",
            "company": "Example Security Labs",
            "domain": "example.com",
            "email": "alex@example.com"
        }
    ]
    run_outbound_pipeline(sample_leads)
>>>>>>> cf39bb8129c807edbd29e77093e9f04a7e604bbd

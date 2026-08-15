import os
import json
import sqlite3
import re
from typing import Dict, Any, Optional
import dns.resolver
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
    @staticmethod
    def analyze_domain(domain: str) -> Dict[str, Any]:
        clean_domain = domain.replace("https://", "").replace("http://", "").strip("/")
        signals = {
            "domain": clean_domain,
            "https_active": False,
            "missing_headers": [],
            "dns_issues": [],
            "security_flags": []
        }

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

        # Check DNS SPF Records
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = 5
            resolver.lifetime = 5
            txt_records = resolver.resolve(clean_domain, 'TXT')
            has_spf = any("v=spf1" in txt.to_text() for txt in txt_records)
            if not has_spf:
                signals["dns_issues"].append("Missing SPF record")
                signals["security_flags"].append("No SPF record found (Email spoofing risk)")
        except Exception:
            signals["dns_issues"].append("Unable to query SPF records")

        return signals

class PitchGenerator:
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

def run_outbound_pipeline(name: str, title: str, company: str, domain: str, recipient_email: Optional[str] = None):
    init_db()
    target_email = recipient_email or RECIPIENT_OVERRIDE

    print(f"[*] [Free Scan] Checking domain security for: {domain}...")
    signals = FreeSecurityScanner.analyze_domain(domain)

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

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO leads (prospect_name, prospect_title, company_name, domain, signals, subject_line, email_body, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (name, title, company, domain, json.dumps(signals), subject, body, status_flag)
    )
    conn.commit()
    conn.close()

    print("\n[+] Success! Lead processed and recorded in growth_agent.db")
    print(f"[*] Status: {status_flag}")
    print("=" * 50)
    print(f"SUBJECT: {subject}\n")
    print(body)
    print("=" * 50)

if __name__ == "__main__":
    run_outbound_pipeline(
        name="Sarah Jenkins",
        title="Director of IT",
        company="Example Logistics",
        domain="example.com",
        recipient_email=RECIPIENT_OVERRIDE
    )

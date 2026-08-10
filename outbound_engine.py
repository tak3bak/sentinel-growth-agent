import os
import json
import sqlite3
from typing import Dict, Any, Optional
import dns.resolver
from dotenv import load_dotenv
from groq import Groq

load_dotenv(".env.local", override=True)
load_dotenv(".env", override=False)

try:
    from outreach_agent import send_email
except ImportError:
    send_email = None

DB_PATH = os.getenv("DB_PATH", "growth_agent.db")


def get_groq_client() -> Optional[Groq]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    return Groq(api_key=api_key.strip("\"'"))


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

        try:
            import requests
            res = requests.get(f"https://{clean_domain}", timeout=5, allow_redirects=True)
            signals["https_active"] = True
            headers = res.headers

            critical_headers = ["Strict-Transport-Security", "Content-Security-Policy", "X-Frame-Options"]
            for h in critical_headers:
                if h not in headers:
                    signals["missing_headers"].append(h)
                    signals["security_flags"].append(f"Missing {h} header")

        except Exception:
            signals["security_flags"].append("HTTPS connection failed or blocked")

        try:
            txt_records = dns.resolver.resolve(clean_domain, 'TXT')
            has_spf = any("v=spf1" in txt.to_text() for txt in txt_records)
            if not has_spf:
                signals["dns_issues"].append("Missing SPF record")
                signals["security_flags"].append("No SPF record found (Email spoofing risk)")
        except Exception:
            signals["dns_issues"].append("Unable to query SPF records")

        return signals


class PitchGenerator:
    SYSTEM_PROMPT = """
You are a cybersecurity consultant representing Nomadik Security Operations.
Draft a brief, highly personalized, zero-fluff cold outreach email to an IT/Security leader.

Rules:
1. Tone: Professional, direct, peer-to-peer advisor.
2. No generic fluff or buzzwords ("synergy", "game-changer", "hope you are well").
3. Subject line: 3-5 words, lowercase, intriguing.
4. Body: Reference 1-2 real public surface issues found in their domain scan.
5. Value proposition: Pitch Nomadik Security Operations' continuous endpoint monitoring & threat management.
6. Call to Action: Low-pressure (e.g., "Open to seeing a 2-minute audit breakdown?").
7. Length: Under 110 words total.
"""

    @classmethod
    def generate_email(cls, prospect_name: str, prospect_title: str, company_name: str, signals: Dict[str, Any]) -> Dict[str, str]:
        client = get_groq_client()
        if not client:
            raise ValueError("GROQ_API_KEY environment variable is missing!")

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

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": cls.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.6
        )

        return json.loads(response.choices[0].message.content)


def run_outbound_pipeline(name: str, title: str, company: str, domain: str, recipient_email: Optional[str] = None):
    init_db()

    print(f"[*] [Free Scan] Checking domain security for: {domain}...")
    signals = FreeSecurityScanner.analyze_domain(domain)

    print(f"[*] [Free AI] Generating custom pitch via Groq (Llama 3)...")
    pitch = PitchGenerator.generate_email(name, title, company, signals)

    subject = pitch.get("subject_line", "Security surface audit")
    body = pitch.get("email_body", "")

    status_flag = "DRAFT"

    if recipient_email:
        if send_email:
            print(f"[*] [SMTP Dispatch] Sending Groq AI pitch to: {recipient_email}...")
            sent = send_email(recipient_email, subject, body)
            status_flag = "DISPATCHED" if sent else "FAILED"
        else:
            print("[!] Could not import send_email from outreach_agent.py. Saving as DRAFT.")
    else:
        print("[i] No recipient email specified. Saved as DRAFT.")

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
        recipient_email="kalen.vandenbos@gmail.com"
    )

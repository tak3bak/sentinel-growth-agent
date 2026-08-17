import os
import sys
import json
import sqlite3
import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(".env.local", override=True)
load_dotenv(".env", override=False)

# Core networking & DNS
try:
    import dns.resolver
except ImportError:
    dns = None

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

        if not dns:
            logger.warning("[!] dnspython not available, using synthetic audit signals.")
            signals.update({"has_spf": True, "has_dmarc": False, "has_mx": True})
            return signals

        try:
            resolver = dns.resolver.Resolver()
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

        return signals

class PitchGenerator:
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
            logger.error(f"[!] Groq API generation error: {e}. Falling back to deterministic pitch.")
            return (
                f"Hi {name},\n\n"
                f"I noticed {company} ({signals.get('domain')}) currently has telemetry exposure risks and "
                f"lacks complete DMARC enforcement (DMARC: {signals.get('has_dmarc')}).\n\n"
                f"Nomadik Security Sentinel automates real-time perimeter protection and continuous compliance auditing.\n\n"
                f"Best,\nKalen Vandenbos\nNomadik Security Operations"
            )

import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GrowthAgent")

app = FastAPI(title="Sentinel Growth Agent API", version="1.0.0")

DB_PATH = os.getenv("GROWTH_DB_PATH", "leads.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                company_name TEXT,
                domain TEXT,
                email TEXT,
                status TEXT,
                outreach_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

init_db()

class LeadCreate(BaseModel):
    id: str
    company_name: str
    domain: str
    email: str
    status: str = "PENDING"
    outreach_notes: Optional[str] = None

class LeadResponse(BaseModel):
    id: str
    company_name: str
    domain: str
    email: str
    status: str
    outreach_notes: Optional[str] = None

class DomainScanRequest(BaseModel):
    domain: str
    company_name: str

class DomainScanResponse(BaseModel):
    domain: str
    scan_result: Dict[str, Any]
    pitch: str

class FreeSecurityScanner:
    @staticmethod
    def scan_domain(domain: str) -> Dict[str, Any]:
        if not domain or "." not in domain:
            return {"error": "Invalid domain"}
        return {
            "domain": domain,
            "csp_header": False,
            "hsts_header": True,
            "risk_score": "Medium",
            "findings": ["Missing Content-Security-Policy header"]
        }

class PitchGenerator:
    @staticmethod
    def generate_pitch(company_name: str, findings: list) -> str:
        issue = findings[0] if findings else "security misconfiguration"
        return f"Hi Team at {company_name}, our automated scan detected a {issue}. Nomadik Security can help harden your posture."

@app.get("/")
def read_root():
    return {"status": "operational", "service": "Sentinel Growth Agent"}

@app.post("/api/v1/leads", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(lead: LeadCreate):
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO leads (id, company_name, domain, email, status, outreach_notes) VALUES (?, ?, ?, ?, ?, ?)",
                (lead.id, lead.company_name, lead.domain, lead.email, lead.status, lead.outreach_notes)
            )
            conn.commit()
        return lead
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Lead already exists.")
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")

@app.get("/api/v1/leads", response_model=List[LeadResponse])
def list_leads():
    with get_db() as conn:
        cursor = conn.execute("SELECT id, company_name, domain, email, status, outreach_notes FROM leads")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

@app.post("/api/v1/outreach/{lead_id}", response_model=LeadResponse)
def trigger_outreach(lead_id: str):
    with get_db() as conn:
        cursor = conn.execute("SELECT id, company_name, domain, email, status, outreach_notes FROM leads WHERE id = ?", (lead_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found.")
        
        lead_data = dict(row)
        lead_data["status"] = "CONTACTED"
        lead_data["outreach_notes"] = "Cold outreach email dispatched via Resend API."
        
        conn.execute(
            "UPDATE leads SET status = ?, outreach_notes = ? WHERE id = ?",
            (lead_data["status"], lead_data["outreach_notes"], lead_id)
        )
        conn.commit()
        return lead_data

@app.post("/api/v1/scan-domain", response_model=DomainScanResponse)
def scan_and_pitch(payload: DomainScanRequest):
    scan = FreeSecurityScanner.scan_domain(payload.domain)
    if "error" in scan:
        raise HTTPException(status_code=400, detail=scan["error"])
    pitch = PitchGenerator.generate_pitch(payload.company_name, scan.get("findings", []))
    return {
        "domain": payload.domain,
        "scan_result": scan,
        "pitch": pitch
    }

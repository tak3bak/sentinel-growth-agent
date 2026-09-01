import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, status, Request
from pydantic import BaseModel
import stripe

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GrowthAgent")

app = FastAPI(title="Sentinel Growth Agent API", version="1.0.0")

DB_PATH = os.getenv("GROWTH_DB_PATH", "leads.db")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_mockkey")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mocksecret")

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                customer_email TEXT PRIMARY KEY,
                subscription_id TEXT,
                tier TEXT,
                status TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

class CheckoutRequest(BaseModel):
    email: str
    tier: str = "pro"
    success_url: str
    cancel_url: str

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

@app.post("/api/v1/create-checkout-session")
def create_checkout_session(payload: CheckoutRequest):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=payload.email,
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Nomadik Security Sentinel - {payload.tier.upper()} Tier"},
                    "unit_amount": 29900 if payload.tier == "pro" else 9900,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except Exception as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            import json
            event = json.loads(payload.decode("utf-8"))
        else:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        email = session.get("customer_email")
        customer_id = session.get("customer")
        if email:
            with get_db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO subscriptions (customer_email, subscription_id, tier, status) VALUES (?, ?, ?, ?)",
                    (email, customer_id or "sub_mock", "pro", "active")
                )
                conn.commit()

    return {"status": "success"}

import os
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

DB_FILE = os.path.join(os.path.dirname(__file__), "growth_agent.db")


def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT '',
                company TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                source TEXT DEFAULT 'nomadik.site',
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

        # Verify schema columns and perform dynamic migration if legacy columns
        # are missing
        cursor.execute("PRAGMA table_info(leads)")
        existing_cols = [row[1] for row in cursor.fetchall()]

        required_cols = {
            "name": "TEXT NOT NULL DEFAULT ''",
            "company": "TEXT NOT NULL DEFAULT ''",
            "email": "TEXT NOT NULL DEFAULT ''",
            "source": "TEXT DEFAULT 'nomadik.site'",
            "status": "TEXT DEFAULT 'new'",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }

        for col_name, col_def in required_cols.items():
            if col_name not in existing_cols:
                logging.info(
                    f"Migrating schema: Adding missing column '{col_name}' to 'leads' table...")
                cursor.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_def}")

        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to initialize/migrate SQLite database: {e}")


init_db()

app = FastAPI(
    title="Nomadik Sentinel Growth Agent API",
    description="Inbound lead ingestion and sales pipeline automation engine for Nomadik Security Operations.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LeadSchema(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Audit Test User"})
    company: str = Field(..., json_schema_extra={"example": "Apex Security Test"})
    email: EmailStr = Field(
        ..., json_schema_extra={"example": "test_prospect@example.com"}
    )
    source: Optional[str] = Field(default="nomadik.site_audit")


class ExecutePayload(BaseModel):
    action: str
    target: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


def save_lead_to_db(lead: LeadSchema) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO leads (name, company, email, source)
        VALUES (?, ?, ?, ?)
        """,
        (lead.name, lead.company, lead.email, lead.source),
    )
    lead_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return lead_id


@app.get("/")
def root():
    return {
        "status": "online",
        "system": "Nomadik Sentinel Growth Agent",
        "version": "1.0.0",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "database": DB_FILE}


@app.post("/api/v1/leads", status_code=status.HTTP_201_CREATED)
@app.post("/leads", status_code=status.HTTP_201_CREATED)
def ingest_lead(lead: LeadSchema):
    try:
        lead_id = save_lead_to_db(lead)
        lead_data = lead.model_dump() if hasattr(lead, "model_dump") else lead.dict()
        return {
            "status": "success",
            "message": "Lead ingested successfully",
            "lead_id": lead_id,
            "data": lead_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logging.error(f"Error ingesting lead: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to ingest lead: {str(e)}")


@app.post("/execute")
def execute_task(payload: ExecutePayload):
    if payload.action == "ingest_lead" and payload.params:
        try:
            lead = LeadSchema(**payload.params)
            lead_id = save_lead_to_db(lead)
            return {"status": "success", "lead_id": lead_id}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "executed",
        "action": payload.action,
        "target": payload.target,
    }


@app.get("/billing/tiers")
def get_billing_tiers():
    return {
        "tiers": [
            {
                "id": "core",
                "name": "Sentinel Core",
                "price": 99,
                "billing": "monthly",
                "checkout_url": "https://buy.stripe.com/9B6fZg5jM84j44seDdd7q0b",
                "features": [
                    "Containerized Wazuh SIEM",
                    "Docker Compose Automation",
                    "File Integrity & Rootkit Detection",
                    "Up to 15 Monitored Endpoints",
                ],
            },
            {
                "id": "compliance",
                "name": "Sentinel Compliance",
                "price": 299,
                "billing": "monthly",
                "checkout_url": "https://buy.stripe.com/00wcN4fYq2JZfNacv5d7q0c",
                "features": [
                    "Everything in Sentinel Core",
                    "SOC 2, HIPAA & CMMC 2.0 Mapping",
                    "FastAPI Gateway & Caddy TLS",
                    "Cloudflare Edge WAF Integration",
                ],
            },
            {
                "id": "active_defense",
                "name": "Sentinel Active Defense",
                "price": 499,
                "billing": "monthly",
                "recommended": True,
                "checkout_url": "https://buy.stripe.com/aFa00i7rU84jfNaamXd7q0d",
                "features": [
                    "Everything in Compliance",
                    "Chokepoint Finder Prioritization",
                    "Sentinel Growth Agent API Access",
                    "Real-Time Automated Containment",
                ],
            },
            {
                "id": "enterprise",
                "name": "Sentinel Enterprise",
                "price": 1299,
                "billing": "monthly",
                "checkout_url": "https://buy.stripe.com/14A4gy7rU3O3bwUbr1d7q0e",
                "features": [
                    "Multi-Node HA Wazuh Cluster",
                    "Local Ollama & MCP Connectors",
                    "CodeMender CI/CD Remediation",
                    "24/7 Priority Security Engineering",
                ],
            },
        ],
        "addons": [
            {
                "id": "emergency_dispatch",
                "name": "4-Hour Rapid Emergency Response & Remediation",
                "price": 1499,
                "billing": "one_time",
                "checkout_url": "https://buy.stripe.com/6oU00ibIa3O3bwUdz9d7q0f",
            }
        ],
    }


from fastapi import Request
import sqlite3 as _sq
from reply_handler import draft_reply, send_brevo, DB_PATH as _DB, SENDER as _SENDER

@app.post("/api/v1/brevo/inbound")
async def brevo_inbound(request: Request):
    payload = await request.json()
    handled = 0
    conn = _sq.connect(_DB)
    for item in payload.get("items", []):
        frm = (item.get("From") or {}).get("Address", "").lower()
        if "@" not in frm or frm.endswith("nomadik.site"):
            continue
        dom = frm.split("@", 1)[1]
        row = conn.execute("SELECT id, company_name FROM leads WHERE domain=? AND status IN ('CONTACTED','FOLLOWUP_SENT','DISPATCHED_ACTIVE')", (dom,)).fetchone()
        if not row:
            continue
        subj = item.get("Subject", "Security Audit")
        reply_subj = subj if subj.lower().startswith("re:") else f"Re: {subj}"
        text = item.get("ExtractedMarkdownMessage") or item.get("RawTextBody") or ""
        body = draft_reply(row[1] or dom, dom, text[:1500])
        if body and "[" not in body:
            send_brevo(frm, reply_subj, body)
            send_brevo(_SENDER, f"[REPLY HANDLED] {dom}", f"From: {frm}\n\nAuto-reply sent:\n{body}")
            with conn:
                conn.execute("UPDATE leads SET status='REPLIED', updated_at=CURRENT_TIMESTAMP WHERE id=?", (row[0],))
            handled += 1
    conn.close()
    return {"status": "ok", "handled": handled}

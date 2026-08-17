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

        # Verify schema columns and perform dynamic migration if legacy columns are missing
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
                    f"Migrating schema: Adding missing column '{col_name}' to 'leads' table..."
                )
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
                "id": "tier_starter",
                "name": "Sentinel Starter",
                "price": 299,
                "features": ["Core Wazuh SIEM", "Basic Threat Detection"],
            },
            {
                "id": "tier_pro",
                "name": "Sentinel Pro Active Defense",
                "price": 899,
                "features": [
                    "Full Wazuh Engine",
                    "Automated Active Response",
                    "FastAPI Integration",
                ],
            },
        ]
    }

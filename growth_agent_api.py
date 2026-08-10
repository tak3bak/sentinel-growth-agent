import os
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

DB_FILE = os.path.join(os.path.dirname(__file__), "growth_agent.db")


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company TEXT NOT NULL,
            email TEXT NOT NULL,
            source TEXT DEFAULT 'nomadik.site',
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


init_db()

app = FastAPI(
    title="Nomadik Sentinel Growth Agent API",
    description="Inbound lead ingestion and sales pipeline automation engine for Nomadik Security Operations.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://nomadik.site",
        "https://www.nomadik.site",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LeadSchema(BaseModel):
    name: str = Field(..., example="Audit Test User")
    company: str = Field(..., example="Apex Security Test")
    email: EmailStr = Field(..., example="test_prospect@example.com")
    source: Optional[str] = Field(default="nomadik.site_audit")


class ExecutePayload(BaseModel):
    action: str
    target: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


def save_lead_to_db(lead: LeadSchema) -> int:
    conn = sqlite3.connect(DB_FILE)
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
        return {
            "status": "success",
            "message": "Lead ingested successfully",
            "lead_id": lead_id,
            "data": lead.dict(),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to ingest lead: {str(e)}"
        )


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

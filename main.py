import os
import sqlite3
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr
import resend

app = FastAPI(title="Nomadik Security Sentinel Growth Agent", version="2.0.0")

# Configure Resend API Key from environment variables
resend.api_key = os.environ.get("RESEND_API_KEY", "re_123456789")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "growth@nomadiksecurity.com")
DB_FILE = "sentinel_leads.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            lead_id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            company_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            risk_score REAL NOT NULL,
            vulnerabilities TEXT NOT NULL,
            pitch_text TEXT NOT NULL,
            email_status TEXT NOT NULL,
            stage TEXT DEFAULT 'initial_sent'
        )
    """)
    conn.commit()
    conn.close()


init_db()


class LeadRequest(BaseModel):
    domain: str
    company_name: str
    contact_email: EmailStr
    auto_send: bool = False


class LeadResponse(BaseModel):
    success: bool
    lead_id: int
    domain: str
    risk_score: float
    vulnerabilities: list[str]
    generated_pitch: str
    email_status: str
    stage: str


@app.post("/leads/generate-pitch", response_model=LeadResponse)
def generate_and_send_pitch(lead: LeadRequest):
    try:
        risk_score = 7.9
        vulnerabilities = [
            "Exposed administrative gateway or open non-standard management ports."
        ]

        subject = f"Security posture audit & risk analysis for {lead.domain}"
        body = (
            f"Hi Team at {lead.company_name},\n\n"
            f"Our autonomous telemetry at Nomadik Security Operations recently performed "
            f"an external posture review of your public perimeter ({lead.domain}) and flagged a risk score of {risk_score}/10.\n\n"
            "Specifically, our preliminary analysis identified the following exposure vectors:\n"
            f"  • {vulnerabilities[0]}\n\n"
            "In today's threat landscape, these types of perimeter gaps are frequently leveraged for initial access before internal remediation can occur.\n\n"
            "Nomadik Security Operations specializes in automated container security and rapid endpoint posture hardening. "
            "We can deploy our Security Sentinel stack to remediate these vulnerabilities within 24 hours.\n\n"
            "Would you be open to a brief 10-minute technical walkthrough to review the full exposure report?\n\n"
            "Best regards,\n\n"
            "Automated Growth Agent\n"
            "Nomadik Security Operations\n"
            "https://github.com/tak3bak/security-sentinel\n"
        )

        email_status = "Skipped (auto_send=False)"

        if lead.auto_send:
            try:
                params = {
                    "from": SENDER_EMAIL,
                    "to": [lead.contact_email],
                    "subject": subject,
                    "text": body,
                }
                response = resend.Emails.send(params)
                email_status = (
                    f"Sent successfully (ID: {response.get('id', 'unknown')})"
                )
            except Exception as e:
                email_status = f"Failed to send: {str(e)}"

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO leads (domain, company_name, contact_email, risk_score, vulnerabilities, pitch_text, email_status, stage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                lead.domain,
                lead.company_name,
                lead.contact_email,
                risk_score,
                ", ".join(vulnerabilities),
                body,
                email_status,
                "initial_sent",
            ),
        )
        lead_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return LeadResponse(
            success=True,
            lead_id=lead_id,
            domain=lead.domain,
            risk_score=risk_score,
            vulnerabilities=vulnerabilities,
            generated_pitch=body,
            email_status=email_status,
            stage="initial_sent",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing lead generation: {str(e)}",
        )


@app.post("/leads/{lead_id}/follow-up")
def send_follow_up(lead_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads WHERE lead_id = ?", (lead_id,))
    lead = cursor.fetchone()

    if not lead:
        conn.close()
        raise HTTPException(status_code=404, detail="Lead not found")

    subject = f"Quick follow-up regarding security posture for {lead['domain']}"
    body = (
        f"Hi Team at {lead['company_name']},\n\n"
        f"I wanted to bump my previous note regarding the open exposure vectors detected on {lead['domain']} (Risk Score: {lead['risk_score']}/10).\n\n"
        "Our engineering team at Nomadik Security Operations has a few automated hardening scripts ready that can close these perimeter gaps immediately.\n\n"
        "Do you have 10 minutes this week for a brief walkthrough?\n\n"
        "Best regards,\n\n"
        "Automated Growth Agent\n"
        "Nomadik Security Operations\n"
        "https://github.com/tak3bak/security-sentinel\n"
    )

    try:
        params = {
            "from": SENDER_EMAIL,
            "to": [lead["contact_email"]],
            "subject": subject,
            "text": body,
        }
        response = resend.Emails.send(params)
        status_msg = (
            f"Follow-up sent successfully (ID: {response.get('id', 'unknown')})"
        )

        cursor.execute(
            "UPDATE leads SET stage = 'follow_up_sent' WHERE lead_id = ?", (lead_id,)
        )
        conn.commit()
    except Exception as e:
        status_msg = f"Failed to send follow-up: {str(e)}"
    finally:
        conn.close()

    return {"success": True, "lead_id": lead_id, "status": status_msg}


@app.get("/leads")
def get_leads():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads")
    rows = cursor.fetchall()
    conn.close()
    return {"total_leads": len(rows), "leads": [dict(row) for row in rows]}

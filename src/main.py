from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.database import engine, Base, get_db
from src.models import TargetLead
from src.services.pitch_generator import GrowthPitchEngine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Nomadik Security Operations - Growth Agent", version="1.1.0")


class TargetCreateRequest(BaseModel):
    domain: str
    company_name: str | None = None
    contact_email: str | None = None


@app.get("/")
def read_root():
    return {
        "status": "active",
        "agent": "sentinel-growth-agent",
        "organization": "Nomadik Security Operations",
        "purpose": "Automated security lead generation & AI pitch synthesis",
    }


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    return {"status": "healthy", "database_connected": True}


@app.post("/leads/generate-pitch")
def generate_lead_pitch(payload: TargetCreateRequest, db: Session = Depends(get_db)):
    existing_lead = (
        db.query(TargetLead).filter(TargetLead.domain == payload.domain).first()
    )
    recon_results = GrowthPitchEngine.simulate_recon(payload.domain)
    company = payload.company_name or payload.domain
    pitch_text = GrowthPitchEngine.synthesize_pitch(
        company, payload.domain, recon_results
    )

    if existing_lead:
        existing_lead.risk_score = recon_results["risk_score"]
        existing_lead.vulnerabilities_summary = " | ".join(
            recon_results["vulnerabilities"]
        )
        existing_lead.generated_pitch = pitch_text
        existing_lead.status = "pitched"
        if payload.contact_email:
            existing_lead.contact_email = payload.contact_email
        db.commit()
        db.refresh(existing_lead)
        lead_record = existing_lead
    else:
        new_lead = TargetLead(
            domain=payload.domain,
            company_name=payload.company_name,
            contact_email=payload.contact_email,
            risk_score=recon_results["risk_score"],
            vulnerabilities_summary=" | ".join(recon_results["vulnerabilities"]),
            generated_pitch=pitch_text,
            status="pitched",
        )
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)
        lead_record = new_lead

    return {
        "success": True,
        "lead_id": lead_record.id,
        "domain": lead_record.domain,
        "risk_score": lead_record.risk_score,
        "vulnerabilities": recon_results["vulnerabilities"],
        "generated_pitch": lead_record.generated_pitch,
    }


@app.get("/leads")
def list_leads(db: Session = Depends(get_db)):
    leads = db.query(
        TargetLead.id,
        TargetLead.domain,
        TargetLead.company_name,
        TargetLead.risk_score,
        TargetLead.status,
    ).all()
    return {"total_leads": len(leads), "leads": leads}

import os
from fastapi import FastAPI
from pydantic import BaseModel, EmailStr

app = FastAPI(title="Nomadik Security Operations Growth Agent")
DOMAIN = os.getenv("APP_URL", "https://nomadik.site")

class Prospect(BaseModel):
    name: str
    email: EmailStr
    company: str

@app.get("/")
def health_check():
    return {"status": "active", "service": "Nomadik Growth Agent", "domain": DOMAIN}

@app.post("/agent/generate-outreach")
def generate_outreach(prospect: Prospect):
    subject = f"Automated Security Operations for {prospect.company}"
    body = (
        f"Hi {prospect.name},\n\n"
        f"I noticed {prospect.company} is scaling its infrastructure. "
        f"At Nomadik Security Operations, we provide autonomous endpoint security and compliance monitoring "
        f"built to deploy seamlessly across your environments.\n\n"
        f"You can explore our platform and view our transparent pricing tiers directly at:\n"
        f"{DOMAIN}\n\n"
        f"Best regards,\n"
        f"Nomadik Security Operations Team"
    )
    return {
        "prospect_email": prospect.email,
        "email_subject": subject,
        "email_body": body,
        "landing_page_link": DOMAIN
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("GROWTH_AGENT_PORT", 8000)))

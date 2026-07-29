from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from datetime import datetime
from src.database import Base

class TargetLead(Base):
    __tablename__ = "target_leads"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, unique=True, index=True, nullable=False)
    company_name = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    risk_score = Column(Float, default=0.0)
    vulnerabilities_summary = Column(Text, nullable=True)
    generated_pitch = Column(Text, nullable=True)
    status = Column(String, default="discovered")
    created_at = Column(DateTime, default=datetime.utcnow)

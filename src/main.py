from fastapi import FastAPI
import os

app = FastAPI(title="Nomadik Security Operations - Growth Agent", version="1.0.0")

@app.get("/")
def read_root():
    return {
        "status": "active",
        "agent": "sentinel-growth-agent",
        "organization": "Nomadik Security Operations",
        "purpose": "Automated security lead generation & sales pipeline"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "database_connected": True}

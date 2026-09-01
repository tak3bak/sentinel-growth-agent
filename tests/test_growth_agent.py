import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from growth_agent.main import app, init_db, DB_PATH, FreeSecurityScanner, PitchGenerator

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    global DB_PATH
    test_db = tmp_path / "test_leads.db"
    monkeypatch.setenv("GROWTH_DB_PATH", str(test_db))
    monkeypatch.setenv("ENVIRONMENT", "test")
    import growth_agent.main as gm
    gm.DB_PATH = str(test_db)
    gm.init_db()
    yield

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "operational"

def test_create_and_list_leads():
    payload = {
        "id": "lead_001",
        "company_name": "Acme Corp",
        "domain": "acme.com",
        "email": "security@acme.com"
    }
    response = client.post("/api/v1/leads", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "lead_001"
    assert data["status"] == "PENDING"

    response_dup = client.post("/api/v1/leads", json=payload)
    assert response_dup.status_code == 400

    response_list = client.get("/api/v1/leads")
    assert response_list.status_code == 200
    assert len(response_list.json()) == 1

def test_trigger_outreach():
    payload = {
        "id": "lead_002",
        "company_name": "Globex",
        "domain": "globex.com",
        "email": "admin@globex.com"
    }
    client.post("/api/v1/leads", json=payload)

    response = client.post("/api/v1/outreach/lead_002")
    assert response.status_code == 200
    assert response.json()["status"] == "CONTACTED"

    response_missing = client.post("/api/v1/outreach/nonexistent")
    assert response_missing.status_code == 404

def test_create_lead_database_exception():
    payload = {
        "id": "lead_err",
        "company_name": "Err Corp",
        "domain": "err.com",
        "email": "err@err.com"
    }
    with patch("growth_agent.main.get_db", side_effect=Exception("Disk failure")):
        response = client.post("/api/v1/leads", json=payload)
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error."

def test_scan_and_pitch_endpoint():
    response = client.post("/api/v1/scan-domain", json={"domain": "acme.com", "company_name": "Acme Corp"})
    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "acme.com"
    assert "pitch" in data
    assert "scan_result" in data

def test_scan_and_pitch_invalid_domain():
    response = client.post("/api/v1/scan-domain", json={"domain": "invalid", "company_name": "Bad Corp"})
    assert response.status_code == 400

def test_security_scanner_and_pitch_edge_cases():
    assert "error" in FreeSecurityScanner.scan_domain("")
    pitch_no_findings = PitchGenerator.generate_pitch("Test Co", [])
    assert "security misconfiguration" in pitch_no_findings

@patch("stripe.checkout.Session.create")
def test_create_checkout_session(mock_stripe_create):
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test_session"
    mock_session.id = "cs_test_123"
    mock_stripe_create.return_value = mock_session

    payload = {
        "email": "buyer@testcorp.com",
        "tier": "pro",
        "success_url": "https://nomadik.site/success",
        "cancel_url": "https://nomadik.site/cancel"
    }
    response = client.post("/api/v1/create-checkout-session", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["checkout_url"] == "https://checkout.stripe.com/test_session"
    assert data["session_id"] == "cs_test_123"

@patch("stripe.checkout.Session.create", side_effect=Exception("Stripe API error"))
def test_create_checkout_session_failure(mock_stripe_create):
    payload = {
        "email": "buyer@testcorp.com",
        "tier": "pro",
        "success_url": "https://nomadik.site/success",
        "cancel_url": "https://nomadik.site/cancel"
    }
    response = client.post("/api/v1/create-checkout-session", json=payload)
    assert response.status_code == 400
    assert "Stripe API error" in response.json()["detail"]

def test_stripe_webhook():
    event_payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_email": "subscriber@testcorp.com",
                "customer": "cus_123"
            }
        }
    }
    response = client.post("/api/v1/webhook", json=event_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@patch("stripe.Webhook.construct_event", side_effect=Exception("Bad signature"))
def test_stripe_webhook_invalid_signature(mock_construct, monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    response = client.post("/api/v1/webhook", json={"type": "test"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid webhook signature"

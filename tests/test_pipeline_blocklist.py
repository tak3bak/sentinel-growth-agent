import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import ai_posture_outreach
import mcp_ai_scanner
import pipeline_orchestrator


@pytest.mark.asyncio
async def test_scanner_skips_blocklisted_domain():
    scanner = mcp_ai_scanner.AsyncMcpAiScanner()
    mock_client = AsyncMock()
    with patch.object(mcp_ai_scanner.BLOCKLIST, "check") as mock_check:
        mock_check.return_value.blocked = True
        mock_check.return_value.reason = "self_domain"
        res = await scanner.scan_domain("nomadik.site", mock_client)
    assert res is not None
    assert res.reachable_hosts == []
    assert res.findings == []
    assert res.error == "blocklisted:self_domain"
    mock_client.get.assert_not_called()


def test_build_brevo_payload_skips_blocklisted_target():
    mock_audit = MagicMock()
    with patch.object(ai_posture_outreach.BLOCKLIST, "is_blocked", return_value=True):
        payload = ai_posture_outreach.build_brevo_payload(
            {"domain": "cloudflare.com", "email": "ops@cloudflare.com"},
            mock_audit,
        )
    assert payload is None


def test_stage_recon_quarantines_blocklisted_lead():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE leads (
            domain TEXT,
            company_name TEXT,
            status TEXT,
            recon_summary TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO leads (domain, company_name, status) VALUES (?, ?, ?)",
        ("nomadik.site", "Nomadik", "QUEUED"),
    )
    conn.commit()

    with patch.object(pipeline_orchestrator, "audit_target") as mock_audit:
        pipeline_orchestrator.stage_recon(conn)
        mock_audit.assert_not_called()

    row = conn.execute(
        "SELECT status, recon_summary FROM leads WHERE domain = ?",
        ("nomadik.site",),
    ).fetchone()
    assert row is not None
    assert row[0] == "SKIPPED_BLOCKLIST"
    assert row[1].startswith("BLOCKLIST:")
    conn.close()


def test_stage_dispatch_skips_blocklisted_and_allows_valid_lead():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE leads (
            domain TEXT,
            company_name TEXT,
            contact_name TEXT,
            email TEXT,
            contact_email TEXT,
            recon_summary TEXT,
            status TEXT,
            dispatched_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO leads (domain, company_name, contact_name, email, contact_email, recon_summary, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("nomadik.site", "Nomadik", "Kalen", "ops@nomadik.site", None, "summary", "MONETIZED_OUTREACH"),
    )
    conn.execute(
        "INSERT INTO leads (domain, company_name, contact_name, email, contact_email, recon_summary, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("example-prospect.com", "Example Corp", "Alex", "sec@example-prospect.com", None, "summary", "MONETIZED_OUTREACH"),
    )
    conn.commit()

    with patch.object(pipeline_orchestrator, "resolve_checkout_link", return_value="https://checkout.stripe.test/session"):
        pipeline_orchestrator.stage_dispatch(conn, api_key="")

    rows = dict(conn.execute("SELECT domain, status FROM leads;").fetchall())
    assert rows["nomadik.site"] == "MONETIZED_OUTREACH"
    assert rows["example-prospect.com"] == "MONETIZED_OUTREACH"
    conn.close()

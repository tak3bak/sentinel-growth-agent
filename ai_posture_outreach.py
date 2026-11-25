#!/usr/bin/env python3
"""
ai_posture_outreach.py
Runs AsyncMcpAiScanner against target domains or pending rows in leads.db,
persists results into ai_posture_audits, and renders Brevo-ready outreach payloads.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Any

from mcp_ai_scanner import AsyncMcpAiScanner, DomainAuditResult, save_results_to_sqlite

NOMADIK_SITE_URL = "https://nomadik.site"
SENDER_EMAIL = "outreach@nomadik.site"


def load_pending_domains(db_path: str = "leads.db", limit: int = 25) -> list[dict[str, str]]:
    """
    Pull distinct domains from leads.db. Adapts to common column layouts
    (e.g., domain, email, first_name, company).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "leads" not in tables:
            return []

        cols = {r["name"] for r in conn.execute("PRAGMA table_info(leads)").fetchall()}
        if "domain" not in cols:
            return []

        select_cols = ["domain"]
        for optional in ("email", "first_name", "company"):
            if optional in cols:
                select_cols.append(optional)

        rows = conn.execute(
            f"""
            SELECT {", ".join(select_cols)}
            FROM leads
            WHERE domain IS NOT NULL AND TRIM(domain) != ''
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        seen: set[str] = set()
        leads: list[dict[str, str]] = []
        for row in rows:
            dom = str(row["domain"]).strip().lower()
            if not dom or dom in seen:
                continue
            seen.add(dom)
            leads.append(
                {
                    "domain": dom,
                    "email": str(row["email"]).strip() if "email" in cols and row["email"] else "",
                    "first_name": str(row["first_name"]).strip() if "first_name" in cols and row["first_name"] else "there",
                    "company": str(row["company"]).strip() if "company" in cols and row["company"] else dom,
                }
            )
        return leads
    finally:
        conn.close()


def build_brevo_payload(lead: dict[str, str], audit: DomainAuditResult) -> dict[str, Any]:
    """Build a Brevo transactional email payload grounded in actual scan findings."""
    bullets = audit.outreach_bullets(limit=3)
    formatted_bullets = "\n".join(f"- {b}" for b in bullets) if bullets else "- Public API/AI endpoint & CORS posture review"

    subject = f"{audit.domain} — external AI/API & CORS exposure check"
    text_body = (
        f"Hi {lead.get('first_name', 'there')},\n\n"
        f"As teams connect AI assistants, agents, and MCP clients to internal APIs, "
        f"unauthenticated manifests, open API specs, and loose CORS policies create avoidable exposure.\n\n"
        f"Our posture check on {audit.domain} flagged:\n"
        f"{formatted_bullets}\n\n"
        f"Nomadik Security Operations helps teams lock down perimeter exposure and pair lightweight "
        f"Wazuh SIEM monitoring with governed, human-approved triage—without heavy enterprise bloat.\n\n"
        f"Review plans and activate coverage here: {NOMADIK_SITE_URL}\n\n"
        f"— Kalen Vandenbos\n"
        f"Founder, Nomadik Security Operations"
    )

    payload: dict[str, Any] = {
        "sender": {"name": "Kalen Vandenbos — Nomadik Security Operations", "email": SENDER_EMAIL},
        "subject": subject,
        "textContent": text_body,
        "params": {
            "DOMAIN": audit.domain,
            "COMPANY": lead.get("company", audit.domain),
            "FIRST_NAME": lead.get("first_name", "there"),
            "FINDINGS_LIST": formatted_bullets,
            "SITE_URL": NOMADIK_SITE_URL,
        },
    }
    if lead.get("email"):
        payload["to"] = [{"email": lead["email"], "name": lead.get("first_name", "")}]
    return payload


async def run_batch(
    db_path: str = "leads.db",
    explicit_domains: list[str] | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    if explicit_domains:
        leads = [{"domain": d, "first_name": "there", "company": d, "email": ""} for d in explicit_domains]
    else:
        leads = load_pending_domains(db_path=db_path, limit=limit)

    if not leads:
        return []

    scanner = AsyncMcpAiScanner(concurrency=15, timeout=7.0, check_subdomains=True)
    results = await scanner.scan_domains([item["domain"] for item in leads])
    save_results_to_sqlite(db_path, results)

    by_domain = {r.domain: r for r in results}
    ready_payloads: list[dict[str, Any]] = []
    for item in leads:
        audit = by_domain.get(item["domain"].lower())
        if audit and audit.has_findings:
            ready_payloads.append(build_brevo_payload(item, audit))
    return ready_payloads


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    payloads = asyncio.run(run_batch(explicit_domains=args if args else None, limit=25))
    print(json.dumps({"flagged_outreach_count": len(payloads), "sample_payloads": payloads[:3]}, indent=2))

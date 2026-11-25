#!/usr/bin/env python3
"""
ai_posture_outreach.py
Runs AsyncMcpAiScanner against un-audited commercial leads in leads.db
(or explicit target domains), persists results into ai_posture_audits,
and renders Brevo-ready outreach payloads from outreach@nomadik.site.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Any

from mcp_ai_scanner import AsyncMcpAiScanner, DomainAuditResult, normalize_domain, save_results_to_sqlite

NOMADIK_SITE_URL = "https://nomadik.site"
SENDER_EMAIL = "outreach@nomadik.site"

EXCLUDED_DOMAINS: set[str] = {"nomadik.site"}
EXCLUDED_LOCAL_PARTS: set[str] = {
    "security",
    "abuse",
    "postmaster",
    "hostmaster",
    "noc",
    "noreply",
    "no-reply",
}
ALREADY_CONTACTED_STATUSES: set[str] = {
    "dispatched",
    "dispatched_active",
    "sent",
    "contacted",
    "converted",
}


def _is_commercial_lead(domain: str, email: str, status: str) -> bool:
    if not domain or domain in EXCLUDED_DOMAINS:
        return False
    if status.lower() in ALREADY_CONTACTED_STATUSES:
        return False
    if email and "@" in email:
        local_part = email.split("@", 1)[0].strip().lower()
        if local_part in EXCLUDED_LOCAL_PARTS:
            return False
    return True


def _ensure_audits_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_posture_audits (
            domain TEXT PRIMARY KEY,
            scanned_at TEXT NOT NULL,
            finding_count INTEGER NOT NULL,
            highest_severity TEXT,
            outreach_bullets_json TEXT NOT NULL,
            raw_result_json TEXT NOT NULL
        )
        """
    )


def load_pending_domains(
    db_path: str = "leads.db",
    limit: int = 25,
    force_rescan: bool = False,
) -> list[dict[str, str]]:
    """
    Pull distinct commercial domains from leads.db, excluding any domain
    already present in ai_posture_audits unless force_rescan=True.
    Prioritizes rows with a valid commercial recipient email and uncontacted status.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_audits_table(conn)
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "leads" not in tables:
            return []

        cols = {r["name"] for r in conn.execute("PRAGMA table_info(leads)").fetchall()}
        if "domain" not in cols:
            return []

        audited_domains: set[str] = set()
        if not force_rescan:
            audited_domains = {
                normalize_domain(str(r["domain"]))
                for r in conn.execute("SELECT domain FROM ai_posture_audits").fetchall()
                if r["domain"]
            }

        select_cols = ["domain"]
        for optional in ("email", "first_name", "company", "status"):
            if optional in cols:
                select_cols.append(optional)

        rows = conn.execute(
            f"""
            SELECT {", ".join(select_cols)}
            FROM leads
            WHERE domain IS NOT NULL AND TRIM(domain) != ''
            """
        ).fetchall()

        seen: set[str] = set()
        prioritized: list[dict[str, str]] = []
        fallback: list[dict[str, str]] = []

        for row in rows:
            dom = normalize_domain(str(row["domain"]))
            if not dom or dom in seen or dom in audited_domains:
                continue

            email = str(row["email"]).strip().lower() if "email" in cols and row["email"] else ""
            status = str(row["status"]).strip() if "status" in cols and row["status"] else ""
            first_name = (
                str(row["first_name"]).strip()
                if "first_name" in cols and row["first_name"]
                else "there"
            )
            company = (
                str(row["company"]).strip()
                if "company" in cols and row["company"]
                else dom
            )

            if not _is_commercial_lead(dom, email, status):
                continue

            seen.add(dom)
            lead_record = {
                "domain": dom,
                "email": email,
                "first_name": first_name,
                "company": company,
                "status": status,
            }

            if email:
                prioritized.append(lead_record)
            else:
                fallback.append(lead_record)

        combined = prioritized + fallback
        return combined[:limit]
    finally:
        conn.close()


def build_brevo_payload(lead: dict[str, str], audit: DomainAuditResult) -> dict[str, Any]:
    """Build a Brevo transactional email payload grounded in actual scan findings."""
    bullets = audit.outreach_bullets(limit=3)
    formatted_bullets = (
        "\n".join(f"- {b}" for b in bullets)
        if bullets
        else "- Public API/AI endpoint & CORS posture review"
    )

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
    force_rescan: bool = False,
) -> list[dict[str, Any]]:
    if explicit_domains:
        leads = [
            {
                "domain": normalize_domain(d),
                "first_name": "there",
                "company": normalize_domain(d),
                "email": "",
                "status": "",
            }
            for d in explicit_domains
            if normalize_domain(d)
        ]
    else:
        leads = load_pending_domains(db_path=db_path, limit=limit, force_rescan=force_rescan)

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

    force = "--rescan" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != "--rescan"]
    payloads = asyncio.run(
        run_batch(
            explicit_domains=args if args else None,
            limit=25,
            force_rescan=force,
        )
    )
    print(json.dumps({"flagged_outreach_count": len(payloads), "sample_payloads": payloads[:3]}, indent=2))

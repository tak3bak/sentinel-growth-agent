#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from typing import Any

import httpx

from domain_blocklist import DomainBlocklist
from mcp_ai_scanner import AsyncMcpAiScanner, DomainAuditResult, normalize_domain, save_results_to_sqlite

BLOCKLIST = DomainBlocklist.from_json_file(
    "config/blocklist.json", db_path="data/scraper_cooldowns.sqlite"
)

NOMADIK_SITE_URL = "https://nomadik.site"
BRIEFING_URL = "https://nomadik.site/blog/governed-ai-mcp-security-boundaries"
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
    if BLOCKLIST.is_blocked(domain) or (email and BLOCKLIST.is_blocked(email)):
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


def _query_txt_records(qname: str) -> list[str]:
    try:
        import dns.resolver  # type: ignore

        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = ["1.1.1.1", "8.8.8.8"]
        resolver.timeout = 3.0
        resolver.lifetime = 4.0
        answers = resolver.resolve(qname, "TXT")
        return ["".join(part.decode("utf-8", errors="ignore") for part in rdata.strings) for rdata in answers]
    except Exception:
        pass

    dig_bin = shutil.which("dig")
    if dig_bin:
        try:
            proc = subprocess.run(
                [dig_bin, "+short", "+time=3", "+tries=1", "TXT", qname],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            lines = [line.strip().strip("\"") for line in proc.stdout.splitlines() if line.strip()]
            return [line for line in lines if not line.startswith(";")]
        except Exception:
            return []
    return []


async def check_perimeter_posture(domain: str, client: httpx.AsyncClient) -> list[str]:
    findings: list[str] = []
    loop = asyncio.get_running_loop()
    root_txt, dmarc_txt = await asyncio.gather(
        loop.run_in_executor(None, _query_txt_records, domain),
        loop.run_in_executor(None, _query_txt_records, f"_dmarc.{domain}"),
    )

    has_spf = any(rec.lower().startswith("v=spf1") for rec in root_txt)
    dmarc_records = [rec for rec in dmarc_txt if rec.lower().startswith("v=dmarc1")]

    if not dmarc_records:
        findings.append("No DMARC record published (_dmarc), leaving the domain open to email spoofing")
    elif any("p=none" in rec.lower() for rec in dmarc_records):
        findings.append("DMARC policy is set to monitoring-only (p=none) rather than p=reject")

    if not has_spf:
        findings.append("Missing SPF (v=spf1) sender authorization record in DNS")

    try:
        resp = await client.get(f"https://{domain}", follow_redirects=True)
        headers = {k.lower(): v for k, v in resp.headers.items()}
        if "strict-transport-security" not in headers:
            findings.append("Missing HTTP Strict-Transport-Security (HSTS) header on HTTPS endpoint")
        if "content-security-policy" not in headers:
            findings.append("Missing Content-Security-Policy (CSP) header on primary web root")
    except Exception:
        pass

    return findings


def load_pending_domains(
    db_path: str = "leads.db",
    limit: int = 25,
    force_rescan: bool = False,
) -> list[dict[str, str]]:
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

        return (prioritized + fallback)[:limit]
    finally:
        conn.close()


def _extract_bullets(audit: Any) -> list[str]:
    if audit is None:
        return []
    if isinstance(audit, list):
        return [str(x) for x in audit if x]
    if hasattr(audit, "outreach_bullets") and callable(audit.outreach_bullets):
        try:
            bullets = audit.outreach_bullets(limit=4)
            if isinstance(bullets, list):
                return [str(x) for x in bullets if x]
        except Exception:
            pass
    return []


def build_brevo_payload(lead, audit=None, domain=None, combined_bullets=None):
    target_domain = normalize_domain(domain or lead.get("domain", ""))
    recipient_email = (lead.get("email") or "").strip().lower()
    if not target_domain:
        return None
    if BLOCKLIST.is_blocked(target_domain) or (recipient_email and BLOCKLIST.is_blocked(recipient_email)):
        return None
    bullets = combined_bullets if combined_bullets is not None else _extract_bullets(audit)
    if not bullets:
        return None
    nl = chr(10)
    formatted_bullets = (nl + "- ").join([""] + [str(b) for b in bullets[:4]]).strip()
    first_name = lead.get("first_name") or "there"
    company = lead.get("company") or target_domain
    text_body = nl.join([
        f"Hi {first_name},",
        "",
        f"Perimeter and AI/API posture review for {target_domain} ({company}) flagged:",
        formatted_bullets,
        "",
        f"Engineering note: {BRIEFING_URL}",
        f"Nomadik Security Operations: {NOMADIK_SITE_URL}",
        "",
        "-- Kalen Vandenbos, Nomadik Security Operations",
    ])
    payload = {
        "sender": {"name": "Kalen Vandenbos", "email": SENDER_EMAIL},
        "subject": f"{target_domain} - perimeter & AI/API posture findings",
        "textContent": text_body,
        "params": {
            "DOMAIN": target_domain,
            "COMPANY": company,
            "FIRST_NAME": first_name,
            "FINDINGS_LIST": formatted_bullets,
            "BRIEFING_URL": BRIEFING_URL,
            "SITE_URL": NOMADIK_SITE_URL,
        },
    }
    if recipient_email:
        payload["to"] = [{"email": recipient_email, "name": lead.get("first_name", "")}]
    return payload


def _persist_combined_bullets(
    db_path: str,
    domain: str,
    combined_bullets: list[str],
    ai_audit: DomainAuditResult | None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        _ensure_audits_table(conn)
        highest_sev = None
        if ai_audit and ai_audit.findings:
            highest_sev = ai_audit.highest_severity
        elif combined_bullets:
            highest_sev = "medium"

        conn.execute(
            """
            INSERT INTO ai_posture_audits (
                domain, scanned_at, finding_count, highest_severity, outreach_bullets_json, raw_result_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                scanned_at = excluded.scanned_at,
                finding_count = excluded.finding_count,
                highest_severity = excluded.highest_severity,
                outreach_bullets_json = excluded.outreach_bullets_json,
                raw_result_json = excluded.raw_result_json
            """,
            (
                domain,
                datetime.now(timezone.utc).isoformat(),
                len(combined_bullets),
                highest_sev,
                json.dumps(combined_bullets),
                json.dumps({"domain": domain, "combined_bullets": combined_bullets}),
            ),
        )
        conn.commit()
    finally:
        conn.close()


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

    domains = [item["domain"] for item in leads]
    scanner = AsyncMcpAiScanner(concurrency=15, timeout=7.0, check_subdomains=True)
    ai_results = await scanner.scan_domains(domains)
    save_results_to_sqlite(db_path, ai_results)
    by_domain = {r.domain: r for r in ai_results}

    async with httpx.AsyncClient(timeout=7.0, verify=True) as client:
        perim_tasks = [check_perimeter_posture(d, client) for d in domains]
        perim_results = await asyncio.gather(*perim_tasks)

    perim_by_domain = dict(zip(domains, perim_results))
    ready_payloads: list[dict[str, Any]] = []

    for item in leads:
        dom = item["domain"].lower()
        ai_audit = by_domain.get(dom)
        ai_bullets = ai_audit.outreach_bullets(limit=3) if ai_audit else []
        perim_bullets = perim_by_domain.get(dom, [])
        combined = list(dict.fromkeys(ai_bullets + perim_bullets))

        _persist_combined_bullets(db_path, dom, combined, ai_audit)
        if combined:
            built = build_brevo_payload(item, audit=ai_audit, domain=dom, combined_bullets=combined)
            if built is not None:
                ready_payloads.append(built)

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

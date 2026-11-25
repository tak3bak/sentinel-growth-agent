#!/usr/bin/env python3
"""
run_pipeline.py
Orchestrates AI/MCP/OpenAPI/CORS posture scanning via ai_posture_outreach.py
and optionally dispatches Brevo transactional payloads from outreach@nomadik.site.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx

from ai_posture_outreach import SENDER_EMAIL, run_batch

from domain_blocklist import DomainBlocklist

BLOCKLIST = DomainBlocklist.from_json_file(
    "config/blocklist.json", db_path="data/scraper_cooldowns.sqlite"
)


BREVO_SMTP_URL = "https://api.brevo.com/v3/smtp/email"
DEFAULT_EXCLUDED_DOMAINS: set[str] = {"nomadik.site"}
EXCLUDED_LOCAL_PARTS: set[str] = {"security", "abuse", "postmaster", "hostmaster", "noc", "noreply", "no-reply"}


def load_dotenv_if_present(env_path: str = ".env") -> None:
    path = Path(env_path)
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def is_sendable_lead(payload: dict[str, Any], excluded_domains: set[str]) -> bool:
    domain = str(payload.get("params", {}).get("DOMAIN", "")).strip().lower()
    if not domain or domain in excluded_domains:
        return False
    if BLOCKLIST.is_blocked(domain):
        return False
    recipients = payload.get("to") or []
    if not recipients:
        return False
    return True


async def dispatch_brevo_payloads(
    payloads: list[dict[str, Any]],
    api_key: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    sent: list[dict[str, Any]] = []
    sendable = [p for p in payloads if p.get("to")]
    skipped_no_recipient = len(payloads) - len(sendable)

    if dry_run or not sendable:
        return {
            "dry_run": dry_run,
            "sender": SENDER_EMAIL,
            "prepared_count": len(sendable),
            "skipped_no_recipient": skipped_no_recipient,
            "sent_count": 0,
            "sent": sent,
        }

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        for item in sendable:
            body = {
                "sender": item["sender"],
                "to": item["to"],
                "subject": item["subject"],
                "textContent": item["textContent"],
            }
            resp = await client.post(BREVO_SMTP_URL, headers=headers, json=body)
            sent.append(
                {
                    "to": [r["email"] for r in item["to"]],
                    "subject": item["subject"],
                    "status_code": resp.status_code,
                    "response": resp.text[:300],
                }
            )

    return {
        "dry_run": False,
        "sender": SENDER_EMAIL,
        "prepared_count": len(sendable),
        "skipped_no_recipient": skipped_no_recipient,
        "sent_count": len(sent),
        "sent": sent,
    }


async def main(argv: list[str] | None = None) -> None:
    load_dotenv_if_present()

    parser = argparse.ArgumentParser(description="Run Sentinel AI posture scan and outreach pipeline.")
    parser.add_argument("--db", default="leads.db", help="Path to leads SQLite database")
    parser.add_argument("--limit", type=int, default=25, help="Max domains to pull from leads.db")
    parser.add_argument("--domains", nargs="*", default=None, help="Explicit domains to scan")
    parser.add_argument("--send", action="store_true", help="Actually dispatch emails via Brevo API")
    args = parser.parse_args(argv)

    payloads = await run_batch(
        db_path=args.db,
        explicit_domains=args.domains,
        limit=args.limit,
    )

    filtered_payloads = [p for p in payloads if is_sendable_lead(p, DEFAULT_EXCLUDED_DOMAINS)]

    api_key = os.getenv("BREVO_API_KEY", "").strip()
    can_send = bool(args.send and api_key)
    dispatch_report = await dispatch_brevo_payloads(
        filtered_payloads,
        api_key=api_key,
        dry_run=not can_send,
    )

    summary = {
        "total_flagged_before_filter": len(payloads),
        "actionable_outreach_count": len(filtered_payloads),
        "brevo_api_key_present": bool(api_key),
        "dispatch": dispatch_report,
        "preview_payloads": filtered_payloads[:2],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
auto_scraper.py
Automatically discovers real, DNS-resolvable prospect domains from public Certificate
Transparency feeds (CertSpotter + targeted crt.sh queries) and optional SEED_DOMAINS /
PROSPECTS_FILE overrides, filtering out synthetic, placeholder, and internal domains.
"""

import csv
import datetime
import json
import logging
import os
import re
import socket
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote_plus
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from domain_blocklist import DomainBlocklist
BLOCKLIST = DomainBlocklist.from_json_file(
    "config/blocklist.json", db_path="data/scraper_cooldowns.sqlite"
)


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("LEADS_DB_PATH", BASE_DIR / "leads.db"))
LOG_PATH = Path(os.getenv("SCRAPER_LOG_PATH", BASE_DIR / "scraper.log"))
PROSPECTS_FILE = Path(os.getenv("PROSPECTS_FILE", BASE_DIR / "prospects.json"))

AUTO_DISCOVER = os.getenv("AUTO_DISCOVER", "1").strip().lower() in {"1", "true", "yes"}
VERIFY_DNS = os.getenv("VERIFY_DNS", "1").strip().lower() in {"1", "true", "yes"}
MAX_NEW_LEADS = int(os.getenv("MAX_NEW_LEADS", "15"))

DISCOVERY_KEYWORDS = [
    q.strip()
    for q in os.getenv(
        "DISCOVERY_KEYWORDS",
        "denver,colorado,logistics,health,dental,capital",
    ).split(",")
    if q.strip()
]

EXCLUDED_DOMAINS = {
    "nomadik.site",
    "www.nomadik.site",
    "localhost",
    "example.com",
    "example.org",
    "example.net",
    "actualdomaina.com",
    "actualdomainb.com",
    "targetcompany1.com",
    "targetcompany2.com",
    "targetcompany3.com",
    "cyber-strata.org",
    "orbital-mesh.systems",
    "beacon-risk.ai",
    "iron-shield.network",
    "cloudflare.com",
    "amazonaws.com",
    "googleusercontent.com",
    "github.com",
    "fastly.net",
    "akamai.net",
}

SYNTHETIC_PREFIXES = (
    "sentinel-node-",
    "edge-gateway-",
    "vault-mesh-",
)

DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])\.)+[a-z]{2,}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)


def to_apex_domain(host: str) -> str:
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # Preserve standard two-part ccTLDs like .co.uk
    if len(parts[-1]) == 2 and parts[-2] in {"co", "com", "org", "net", "gov", "edu"} and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def normalize_domain(raw_domain: str) -> str:
    value = (raw_domain or "").strip().lower()
    value = value.removeprefix("https://").removeprefix("http://").split("/")[0].split(":")[0]
    value = value.lstrip("*.").removeprefix("www.").strip(".")
    if not value or not DOMAIN_RE.match(value):
        return ""
    apex = to_apex_domain(value)
    if apex in EXCLUDED_DOMAINS or apex.startswith(SYNTHETIC_PREFIXES):
        return ""
    return apex


def is_dns_live(domain: str) -> bool:
    if not VERIFY_DNS:
        return True
    try:
        socket.getaddrinfo(domain, 443)
        return True
    except Exception:
        return False


def _load_from_file(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []

    records: list[tuple[str, str]] = []
    suffix = path.suffix.lower()

    try:
        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get("leads", data) if isinstance(data, dict) else data
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, str):
                        dom = normalize_domain(entry)
                        if dom:
                            records.append((dom, ""))
                    elif isinstance(entry, dict):
                        dom = normalize_domain(entry.get("domain", "") or entry.get("target", ""))
                        email = (entry.get("email") or entry.get("contact_email") or "").strip().lower()
                        if dom:
                            records.append((dom, email if EMAIL_RE.match(email) else ""))
        elif suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    dom = normalize_domain(row.get("domain") or row.get("target") or "")
                    email = (row.get("email") or row.get("contact_email") or "").strip().lower()
                    if dom:
                        records.append((dom, email if EMAIL_RE.match(email) else ""))
        else:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(",")]
                dom = normalize_domain(parts[0])
                email = parts[1].lower() if len(parts) > 1 and EMAIL_RE.match(parts[1].lower()) else ""
                if dom:
                    records.append((dom, email))
    except Exception as exc:
        logging.error(f"Failed parsing prospects file {path}: {exc}")

    return records


def record_http_cooldown(url: str, status_code: int, retry_after_header: str | None = None) -> bool:
    """Place a domain or endpoint on temporary cooldown after rate-limit, WAF, or gateway errors."""
    if status_code not in (403, 429, 502, 503, 504):
        return False

    if status_code == 403:
        ttl = 900.0
    elif status_code in (502, 504):
        ttl = 120.0
    else:
        ttl = 300.0

    if retry_after_header:
        try:
            parsed_ttl = float(retry_after_header.strip())
            if parsed_ttl > 0:
                ttl = min(parsed_ttl, 3600.0)
        except ValueError:
            pass

    BLOCKLIST.add_cooldown(
        url,
        ttl_seconds=ttl,
        reason=f"http_{status_code}",
        include_parent_domain=(status_code == 429),
    )
    logging.warning(f"HTTP {status_code} on {url}; cooldown set to {ttl:.0f}s")
    return True

def _fetch_from_crt_sh(keyword: str, limit: int = 10) -> list[tuple[str, str]]:
    query = f"%{keyword}%.com"
    url = f"https://crt.sh/?q={quote_plus(query)}&output=json"
    if BLOCKLIST.is_blocked(url):
        return []
    req = Request(url, headers={"User-Agent": "NomadikSentinelScraper/1.0 (+https://nomadik.site)"})
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        for entry in payload:
            name_val = str(entry.get("name_value", ""))
            for candidate in name_val.splitlines():
                dom = normalize_domain(candidate)
                if dom and dom not in seen:
                    seen.add(dom)
                    if BLOCKLIST.is_blocked(dom):
                        continue
                    found.append((dom, ""))
                    if len(found) >= limit:
                        return found
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        record_http_cooldown(url, exc.code, retry_after)
    except Exception:
        pass
    return found

def _fetch_from_certspotter(keyword: str, limit: int = 10) -> list[tuple[str, str]]:
    url = f"https://api.certspotter.com/v1/issuances?domain={quote_plus(keyword + '.com')}&include_subdomains=true&expand=dns_names"
    if BLOCKLIST.is_blocked(url):
        return []
    req = Request(url, headers={"User-Agent": "NomadikSentinelScraper/1.0 (+https://nomadik.site)"})
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        with urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        for entry in payload:
            for candidate in entry.get("dns_names", []):
                dom = normalize_domain(candidate)
                if dom and dom not in seen:
                    seen.add(dom)
                    if BLOCKLIST.is_blocked(dom):
                        continue
                    found.append((dom, ""))
                    if len(found) >= limit:
                        return found
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        record_http_cooldown(url, exc.code, retry_after)
    except Exception:
        pass
    return found


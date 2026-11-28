#!/usr/bin/env python3
"""
auto_scraper.py
Discovers real, DNS-resolvable SMB prospect domains from search-backed local queries,
Certificate Transparency feeds, and SEED_DOMAINS / PROSPECTS_FILE overrides, enriches
company names and verified on-site contact emails concurrently, syncs Brevo hard bounces,
and filters out synthetic, placeholder, staging, and internal domains.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import datetime
import html as html_lib
import json
import logging
import os
import random
import re
import socket
import sqlite3
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from dotenv import dotenv_values
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
REQUIRE_VERIFIED_EMAIL = os.getenv("REQUIRE_VERIFIED_EMAIL", "1").strip().lower() in {"1", "true", "yes"}
MAX_NEW_LEADS = int(os.getenv("MAX_NEW_LEADS", "110"))
ENRICH_WORKERS = int(os.getenv("ENRICH_WORKERS", "12"))

DEFAULT_DISCOVERY_KEYWORDS = (
    "denverroofing,denverhvac,denverplumbing,denverelectric,coloradoroofing,coloradohvac,"
    "denverdental,denverlaw,coloradoplumbing,coloradoelectric,frontrangeroofing,frontrangehvac,"
    "boulderroofing,boulderhvac,boulderdental,auroraroofing,aurorahvac,lakewoodroofing,"
    "lakewoodplumbing,littletondental,littletonroofing,arvadaplumbing,arvadaroofing,"
    "thorntonhvac,westminsterplumbing,centennialdental,englewoodauto,coloradospringsroofing,"
    "coloradospringshvac,fortcollinsroofing,fortcollinshvac,lovelandplumbing,greeleyhvac,"
    "denverlandscaping,denverremodeling,denverauto,denveraccounting,denvercpa,coloradosolar,"
    "denverchiropractic,coloradoveterinary,denverinsurance,denverrealty,coloradoconstruction"
)

DISCOVERY_KEYWORDS = [
    q.strip()
    for q in os.getenv("DISCOVERY_KEYWORDS", DEFAULT_DISCOVERY_KEYWORDS).split(",")
    if q.strip()
]

SEARCH_QUERIES = [
    '"denver" "roofing" "contact@" OR "info@" OR "office@"',
    '"denver" "hvac" "service@" OR "info@" OR "office@"',
    '"denver" "plumbing" "service@" OR "info@" OR "office@"',
    '"denver" "electrical" OR "electrician" "info@" OR "office@"',
    '"englewood" OR "lakewood" "roofing" OR "hvac" "@"',
    '"aurora" OR "arvada" "plumbing" OR "roofing" "@"',
    '"littleton" OR "centennial" "hvac" OR "dental" "@"',
    '"boulder" OR "longmont" "roofing" OR "plumbing" "@"',
    '"colorado springs" "roofing" OR "hvac" "info@" OR "contact@"',
    '"fort collins" "roofing" OR "plumbing" "info@" OR "office@"',
    '"denver" "dental" "office@" OR "info@"',
    '"denver" "chiropractic" OR "physical therapy" "info@" OR "office@"',
    '"denver" "law firm" OR "attorney" "info@" OR "contact@"',
    '"denver" "cpa" OR "accounting" "info@" OR "contact@"',
    '"denver" "auto repair" OR "collision" "service@" OR "info@"',
    '"denver" "landscaping" OR "tree service" "info@" OR "office@"',
    '"denver" "remodeling" OR "general contractor" "info@" OR "contact@"',
    '"denver" "garage door" OR "locksmith" "service@" OR "info@"',
    '"denver" "pest control" OR "cleaning" "info@" OR "office@"',
    '"denver" "property management" "info@" OR "leasing@"',
    '"colorado" "commercial roofing" "info@" OR "estimating@"',
    '"colorado" "mechanical" OR "heating and cooling" "service@"',
    '"colorado" "veterinary" OR "animal hospital" "info@" OR "office@"',
    '"colorado" "orthodontics" OR "optometry" "office@" OR "info@"',
    '"colorado" "real estate" "info@" OR "contact@"',
    '"colorado" "insurance agency" "info@" OR "contact@"',
    '"colorado" "it services" OR "managed services" "info@" OR "support@"',
    '"colorado" "solar" "info@" OR "sales@"',
    '"westminster" OR "thornton" "roofing" OR "hvac" "info@" OR "office@"',
    '"broomfield" OR "louisville" "dental" OR "plumbing" "info@" OR "office@"',
    '"parker" OR "castle rock" "roofing" OR "landscaping" "info@" OR "contact@"',
    '"golden" OR "wheat ridge" "auto repair" OR "contractor" "info@" OR "service@"',
    '"loveland" OR "greeley" "hvac" OR "electrical" "info@" OR "office@"',
    '"pueblo" OR "grand junction" "roofing" OR "plumbing" "info@" OR "contact@"',
    '"colorado" "custom home builder" OR "architect" "info@" OR "contact@"',
    '"colorado" "flooring" OR "painting contractor" "info@" OR "estimates@"',
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
    "duckduckgo.com",
    "bing.com",
    "google.com",
    "yahoo.com",
    "yelp.com",
    "bbb.org",
    "angi.com",
    "homeadvisor.com",
    "thumbtack.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "nextdoor.com",
    "mapquest.com",
    "yellowpages.com",
    "chamberofcommerce.com",
    "indeed.com",
    "glassdoor.com",
    "zillow.com",
    "realtor.com",
    "healthgrades.com",
    "zocdoc.com",
    "avvo.com",
    "justia.com",
    "findlaw.com",
    "superlawyers.com",
    "wikimedia.org",
    "wikipedia.org",
    "reddit.com",
    "twitter.com",
    "x.com",
    "pinterest.com",
    "tiktok.com",
    "apple.com",
    "microsoft.com",
    "amazon.com",
    "cloudflare.com",
    "godaddy.com",
    "wix.com",
    "squarespace.com",
    "wordpress.com",
}

NON_PROD_LABELS = {"staging", "stage", "dev", "test", "qa", "uat", "sandbox"}
PREFERRED_PREFIXES = ("contact@", "office@", "service@", "support@", "admin@", "hello@", "info@")

DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def normalize_domain(raw: str) -> str:
    val = (raw or "").strip().lower()
    if not val or "*" in val:
        return ""
    val = re.sub(r"^https?://", "", val)
    val = val.split("/", 1)[0].split(":", 1)[0].strip(".")
    if val.startswith("www.") and len(val) > 4:
        val = val[4:]
    if not DOMAIN_RE.match(val):
        return ""
    if val in EXCLUDED_DOMAINS:
        return ""
    labels = val.split(".")
    if len(labels) != 2:
        return ""
    if labels[0] in DISCOVERY_KEYWORDS:
        return ""
    if any(lbl in NON_PROD_LABELS for lbl in labels):
        return ""
    return val


def is_dns_live(domain: str, timeout: float = 2.0) -> bool:
    if not VERIFY_DNS:
        return True
    prev_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False
    finally:
        socket.setdefaulttimeout(prev_timeout)


def enrich_domain_metadata(domain: str, timeout: float = 4.5) -> tuple[str, str]:
    """Fetch homepage and /contact to extract (company_name, verified_on_site_email)."""
    found_emails: set[str] = set()
    company_name = ""
    email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@" + re.escape(domain), re.I)

    for path in ("", "/contact", "/contact-us"):
        url = f"https://{domain}{path}"
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NomadikAudit/1.0)"})
            with urlopen(req, timeout=timeout) as resp:
                raw_html = resp.read(200_000).decode("utf-8", errors="ignore")
        except Exception:
            continue

        if not company_name:
            og_match = re.search(
                r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']',
                raw_html,
                re.I,
            )
            if og_match:
                company_name = html_lib.unescape(og_match.group(1)).strip()
            else:
                title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.I | re.S)
                if title_match:
                    raw_title = re.sub(r"\s+", " ", html_lib.unescape(title_match.group(1))).strip()
                    company_name = re.split(r"\s*[|\-–—:]\s*", raw_title)[0].strip()[:80]

        for match in email_pattern.findall(raw_html):
            cleaned = match.lower().strip(".")
            if EMAIL_RE.match(cleaned) and not cleaned.endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
            ):
                found_emails.add(cleaned)

        if found_emails and company_name:
            break

    chosen_email = ""
    if found_emails:
        for prefix in PREFERRED_PREFIXES:
            for candidate in sorted(found_emails):
                if candidate.startswith(prefix):
                    chosen_email = candidate
                    break
            if chosen_email:
                break
        if not chosen_email:
            chosen_email = sorted(found_emails)[0]

    if not company_name:
        company_name = domain.split(".")[0].replace("-", " ").title()

    return company_name, chosen_email


def _connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def _get_existing_domains(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    try:
        conn = _connect_db(db_path)
        rows = conn.execute("SELECT domain FROM leads WHERE domain IS NOT NULL").fetchall()
        conn.close()
        return {row[0].strip().lower() for row in rows if row and row[0]}
    except Exception:
        return set()

def sync_brevo_bounces(db_path: Path) -> int:
    """Pull recent hardBounces from Brevo API and mark matching leads BOUNCED."""
    api_key = os.getenv("BREVO_API_KEY", "").strip() or dotenv_values(BASE_DIR / ".env").get(
        "BREVO_API_KEY", ""
    ).strip()
    if not api_key or not db_path.exists():
        return 0

    url = "https://api.brevo.com/v3/smtp/statistics/events?event=hardBounces&limit=100"
    req = Request(url, headers={"accept": "application/json", "api-key": api_key})
    try:
        with urlopen(req, timeout=8) as resp:
            events = json.loads(resp.read().decode("utf-8")).get("events", [])
    except Exception:
        return 0

    bounced_emails = {str(ev.get("email", "")).strip().lower() for ev in events if ev.get("email")}
    if not bounced_emails:
        return 0

    conn = _connect_db(db_path)
    cursor = conn.cursor()
    updated = 0
    for em in bounced_emails:
        cursor.execute(
            "UPDATE leads SET status='BOUNCED' WHERE LOWER(contact_email)=? AND status NOT IN ('BOUNCED', 'CONVERTED');",
            (em,),
        )
        updated += cursor.rowcount
    conn.commit()
    conn.close()
    if updated:
        logging.info(f"Synced {updated} Brevo hard-bounce(s) into {db_path.name}.")
    return updated


def _load_from_file(path: Path) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    if not path.exists():
        return records

    try:
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        dom = normalize_domain(item)
                        if dom:
                            records.append((dom, ""))
                    elif isinstance(item, dict):
                        dom = normalize_domain(
                            str(item.get("domain") or item.get("target") or "")
                        )
                        email = str(item.get("email") or item.get("contact_email") or "").strip().lower()
                        if not EMAIL_RE.match(email):
                            email = ""
                        if dom:
                            records.append((dom, email))
        elif path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    dom = normalize_domain(str(row.get("domain") or row.get("target") or ""))
                    email = str(row.get("email") or row.get("contact_email") or "").strip().lower()
                    if not EMAIL_RE.match(email):
                        email = ""
                    if dom:
                        records.append((dom, email))
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


def _fetch_from_search(query: str, limit: int = 25) -> list[tuple[str, str]]:
    """Query DuckDuckGo Lite HTML to discover real SMB websites and visible emails."""
    url = "https://lite.duckduckgo.com/lite/"
    if BLOCKLIST.is_blocked(url):
        return []
    body = urllib.parse.urlencode({"q": query}).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 10 Pro) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        with urlopen(req, timeout=12) as resp:
            page = resp.read().decode("utf-8", errors="ignore")
        for href in re.findall(r'href=["\'](https?://[^"\']+)["\']', page, re.I):
            dom = normalize_domain(href)
            if dom and dom not in seen and not BLOCKLIST.is_blocked(dom):
                seen.add(dom)
                found.append((dom, ""))
            if len(found) >= limit:
                break
        for em in re.findall(r"[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,24})", page):
            dom = normalize_domain(em)
            if dom and dom not in seen and not BLOCKLIST.is_blocked(dom):
                seen.add(dom)
                found.append((dom, ""))
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        record_http_cooldown(url, exc.code, retry_after)
    except Exception:
        pass
    return found


def _fetch_from_crt_sh(keyword: str, limit: int = 25, tld: str = "com") -> list[tuple[str, str]]:
    query = f"%{keyword}%.{tld}"
    url = f"https://crt.sh/?q={quote_plus(query)}&output=json"
    if BLOCKLIST.is_blocked(url):
        return []
    req = Request(url, headers={"User-Agent": "NomadikSentinelScraper/1.0 (+https://nomadik.site)"})
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        with urlopen(req, timeout=15) as resp:
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


def _fetch_from_certspotter(keyword: str, limit: int = 25, tld: str = "com") -> list[tuple[str, str]]:
    url = (
        f"https://api.certspotter.com/v1/issuances?domain={quote_plus(keyword + '.' + tld)}"
        f"&include_subdomains=true&expand=dns_names"
    )
    if BLOCKLIST.is_blocked(url):
        return []
    req = Request(url, headers={"User-Agent": "NomadikSentinelScraper/1.0 (+https://nomadik.site)"})
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        with urlopen(req, timeout=12) as resp:
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


def fetch_candidate_domains() -> list[tuple[str, str]]:
    existing = _get_existing_domains(DB_PATH)
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_pair(dom: str, email: str) -> bool:
        if dom and dom not in seen and dom not in existing and not BLOCKLIST.is_blocked(dom):
            seen.add(dom)
            candidates.append((dom, email))
            return True
        return False

    env_domains = os.getenv("SEED_DOMAINS", "")
    for raw in env_domains.split(","):
        dom = normalize_domain(raw)
        if dom:
            add_pair(dom, "")

    if AUTO_DISCOVER:
        target_pool = MAX_NEW_LEADS * 4
        shuffled_queries = list(SEARCH_QUERIES)
        random.shuffle(shuffled_queries)

        for q in shuffled_queries[:14]:
            if len(candidates) >= target_pool:
                break
            for dom, email in _fetch_from_search(q, limit=25):
                add_pair(dom, email)
            time.sleep(0.4)

        shuffled_keywords = list(DISCOVERY_KEYWORDS)
        random.shuffle(shuffled_keywords)
        tld = random.choice(["com", "com", "co", "net", "org"])

        for kw in shuffled_keywords[:16]:
            if len(candidates) >= target_pool:
                break
            batch = _fetch_from_crt_sh(kw, limit=25, tld=tld)
            if not batch:
                batch = _fetch_from_certspotter(kw, limit=25, tld=tld)
            for dom, email in batch:
                add_pair(dom, email)
            time.sleep(0.4)

    file_records = _load_from_file(PROSPECTS_FILE)
    if file_records:
        random.shuffle(file_records)
        for dom, email in file_records:
            add_pair(dom, email)

    return candidates


def _probe_candidate(pair: tuple[str, str]) -> tuple[str, str, str] | None:
    clean_domain, explicit_email = pair
    if not is_dns_live(clean_domain):
        return None
    company_name, scraped_email = enrich_domain_metadata(clean_domain)
    contact = explicit_email or scraped_email
    if not contact:
        if REQUIRE_VERIFIED_EMAIL:
            return None
        contact = f"info@{clean_domain}"
    return clean_domain, company_name, contact


def ingest_domains(db_path: Path, candidates: list[tuple[str, str]]) -> int:
    if not candidates:
        logging.info("No candidate domains discovered.")
        return 0

    conn = _connect_db(db_path)
    cursor = conn.cursor()
    cols = {row[1] for row in cursor.execute("PRAGMA table_info(leads)").fetchall()}
    existing = {
        row[0].strip().lower()
        for row in cursor.execute("SELECT domain FROM leads WHERE domain IS NOT NULL").fetchall()
    }

    unseen = [(d, e) for d, e in candidates if d not in existing]
    if not unseen:
        conn.close()
        return 0

    inserted_count = 0
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with ThreadPoolExecutor(max_workers=ENRICH_WORKERS) as pool:
        futures = [pool.submit(_probe_candidate, pair) for pair in unseen[: MAX_NEW_LEADS * 4]]
        for fut in as_completed(futures):
            if inserted_count >= MAX_NEW_LEADS:
                break
            res = fut.result()
            if not res:
                continue
            clean_domain, company_name, contact = res
            if clean_domain in existing:
                continue

            lead_id = f"lead_{uuid.uuid4().hex[:8]}"
            if "company_name" in cols:
                query = """
                    INSERT INTO leads (
                        id,
                        domain,
                        company_name,
                        email,
                        contact_email,
                        recipient_email,
                        status,
                        sequence_step,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 0, ?, ?)
                """
                params = (lead_id, clean_domain, company_name, contact, contact, contact, now, now)
            else:
                query = """
                    INSERT INTO leads (
                        id,
                        domain,
                        email,
                        contact_email,
                        recipient_email,
                        status,
                        sequence_step,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'PENDING', 0, ?, ?)
                """
                params = (lead_id, clean_domain, contact, contact, contact, now, now)

            try:
                cursor.execute(query, params)
                existing.add(clean_domain)
                inserted_count += 1
                logging.info(
                    f"Queued lead: [{lead_id}] {clean_domain} ({company_name}) -> {contact} (PENDING)"
                )
            except sqlite3.IntegrityError:
                continue
            except Exception as exc:
                logging.error(f"Error inserting domain {clean_domain}: {exc}")

    conn.commit()
    conn.close()
    return inserted_count


def main() -> None:
    logging.info("--- Starting auto_scraper pipeline run ---")
    if not DB_PATH.exists():
        logging.error(f"Database {DB_PATH} not found!")
        sys.exit(1)

    sync_brevo_bounces(DB_PATH)
    candidates = fetch_candidate_domains()
    logging.info(f"Discovered {len(candidates)} candidate domain(s); probing concurrently...")
    added = ingest_domains(DB_PATH, candidates)
    logging.info(f"Scraper execution complete. Added {added} new domain(s) to {DB_PATH.name}.")


if __name__ == "__main__":
    main()

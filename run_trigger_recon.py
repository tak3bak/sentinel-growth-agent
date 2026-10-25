import asyncio
import csv
import sys
import dns.resolver
import httpx
from jinja2 import Template

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

TEMPLATES = {
    "DMARC_MISSING": """
Subject: Quick note on {{ domain }}'s email delivery & domain security

Hi {{ contact_name }},

While reviewing domain security records for businesses in the area, I noticed that {{ domain }} does not currently have a DMARC policy published.

With Gmail and Yahoo's sender compliance requirements, sending outbound email without DMARC often causes proposals and client communications to route directly to spam. It also leaves your domain vulnerable to direct spoofing.

Setting up a basic monitoring record takes only a couple of minutes in your DNS. If helpful, I put together a 3-step checklist for safe DMARC deployment without impacting your daily mail flow.

Would you like me to send that over?
""",
    "DMARC_P_NONE": """
Subject: Quick note on {{ domain }}'s email delivery & domain security

Hi {{ contact_name }},

While reviewing domain records for businesses in the area, I noticed that {{ domain }} has an active DMARC record set to monitoring mode ({{ proof }}).

Under current provider guidelines, an un-enforced policy can still lead to deliverability issues and does not protect against domain impersonation.

Moving this to quarantine or reject once aligned resolves this. If useful, I have a quick verification checklist for safely enforcing the policy. Would you like me to send it over?
""",
    "EDGE_HEADERS_MISSING": """
Subject: Web security header check for {{ domain }}

Hi {{ contact_name }},

While doing a quick edge configuration audit for {{ domain }}, I noticed your web server is currently omitting {{ proof }}.

For sites handling client interactions, missing HSTS and frame protection leaves connections susceptible to protocol downgrades and clickjacking.

Adding these is typically just a few lines in your edge configuration or web server rules. Would you like the recommended header snippets to pass along to your technical lead?
""",
    "EXPOSED_STAGING": """
Subject: Public staging endpoint on {{ domain }}

Hi {{ contact_name }},

I noticed that {{ proof }} appears to be publicly accessible without access-control or authentication.

Leaving dev or staging environments open to web indexing often exposes internal routing or configuration details to automated scanners.

Isolating this behind a zero-trust access tunnel takes about 15 minutes. Happy to share a quick deployment guide if you'd like to pass it to your team.
"""
}

async def check_dmarc(domain: str) -> dict:
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 4.0
        answers = resolver.resolve(f"_dmarc.{domain}", "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith("v=DMARC1"):
                if "p=none" in txt:
                    return {"trigger": "DMARC_P_NONE", "proof": txt, "weight": 80}
                return {"trigger": "DMARC_ENFORCED", "proof": txt, "weight": 0}
        return {"trigger": "DMARC_MISSING", "proof": "No DMARC record found", "weight": 85}
    except Exception:
        return {"trigger": "DMARC_MISSING", "proof": "No DMARC record found", "weight": 85}

async def check_edge_headers(domain: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, headers=HEADERS) as client:
            res = await client.head(f"https://{domain}")
            headers = {k.lower(): v for k, v in res.headers.items()}
            missing = []
            if "strict-transport-security" not in headers:
                missing.append("Strict-Transport-Security")
            if "content-security-policy" not in headers:
                missing.append("Content-Security-Policy")
            if "x-frame-options" not in headers:
                missing.append("X-Frame-Options")
            if missing:
                return {"trigger": "EDGE_HEADERS_MISSING", "proof": f"Missing: {', '.join(missing)}", "weight": 50}
    except Exception:
        pass
    return {"trigger": "EDGE_CLEAN", "proof": None, "weight": 0}

async def check_exposed_staging(domain: str) -> dict:
    staging_prefixes = ["staging", "dev", "test"]
    async with httpx.AsyncClient(timeout=3.0, follow_redirects=False, headers=HEADERS) as client:
        for prefix in staging_prefixes:
            url = f"https://{prefix}.{domain}"
            try:
                res = await client.get(url)
                if res.status_code == 200 and not any(k in res.text.lower() for k in ["login", "sign in"]):
                    return {"trigger": "EXPOSED_STAGING", "proof": url, "weight": 100}
            except Exception:
                continue
    return {"trigger": "NO_STAGING", "proof": None, "weight": 0}

async def process_domain(domain: str, contact_name: str = "there") -> dict:
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    findings = await asyncio.gather(
        check_dmarc(domain),
        check_edge_headers(domain),
        check_exposed_staging(domain)
    )
    active = [f for f in findings if f["weight"] > 0]
    if not active:
        return {"domain": domain, "trigger": None, "proof": None, "email": None}

    primary = max(active, key=lambda x: x["weight"])
    t_str = TEMPLATES.get(primary["trigger"], "")
    rendered = Template(t_str.strip()).render(
        contact_name=contact_name,
        domain=domain,
        proof=primary["proof"]
    ) if t_str else None

    return {
        "domain": domain,
        "trigger": primary["trigger"],
        "proof": primary["proof"],
        "email": rendered
    }

async def main():
    if len(sys.argv) > 1 and not sys.argv[1].endswith(".csv"):
        res = await process_domain(sys.argv[1])
        print(f"\n[+] Trigger: {res['trigger']}")
        print(f"[+] Proof:   {res['proof']}")
        if res["email"]:
            print(f"\n--- GENERATED EMAIL ---\n{res['email']}\n-----------------------")
    else:
        csv_file = sys.argv[1] if len(sys.argv) > 1 else "leads.csv"
        out_file = "enriched_leads.csv"
        try:
            with open(csv_file, mode="r") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            print(f"[-] {csv_file} not found.")
            return

        print(f"[*] Processing {len(rows)} leads from {csv_file}...")
        enriched = []
        for r in rows:
            domain = r.get("domain") or r.get("website", "")
            contact = r.get("contact_name") or r.get("first_name", "there")
            if domain:
                res = await process_domain(domain, contact)
                r["primary_trigger"] = res["trigger"]
                r["trigger_proof"] = res["proof"]
                r["email_draft"] = res["email"]
                enriched.append(r)

        if enriched:
            fieldnames = list(enriched[0].keys())
            with open(out_file, mode="w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(enriched)
            print(f"[+] Done. Output written to {out_file}")

if __name__ == "__main__":
    asyncio.run(main())

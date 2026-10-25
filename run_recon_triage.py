#!/usr/bin/env python3
"""
Nomadik Security Operations — Autonomous Reconnaissance & Monetization Triage Engine
Triages queued prospects, audits perimeter DNS/headers, and transitions them to MONETIZED_OUTREACH.
"""
import os
import sqlite3
import socket
import urllib.request
import urllib.error
import ssl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "leads.db")

def check_target(domain: str) -> dict:
    findings = []
    ip_resolved = None

    # 1. DNS Resolution check
    try:
        addr_info = socket.getaddrinfo(domain, None)
        if addr_info:
            ip_resolved = addr_info[0][4][0]
    except (socket.gaierror, socket.herror, socket.timeout):
        findings.append("Dormant or unmapped root DNS record (NXDOMAIN / resolution failure)")

    # 2. Web Service / Security Headers Check (only if DNS resolved)
    if ip_resolved:
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                f"https://{domain}",
                headers={"User-Agent": "Nomadik-Sentinel-Audit/1.0"}
            )
            with urllib.request.urlopen(req, timeout=4, context=ctx) as resp:
                headers = {k.lower(): v for k, v in resp.getheaders()}
                if "strict-transport-security" not in headers:
                    findings.append("Missing HTTP Strict Transport Security (HSTS) baseline")
                if "content-security-policy" not in headers:
                    findings.append("Absence of Content-Security-Policy (CSP) headers")
        except urllib.error.HTTPError as e:
            findings.append(f"HTTP edge status anomaly (HTTP {e.code})")
        except Exception:
            findings.append("Primary HTTPS edge endpoint unverified or connection timed out")

        # 3. Perimeter Transport Port Footprint
        open_ports = []
        for port in [80, 443, 8080]:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            try:
                res = sock.connect_ex((domain, port))
                if res == 0:
                    open_ports.append(str(port))
            except (socket.error, OSError):
                pass
            finally:
                sock.close()

        if open_ports:
            findings.append(f"Exposed perimeter transport ports: {', '.join(open_ports)}")

    if not findings:
        findings.append("Legacy DNS record hardening recommended (SPF/DMARC baseline)")

    return {
        "summary": " | ".join(findings),
        "bullets": "\n".join([f" - {f}" for f in findings])
    }

def triage_queue():
    if not os.path.exists(DB_PATH):
        print(f"[-] Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    leads = c.execute(
        "SELECT domain, company_name FROM leads WHERE status IN ('QUEUED', 'PENDING');"
    ).fetchall()

    if not leads:
        print("[*] No pending prospects found in scan queue.")
        conn.close()
        return

    print(f"[*] Triaging {len(leads)} target prospects in pipeline...")

    for domain, company in leads:
        print(f"  -> Auditing {domain} ({company})...")
        try:
            audit = check_target(domain)
            cur = c.execute(
                """
                UPDATE leads
                SET status = 'MONETIZED_OUTREACH',
                    recon_summary = ?,
                    updated_at = datetime('now')
                WHERE domain = ?;
                """,
                (audit["bullets"], domain)
            )
            conn.commit()
            print(f"     [+] Triaged successfully (rows affected: {cur.rowcount}).")
        except Exception as e:
            print(f"     [-] Audit bypassed on error: {e}")

    monetized = c.execute("SELECT COUNT(*) FROM leads WHERE status = 'MONETIZED_OUTREACH';").fetchone()[0]
    queued = c.execute("SELECT COUNT(*) FROM leads WHERE status IN ('QUEUED', 'PENDING');").fetchone()[0]
    conn.close()

    print(f"\n[+] Recon audit complete:")
    print(f"    - Staged for outreach: {monetized} prospects")
    print(f"    - Queued for scanning: {queued} prospects")

if __name__ == "__main__":
    triage_queue()

# ==============================================================================
# NOMADIK SECURITY OPERATIONS - INTENT-DRIVEN OUTREACH ENGINE v3.6
# Author: Kalen Vandenbos <kalen@nomadik.site>
# Description: Automated passive reconnaissance auditor with timeout protection,
#              Groq AI pitch synthesizer, and Brevo API v3 correct header authentication.
# ==============================================================================

import os
import sys
import json
import csv
import socket
import ssl
import subprocess
import requests
from datetime import datetime, timezone

# --- CONFIGURATION ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "your_groq_api_key_here")
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
WEBHOOK_BASE_URL = "https://nomadik.site/api/track"
LEADS_DIR = os.path.expanduser("~/projects/sentinel-growth-agent")
TEST_MODE_OVERRIDE = os.getenv("TEST_MODE_OVERRIDE", "false").lower() == "true"
SANDBOX_RECIPIENT = "tak3bak@gmail.com"

# --- PASSIVE RECONNAISSANCE AUDITOR ---
def audit_target_perimeter(domain: str) -> dict:
    """Executes non-intrusive passive checks with strict timeout handling."""
    audit_results = {
        "domain": domain,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "open_ports": [],
        "ssl_valid": False,
        "ssl_expiry_days": None,
        "dmarc_present": False,
        "vulnerability_score": 0
    }

    common_ports = [21, 22, 80, 443, 3306, 3389, 8080]
    for port in common_ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            result = s.connect_ex((domain, port))
            if result == 0:
                audit_results["open_ports"].append(port)
                if port in [21, 22, 3306, 3389]:
                    audit_results["vulnerability_score"] += 25
            s.close()
        except Exception:
            pass

    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=2) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                audit_results["ssl_valid"] = True
                not_after = cert.get('notAfter')
                if not_after:
                    expiry_date = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                    days_remaining = (expiry_date - datetime.now(timezone.utc)).days
                    audit_results["ssl_expiry_days"] = days_remaining
                    if days_remaining < 14:
                        audit_results["vulnerability_score"] += 20
    except Exception:
        audit_results["vulnerability_score"] += 30

    try:
        dmarc_lookup = subprocess.run(
            ["dig", "+short", f"_dmarc.{domain}", "TXT"],
            capture_output=True, text=True, timeout=2
        )
        if "v=DMARC1" in dmarc_lookup.stdout:
            audit_results["dmarc_present"] = True
        else:
            audit_results["vulnerability_score"] += 15
    except Exception:
        audit_results["vulnerability_score"] += 15

    return audit_results

# --- GROQ AI PITCH SYNTHESIZER ---
def generate_custom_pitch(target_name: str, company: str, audit_data: dict, trigger_event: str) -> str:
    """Synthesizes a hyper-personalized, individualized diagnostic pitch for the specific target."""
    prompt = f"""
    You are Kalen Vandenbos, Lead Security Engineer at Nomadik Security Operations.
    Write a concise, high-impact B2B cold email to {target_name} at {company}.
    
    Context:
    - Target Executive: {target_name}
    - Target Company: {company}
    - Trigger Event: {trigger_event}
    - Diagnostic Audit Findings for {company}:
      * Open/Exposed Ports: {audit_data['open_ports']}
      * SSL Status: Valid ({audit_data.get('ssl_expiry_days')} days remaining) if {audit_data['ssl_valid']} else Misconfigured/Missing
      * DMARC Record Present: {audit_data['dmarc_present']}
      * Risk Exposure Score: {audit_data['vulnerability_score']}/100
      
    Objective:
    Do not use generic sales fluff. Directly reference {company} and the specific audit results above as a free zero-friction diagnostic value drop. Introduce our fixed-fee 48-Hour Perimeter Assessment as a low-risk next step. Keep tone professional, candid, and peer-level technical.
    """

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    models_to_try = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen-2.5-coder-32b"]

    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 600
        }
        try:
            response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip()
        except Exception:
            continue

    return f"Hello {target_name},\n\nWe performed a routine perimeter audit for {company} and identified potential exposure vectors (Risk Score: {audit_data['vulnerability_score']}/100). Let's schedule a brief review of our 48-Hour Perimeter Assessment.\n\nBest,\nKalen Vandenbos\nNomadik Security Operations"

# --- BREVO HTTP API DISPATCHER ---
def dispatch_outreach_email(recipient_email: str, recipient_name: str, company: str, pitch_body: str) -> bool:
    """Dispatches outreach directly via Brevo HTTP API using 'api-key' header."""
    if not BREVO_API_KEY:
        print(f"[-] Brevo API key is not configured.")
        return False

    target_email = SANDBOX_RECIPIENT if TEST_MODE_OVERRIDE else recipient_email
    if TEST_MODE_OVERRIDE:
        pitch_body = f"[TEST MODE: Original intended recipient was {recipient_email} at {company}]\n\n" + pitch_body

    headers = {
        "Accept": "application/json",
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json"
    }

    tracking_html = f"""
    <div>
        {pitch_body.replace(chr(10), '<br>')}
        <img src="{WEBHOOK_BASE_URL}?email={target_email}&company={company}" width="1" height="1" style="display:none;" />
    </div>
    """

    payload = {
        "sender": {"name": "Kalen Vandenbos", "email": "kalen@nomadik.site"},
        "to": [{"email": target_email, "name": recipient_name}],
        "subject": f"Security perimeter audit & exposure snapshot for {company}",
        "htmlContent": tracking_html,
        "replyTo": {"email": "kalen@nomadik.site", "name": "Kalen Vandenbos"}
    }

    try:
        response = requests.post("https://api.brevo.com/v3/smtp/email", headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"[+] Successfully dispatched individualized audit pitch to {target_email} ({company})")
            return True
        else:
            print(f"[-] Failed to dispatch to {target_email} (Status {response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"[-] Brevo API dispatch exception: {str(e)}")
        return False

# --- LOAD LEADS FROM JSON OR CSV ---
def load_leads() -> list:
    """Automatically scans LEADS_DIR for JSON or CSV scrape outputs and aggregates prospects."""
    all_leads = []
    output_file = os.path.expanduser("~/projects/sentinel-growth-agent/leads.json")

    if not os.path.exists(LEADS_DIR):
        os.makedirs(LEADS_DIR, exist_ok=True)

    for filename in os.listdir(LEADS_DIR):
        file_path = os.path.join(LEADS_DIR, filename)
        
        if filename.endswith(".json") and os.path.abspath(file_path) != os.path.abspath(output_file):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_leads.extend(data)
            except Exception:
                pass

        elif filename.endswith(".csv"):
            try:
                with open(file_path, mode="r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        lead = {
                            "name": row.get("name") or row.get("Name") or row.get("First Name", "Security Lead"),
                            "company": row.get("company") or row.get("Company") or "Target Enterprise",
                            "domain": row.get("domain") or row.get("Domain") or row.get("Website", "").replace("https://", "").replace("http://", "").strip("/").split("/")[0],
                            "email": row.get("email") or row.get("Email") or row.get("Work Email"),
                            "trigger": row.get("trigger") or row.get("Trigger") or "Infrastructure expansion & security posture review"
                        }
                        if lead["email"] and lead["domain"]:
                            all_leads.append(lead)
            except Exception:
                pass

    if os.path.exists(output_file):
        try:
            with open(output_file, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if item not in all_leads:
                            all_leads.append(item)
        except Exception:
            pass

    if not all_leads:
        all_leads.append({
            "name": "Target Executive",
            "company": "Resend Test Corp",
            "domain": "resend.com",
            "email": SANDBOX_RECIPIENT,
            "trigger": "Recent funding round & scaling infrastructure expansion"
        })

    return all_leads

# --- EXECUTION PIPELINE ---
if __name__ == "__main__":
    print("[*] Initializing Nomadik Security Operations Growth Agent v3.6 (Brevo API Mode)...")
    prospects = load_leads()
    print(f"[*] Total active prospects queued for outreach: {len(prospects)}")
    
    for p in prospects:
        domain = p.get("domain")
        name = p.get("name", "Security Lead")
        company = p.get("company", domain)
        email = p.get("email")
        trigger = p.get("trigger", "Infrastructure scaling & security posture expansion")

        if not email or not domain:
            continue

        print(f"\n[->] Processing Prospect: {name} at {company} ({domain})")
        print(f"[*] Running passive reconnaissance audit against {domain}...")
        audit = audit_target_perimeter(domain)
        
        print(f"[*] Synthesizing customized Groq AI diagnostic pitch for {company}...")
        pitch = generate_custom_pitch(name, company, audit, trigger)
        
        print(f"[*] Dispatching via Brevo API...")
        dispatch_outreach_email(email, name, company, pitch)
        
    print("\n[+] Batch outreach cycle complete.")

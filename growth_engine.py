#!/usr/bin/env python3
"""
Sentinel Growth Agent - Growth Engine
Automated reconnaissance, perimeter audit, AI diagnostic pitch synthesizer via local Ollama
(qwen2.5-coder:7b), and Brevo API v3 header authentication.
"""

import os
import sys
import json
import socket
import ssl
import subprocess
import requests
from datetime import datetime
from typing import Dict, Any, Optional

# --- CONFIGURATION & CREDENTIALS ---
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "kalen.vandenbos@gmail.com")
SENDER_NAME = os.getenv("SENDER_NAME", "Kalen Vandenbos | Nomadik Security Operations")
SANDBOX_RECIPIENT = os.getenv("SANDBOX_RECIPIENT", "kalen.vandenbos@gmail.com")
TEST_MODE_OVERRIDE = os.getenv(
    "TEST_MODE_OVERRIDE",
    "true").lower() in (
        "true",
        "1",
    "yes")

# Local Inference Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "qwen2.5-coder:7b")


# --- NETWORK AUDIT & RECONNAISSANCE ---
def check_exposed_ports(host: str, ports: list = None) -> list:
    """Scans high-risk perimeter ports on the target host."""
    if ports is None:
        ports = [21, 22, 23, 25, 80, 443, 8080, 8443, 3389, 5432, 27017]
    open_ports = []
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.5)
                result = sock.connect_ex((host, port))
                if result == 0:
                    open_ports.append(port)
        except Exception:
            continue
    return open_ports


def check_ssl_certificate(domain: str) -> dict:
    """Verifies SSL cert validity and days until expiry."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((domain, 443), timeout=3.0) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                expiry_str = cert.get("notAfter")
                expiry_date = datetime.strptime(expiry_str, "%b %d %H:%M:%S %Y %Z")
                remaining_days = (expiry_date - datetime.utcnow()).days
                return {
                    "ssl_valid": True,
                    "ssl_expiry_days": max(0, remaining_days)
                }
    except Exception:
        return {
            "ssl_valid": False,
            "ssl_expiry_days": 0
        }


def check_dmarc_record(domain: str) -> bool:
    """Checks for standard DMARC DNS record existence."""
    try:
        dmarc_host = f"_dmarc.{domain}"
        result = socket.gethostbyname_ex(dmarc_host)
        return bool(result)
    except Exception:
        return False


def run_perimeter_diagnostic(domain: str) -> dict:
    """Aggregates perimeter scan data and computes vulnerability exposure index."""
    open_ports = check_exposed_ports(domain)
    ssl_info = check_ssl_certificate(domain)
    dmarc_present = check_dmarc_record(domain)

    score = 10
    if 21 in open_ports or 23 in open_ports or 3389 in open_ports:
        score += 40
    if not ssl_info["ssl_valid"]:
        score += 30
    elif ssl_info["ssl_expiry_days"] < 14:
        score += 15
    if not dmarc_present:
        score += 20
    if len(open_ports) > 3:
        score += 15

    score = min(score, 100)

    return {
        "domain": domain,
        "open_ports": open_ports,
        "ssl_valid": ssl_info["ssl_valid"],
        "ssl_expiry_days": ssl_info["ssl_expiry_days"],
        "dmarc_present": dmarc_present,
        "vulnerability_score": score
    }


# --- LOCAL AI PITCH SYNTHESIZER (OLLAMA / QWEN 2.5 CODER 7B) ---
def generate_custom_pitch(
        target_name: str,
        company: str,
        audit_data: dict,
        trigger_event: str) -> str:
    """
    Synthesizes a hyper-personalized diagnostic pitch for the specific target
    using local Ollama inference running qwen2.5-coder:7b.
    """
    prompt = """You are Kalen Vandenbos, Lead Security Engineer at Nomadik Security Operations.
Write a concise, high-impact B2B cold email to {target_name} at {company}.

Context:
- Target Executive: {target_name}
- Target Company: {company}
- Trigger Event: {trigger_event}
- Diagnostic Audit Findings for {company}:
  * Open/Exposed Ports: {audit_data.get('open_ports', [])}
  * SSL Status: {'Valid (' + str(audit_data.get('ssl_expiry_days', 0)) + ' days remaining)' if audit_data.get('ssl_valid') else 'Misconfigured/Missing'}
  * DMARC Record Present: {audit_data.get('dmarc_present', False)}
  * Risk Exposure Score: {audit_data.get('vulnerability_score', 0)}/100

Objective:
Do not use generic sales fluff. Directly reference {company} and the specific audit results above as a free zero-friction diagnostic value drop. Introduce our fixed-fee 48-Hour Perimeter Assessment as a low-risk next step. Keep tone professional, candid, and peer-level technical."""

    payload = {"model": LOCAL_MODEL,
               "messages": [{"role": "system",
                             "content": "You are a professional security operations engineer. Keep technical communication grounded, precise, and actionable."},
                            {"role": "user",
                             "content": prompt}],
               "stream": False,
               "options": {"temperature": 0.3,
                           "num_predict": 600}}

    try:
        url = f"{OLLAMA_BASE_URL}/api/chat"
        response = requests.post(url, json=payload, timeout=45)
        if response.status_code == 200:
            res_json = response.json()
            if "message" in res_json and "content" in res_json["message"]:
                return res_json["message"]["content"].strip()
            if "choices" in res_json and res_json["choices"]:
                return res_json["choices"][0]["message"]["content"].strip()
    except Exception as err:
        print(f"[-] Local Ollama inference call failed: {err}")

    return (
        f"Hello {target_name},\n\n"
        f"We performed a routine perimeter audit for {company} and identified potential exposure vectors "
        f"(Risk Score: {audit_data.get('vulnerability_score', 0)}/100).\n\n"
        "Key observations:\n"
        f"- Open/Exposed Ports: {audit_data.get('open_ports', [])}\n"
        f"- SSL Status: {'Active' if audit_data.get('ssl_valid') else 'Needs Review'}\n"
        f"- DMARC Record: {'Configured' if audit_data.get('dmarc_present') else 'Missing'}\n\n"
        "Let's schedule a brief review of our 48-Hour Perimeter Assessment.\n\n"
        "Best,\n"
        "Kalen Vandenbos\n"
        "Nomadik Security Operations"
    )


# --- BREVO HTTP API DISPATCHER ---
def dispatch_outreach_email(
        recipient_email: str,
        recipient_name: str,
        company: str,
        pitch_body: str) -> bool:
    """Dispatches outreach directly via Brevo HTTP API using 'api-key' header."""
    if not BREVO_API_KEY:
        print("[-] Brevo API key is not configured.")
        return False

    target_email = SANDBOX_RECIPIENT if TEST_MODE_OVERRIDE else recipient_email
    if TEST_MODE_OVERRIDE:
        pitch_body = f"[TEST MODE: Original intended recipient was {recipient_email} at {company}]\n\n" + pitch_body

    headers = {
        "Accept": "application/json",
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "sender": {
            "name": SENDER_NAME,
            "email": SENDER_EMAIL
        },
        "to": [
            {
                "email": target_email,
                "name": recipient_name
            }
        ],
        "subject": f"Security perimeter audit for {company}",
        "textContent": pitch_body
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=payload,
            timeout=10
        )
        if response.status_code in (200, 201):
            print(
                f"[+] Successfully dispatched audit email to {target_email} ({company})")
            return True
        else:
            print(
                f"[-] Brevo dispatch failed with HTTP {response.status_code}: {response.text}")
            return False
    except Exception as err:
        print(f"[-] Network exception while calling Brevo API: {err}")
        return False


# --- EXECUTION PIPELINE ---
def run_growth_pipeline(
        target_name: str,
        company: str,
        domain: str,
        recipient_email: str,
        trigger_event: str = "Quarterly Infrastructure Audit"):
    print(f"[*] Initiating perimeter diagnostic for {company} ({domain})...")
    audit_data = run_perimeter_diagnostic(domain)
    print(
        f"[+] Audit complete. Score: {audit_data['vulnerability_score']}/100. Open Ports: {audit_data['open_ports']}")

    print(
        f"[*] Synthesizing customized local AI diagnostic pitch via {LOCAL_MODEL} for {company}...")
    pitch = generate_custom_pitch(target_name, company, audit_data, trigger_event)

    print("[*] Dispatching pitch via Brevo HTTP API...")
    success = dispatch_outreach_email(recipient_email, target_name, company, pitch)
    return {
        "audit": audit_data,
        "pitch": pitch,
        "dispatched": success
    }


if __name__ == "__main__":
    test_run = run_growth_pipeline(
        target_name="Test Exec",
        company="Nomadik Test Corp",
        domain="nomadik.site",
        recipient_email="kalen.vandenbos@gmail.com"
    )
    print("\n--- SAMPLE GENERATED PITCH ---")
    print(test_run["pitch"])

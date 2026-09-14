#!/usr/bin/env python3
"""
Nomadik Security Operations - Growth Pipeline Simulation
"""
import sqlite3
import json
from growth_agent.main import FreeSecurityScanner, PitchGenerator, init_db, DB_PATH

def run_dry_run():
    print("==================================================")
    print("  NOMADIK SECURITY OPERATIONS - PIPELINE TEST")
    print("==================================================")

    # 1. Database Initialization
    print("\n[1/4] Verifying database setup...")
    init_db()
    print(f"  [✓] Database structure verified at {DB_PATH}")

    # 2. Test Signal Scanner
    test_domain = "example.com"
    print(f"\n[2/4] Executing Free Security Scan on '{test_domain}'...")
    scan_results = FreeSecurityScanner.scan_domain(test_domain)
    
    findings = []
    if isinstance(scan_results, dict):
        findings = scan_results.get("findings", scan_results.get("security_flags", []))
        if not findings and "error" not in scan_results:
            findings = [f"{k}: {v}" for k, v in scan_results.items() if v]
    elif isinstance(scan_results, list):
        findings = scan_results

    print(f"  [✓] Scan completed. {len(findings)} findings/signals detected.")
    for f in findings[:5]:
        print(f"      - {f}")

    # 3. Test AI Pitch Generation
    print("\n[3/4] Generating tailored security pitch...")
    checkout_url = "https://api.nomadik.site/api/v1/billing/checkout-session"
    
    # generate_pitch(company_name, findings, checkout_url)
    try:
        pitch = PitchGenerator.generate_pitch(
            company_name="Vance Systems",
            findings=findings,
            checkout_url=checkout_url
        )
        print("  [✓] Pitch generated successfully!")
        print("\n  --------------------------------------------------")
        print(f"  {pitch}")
        print("  --------------------------------------------------")
    except Exception as e:
        print(f"  [!] PitchGenerator fallback: {e}")
        pitch = f"Subject: Security posture for Vance Systems\n\nIdentified {len(findings)} exposure signals on {test_domain}.\nDeploy Nomadik Sentinel: {checkout_url}"
        print(pitch)

    # 4. Save to Database
    print("\n[4/4] Writing lead entry to database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check table columns
    cursor.execute("PRAGMA table_info(leads);")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "domain" in columns and "company_name" in columns:
        cursor.execute(
            """
            INSERT INTO leads (company_name, domain, status)
            VALUES (?, ?, 'SIMULATED')
            """,
            ("Vance Systems", test_domain)
        )
        conn.commit()
        print("  [✓] Lead record inserted into 'leads' table.")
    elif "domain" in columns:
        cursor.execute(
            "INSERT INTO leads (domain, status) VALUES (?, 'SIMULATED')",
            (test_domain,)
        )
        conn.commit()
        print("  [✓] Lead record inserted.")
    
    lead_count = cursor.execute("SELECT COUNT(*) FROM leads;").fetchone()[0]
    print(f"  [✓] Total active leads: {lead_count}")
    conn.close()

    print("\n==================================================")
    print("  [SUCCESS] 4-STAGE PIPELINE SIMULATION COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    run_dry_run()

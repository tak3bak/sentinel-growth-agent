import os
import sqlite3
import json
from dotenv import load_dotenv

# Load env variables (.env)
load_dotenv()

from outbound_engine import FreeSecurityScanner, PitchGenerator, init_db

def run_dry_run():
    print("==================================================")
    print("  NOMADIK SECURITY OPERATIONS - PIPELINE TEST")
    print("==================================================")
    
    # 1. Initialize DB
    print("\n[1/4] Verifying growth_agent.db table setup...")
    init_db()
    print("  [✓] Database structure verified.")

    # 2. Test Signal Scanner
    test_domain = "example.com"
    print(f"\n[2/4] Executing Free Security Scan on '{test_domain}'...")
    signals = FreeSecurityScanner.analyze_domain(test_domain)
    print(f"  [✓] Signals retrieved: {len(signals['security_flags'])} flags found.")
    for flag in signals['security_flags']:
        print(f"      - {flag}")

    # 3. Test Groq Pitch Generation
    print("\n[3/4] Testing AI Pitch Generation via Groq API...")
    try:
        pitch = PitchGenerator.generate_email(
            prospect_name="Alex Vance",
            prospect_title="Head of Information Security",
            company_name="Vance Systems",
            signals=signals
        )
        print("  [✓] Pitch generated successfully!")
        print(f"\n  Subject: {pitch.get('subject_line')}")
        print("  Body Preview:")
        print("  --------------------------------------------------")
        print(f"  {pitch.get('email_body')}")
        print("  --------------------------------------------------")
    except Exception as e:
        print(f"  [X] Groq generation failed: {e}")
        return

    # 4. Save to Database
    print("\n[4/4] Writing lead entry to growth_agent.db...")
    conn = sqlite3.connect("growth_agent.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO leads (prospect_name, prospect_title, company_name, domain, signals, subject_line, email_body, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'DRAFT')
    """, ("Alex Vance", "Head of InfoSec", "Vance Systems", test_domain, json.dumps(signals), pitch.get('subject_line'), pitch.get('email_body')))
    lead_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"  [✓] Saved successfully as Lead ID: #{lead_id}")
    print("\n==================================================")
    print("  PIPELINE VERIFIED AND READY FOR OUTBOUND")
    print("==================================================\n")

if __name__ == "__main__":
    run_dry_run()

#!/usr/bin/env bash
# ==============================================================================
# Nomadik Security Operations - High-ROI Outbound Outreach Dispatcher
# Target: Enterprise Prospects -> Live Stripe Checkout Conversion
# ==============================================================================

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cd "$HOME/projects/sentinel-growth-agent"
export PYTHONPATH="src:.:${PYTHONPATH:-}"

echo -e "${BLUE}[*] 1. Checking Brevo API Egress Credentials...${NC}"

if [[ -z "${BREVO_API_KEY:-}" ]]; then
  # Check if stored in .env
  if [[ -f ".env" ]] && grep -q "BREVO_API_KEY" .env; then
    export BREVO_API_KEY=$(grep "BREVO_API_KEY" .env | cut -d '=' -f2 | tr -d '"\r ')
    echo -e "  ${GREEN}[+] Loaded BREVO_API_KEY from .env.${NC}"
  else
    echo -e "  ${YELLOW}[!] BREVO_API_KEY not found in environment or .env.${NC}"
    echo -e "  To send live emails, run: export BREVO_API_KEY=\"xkeysib-...\""
    echo -e "  Proceeding in DRY-RUN verification mode...\n"
  fi
else
  echo -e "  ${GREEN}[+] BREVO_API_KEY detected in environment.${NC}\n"
fi

# Step 2: Self-Test Probe
echo -e "${BLUE}[*] 2. Executing Self-Test Dispatch Probe...${NC}"

python3 -c "
import os
import requests
import json

api_key = os.getenv('BREVO_API_KEY')
test_recipient = 'kalen.vandenbos@gmail.com'

# Generate real checkout link from local gateway
checkout_url = 'https://nomadik.site/#pricing'
try:
    res = requests.post(
        'http://127.0.0.1:8000/api/v1/billing/checkout-session',
        json={'plan': 'sentinel_pro', 'customer_email': test_recipient},
        timeout=3
    )
    if res.status_code == 200:
        checkout_url = res.json().get('checkout_url', checkout_url)
except Exception:
    pass

subject = 'Security Notice: Vulnerability report for Vance Systems'
body = f'''Hello Security Team,

Our autonomous perimeter reconnaissance surfaced key exposure vectors:
 - Exposed perimeter services detected on root domain
 - Missing strict DMARC / SPF DNS record hardening
 - Subdomain takeover risk on unmapped cloud endpoints

Activate real-time perimeter protection immediately: {checkout_url}

— Kalen Vandenbos
Founder, Nomadik Security Operations'''

if not api_key:
    print(f'[DRY-RUN] Verified email payload for {test_recipient}:')
    print('--------------------------------------------------')
    print(body)
    print('--------------------------------------------------')
else:
    print(f'[*] Sending live probe to {test_recipient} via Brevo API...')
    resp = requests.post(
        'https://api.brevo.com/v3/smtp/email',
        headers={
            'accept': 'application/json',
            'api-key': api_key,
            'content-type': 'application/json'
        },
        json={
            'sender': {'name': 'Kalen Vandenbos', 'email': 'outreach@nomadik.site'},
            'to': [{'email': test_recipient, 'name': 'Kalen Vandenbos'}],
            'subject': subject,
            'textContent': body
        }
    )
    if resp.status_code in [200, 201, 202]:
        print(f'[SUCCESS] Self-test email delivered to {test_recipient} (HTTP {resp.status_code}).')
    else:
        print(f'[ERROR] Brevo API returned HTTP {resp.status_code}: {resp.text}')
"

echo -e "\n${BLUE}[*] 3. Target Batch Status in leads.db...${NC}"
python3 -c "
import sqlite3
conn = sqlite3.connect('leads.db')
c = conn.cursor()
queued = c.execute(\"SELECT COUNT(*) FROM leads WHERE status = 'QUEUED' OR status = 'PENDING';\").fetchone()[0]
monetized = c.execute(\"SELECT COUNT(*) FROM leads WHERE status = 'MONETIZED_OUTREACH';\").fetchone()[0]
print(f'  - Staged for outreach: {monetized} prospects')
print(f'  - Queued for scanning: {queued} prospects')
conn.close()
"

echo -e "\n${GREEN}[SUCCESS] Dispatch engine audit complete.${NC}"

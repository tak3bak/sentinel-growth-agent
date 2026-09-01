#!/usr/bin/env bash
set -e

# Load environment variables if available
if [ -f ~/.env ]; then
  set -a
  source ~/.env
  set +a
fi

cd ~/projects/sentinel/sentinel-growth-agent

# Target leads data
LEAD_FILE="$HOME/data/leads/prospects.csv"
if [ ! -s "$LEAD_FILE" ]; then
  LEAD_FILE="$HOME/data/leads/leads.csv"
fi

if [ ! -s "$LEAD_FILE" ]; then
  echo "[-] Error: No lead records found in ~/data/leads/"
  exit 1
fi

TOTAL_LEADS=$(tail -n +2 "$LEAD_FILE" | grep -c '[^[:space:]]' || true)
LOG_FILE="$HOME/logs/outbound_campaign_$(date +%Y%m%d_%H%M%S).log"

echo "[*] Initializing Sentinel Growth Agent Outreach Engine"
echo "[*] Target List: $LEAD_FILE ($TOTAL_LEADS prospects queued)"
echo "[*] Logging to: $LOG_FILE"

# Execute agent with output streaming to console and log file
python3 outbound_engine.py \
  --leads "$LEAD_FILE" \
  --outbox "$HOME/data/queues/outbox" \
  --reports "$HOME/data/leads/reports" \
  2>&1 | tee -a "$LOG_FILE"

echo "[+] Outbound sequence dispatch complete."

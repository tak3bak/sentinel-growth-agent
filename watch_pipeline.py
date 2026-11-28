#!/usr/bin/env python3
import os
import subprocess
import sys
import time

base_dir = os.path.expanduser("~/projects/sentinel-growth-agent")
scraper_path = os.path.join(base_dir, "auto_scraper.py")
orchestrator_path = os.path.join(base_dir, "pipeline_orchestrator.py")
followup_path = os.path.join(base_dir, "followup_engine.py")
interval = int(os.getenv("DAEMON_INTERVAL_SEC", "1800"))  # 30 minutes

print("[*] Starting Nomadik Security Sentinel autonomous growth daemon (LIVE --send + follow-up mode)...", flush=True)
while True:
    try:
        print(f"\n[*] Triggering scraper + orchestrator + follow-up cycle at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        subprocess.run([sys.executable, scraper_path], check=False)
        subprocess.run([sys.executable, orchestrator_path, "--send"], check=False)
        subprocess.run([sys.executable, os.path.join(base_dir, 'sync_replies.py')], check=False)
        subprocess.run([sys.executable, followup_path], check=False)
    except Exception as e:
        print(f"[-] Pipeline execution error: {e}", flush=True)

    print(f"[*] Sleeping for {interval // 60} minutes...", flush=True)
    time.sleep(interval)

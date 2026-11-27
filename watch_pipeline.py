#!/usr/bin/env python3
import os
import subprocess
import sys
import time

base_dir = os.path.expanduser("~/projects/sentinel-growth-agent")
scraper_path = os.path.join(base_dir, "auto_scraper.py")
orchestrator_path = os.path.join(base_dir, "pipeline_orchestrator.py")
interval = 1800  # 30 minutes

print("[*] Starting Nomadik Security Sentinel autonomous growth daemon (LIVE --send mode)...")
while True:
    try:
        print(f"[*] Triggering scraper + orchestrator run at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        subprocess.run([sys.executable, scraper_path], check=False)
        subprocess.run([sys.executable, orchestrator_path, "--send"], check=True)
    except Exception as e:
        print(f"[-] Pipeline execution error: {e}")

    print(f"[*] Sleeping for {interval // 60} minutes...")
    time.sleep(interval)

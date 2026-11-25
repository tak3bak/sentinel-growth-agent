#!/usr/bin/env python3
import time
import subprocess
import os
import sys

orchestrator_path = os.path.expanduser('~/projects/sentinel-growth-agent/pipeline_orchestrator.py')
interval = 1800  # 30 minutes

print("[*] Starting Nomadik Security Sentinel autonomous growth daemon...")
while True:
    try:
        print(f"[*] Triggering orchestrator run at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        subprocess.run([sys.executable, orchestrator_path], check=True)
    except Exception as e:
        print(f"[-] Pipeline execution error: {e}")

    print(f"[*] Sleeping for {interval // 60} minutes...")
    time.sleep(interval)

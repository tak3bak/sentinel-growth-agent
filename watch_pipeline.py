#!/usr/bin/env python3
import time
import subprocess
import os

pipeline_path = os.path.expanduser('~/projects/sentinel-growth-agent/run_pipeline.py')
interval = 1800  # 30 minutes

print("[*] Starting Nomadik Security Sentinel autonomous growth daemon...")
while True:
    try:
        print(f"[*] Triggering pipeline run at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        subprocess.run([pipeline_path], check=True)
    except Exception as e:
        print(f"[-] Pipeline execution error: {e}")
    
    print(f"[*] Sleeping for {interval // 60} minutes...")
    time.sleep(interval)

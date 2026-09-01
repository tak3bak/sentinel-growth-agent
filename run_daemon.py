import time
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GrowthDaemon")

INTERVAL_HOURS = 4

def job():
    logger.info("[-] Starting automated growth cycle...")
    try:
        subprocess.run(["python3", "auto_scraper.py"], check=True)
        # Create a temporary targets file or let run_live_campaign pull from db directly
        subprocess.run(["python3", "run_live_campaign.py", "targets.json"], check=True)
        logger.info("[+] Growth cycle completed successfully.")
    except Exception as e:
        logger.error(f"[!] Error in growth cycle: {e}")

if __name__ == "__main__":
    logger.info(f"[✓] Sentinel Growth Daemon active. Running every {INTERVAL_HOURS} hours.")
    while True:
        job()
        time.sleep(INTERVAL_HOURS * 3600)

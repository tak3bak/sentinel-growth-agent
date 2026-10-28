import os
import requests
import logging

logger = logging.getLogger("sentinel_mesh")

def emit_sentinel_telemetry(event_type: str, destination_ip: str = "api.brevo.com", info: str = "", packet_length: int = 512):
    """Dispatches security telemetry to Nomadik Security Sentinel (Port 8000)."""
    sentinel_key = os.getenv("SENTINEL_API_KEY")
    if not sentinel_key:
        env_path = os.path.expanduser("~/projects/nomadik-security-sentinel/.env")
        if os.path.exists(env_path):
            try:
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("SENTINEL_API_KEY="):
                            sentinel_key = line.strip().split("=", 1)[1].strip('"\'')
                            break
            except Exception:
                pass

    if not sentinel_key:
        return False

    payload = {
        "source_ip": "127.0.0.1",
        "destination_ip": destination_ip,
        "source_port": 8001,
        "destination_port": 443 if "api." in destination_ip else 8000,
        "protocol": "HTTPS",
        "packet_length": packet_length,
        "event_type": event_type,
        "info": info
    }

    try:
        res = requests.post(
            "http://127.0.0.1:8000/api/v1/sentinel/ingest",
            headers={"X-API-Key": sentinel_key, "Content-Type": "application/json"},
            json=payload,
            timeout=1.5
        )
        return res.status_code == 200
    except Exception as e:
        logger.debug(f"Sentinel mesh telemetry dispatch skipped: {e}")
        return False

import os
import requests
import logging

logger = logging.getLogger("sentinel_mesh")

def get_sentinel_key() -> str:
    key = os.getenv("SENTINEL_API_KEY")
    if key:
        return key

    candidate_paths = [
        os.path.expanduser("~/projects/security-sentinel/config.env"),
        os.path.expanduser("~/projects/security-sentinel/.env"),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("SENTINEL_API_KEY="):
                            return line.split("=", 1)[1].strip('"\'')
            except Exception:
                pass
    return "dev-sentinel-api-key"

def emit_sentinel_telemetry(
    event_type: str,
    destination_ip: str = "api.brevo.com",
    info: str = "",
    packet_length: int = 512
) -> bool:
    """Dispatches security telemetry to Nomadik Security Sentinel (Port 8000)."""
    sentinel_key = get_sentinel_key()

    payload = {
        "source": "growth_agent",
        "event_type": event_type[:128],
        "title": f"Telemetry: {event_type}"[:500],
        "severity": "info",
        "payload": {
            "source_ip": "127.0.0.1",
            "destination_ip": destination_ip,
            "source_port": 8001,
            "destination_port": 443 if "api." in destination_ip else 8000,
            "protocol": "HTTPS",
            "packet_length": packet_length,
            "info": info or f"Egress dispatch to {destination_ip}"
        }
    }

    try:
        res = requests.post(
            "http://127.0.0.1:8000/api/v1/events",
            headers={
                "X-API-Key": sentinel_key,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=1.5
        )
        return res.status_code in (200, 201)
    except Exception as e:
        logger.debug(f"Sentinel mesh telemetry dispatch skipped: {e}")
        return False

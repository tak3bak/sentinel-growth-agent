#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

TARGETS = [
    {
        "name": "Nomadik Edge API",
        "url": "https://nomadik.site/api/checkout",
        "method": "GET",
        "expected": [200, 400, 405]
    },
    {
        "name": "Cloudflare PoP & Egress",
        "url": "https://www.cloudflare.com/cdn-cgi/trace",
        "method": "GET",
        "expected": [200]
    },
    {
        "name": "Google DNS-over-HTTPS",
        "url": "https://dns.google/resolve?name=nomadik.site&type=A",
        "method": "GET",
        "expected": [200]
    }
]

def run_suite():
    print("=" * 66)
    print(" [Nomadik SecOps] Automated Scraper & Egress Diagnostic Suite")
    print(f" UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}")
    print("=" * 66)

    results = []
    trace_meta = {}
    all_ok = True

    for target in TARGETS:
        name = target["name"]
        url = target["url"]
        expected = target["expected"]

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Nomadik-SecOps/2.0 (Android/Termux; +https://nomadik.site)"},
            method=target["method"]
        )

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                latency = (time.perf_counter() - t0) * 1000
                status = resp.status
                body = resp.read().decode("utf-8", errors="ignore")

                if "cdn-cgi/trace" in url:
                    for line in body.splitlines():
                        if "=" in line:
                            k, v = line.split("=", 1)
                            trace_meta[k.strip()] = v.strip()

                is_valid = status in expected
                results.append({"name": name, "url": url, "status": status, "latency_ms": round(latency, 2), "success": is_valid})

                flag = "[✓]" if is_valid else "[!]"
                print(f"{flag} {name:<26} | HTTP {status:<3} | Latency: {latency:6.2f}ms")
                if not is_valid:
                    all_ok = False

        except urllib.error.HTTPError as e:
            latency = (time.perf_counter() - t0) * 1000
            is_valid = e.code in expected
            results.append({"name": name, "url": url, "status": e.code, "latency_ms": round(latency, 2), "success": is_valid})
            flag = "[✓]" if is_valid else "[✗]"
            print(f"{flag} {name:<26} | HTTP {e.code:<3} (Handled) | Latency: {latency:6.2f}ms")
            if not is_valid:
                all_ok = False
        except Exception as e:
            results.append({"name": name, "url": url, "error": str(e), "success": False})
            print(f"[✗] {name:<26} | FAILED: {str(e)}")
            all_ok = False

    print("-" * 66)
    if trace_meta:
        print(f" Egress IP  : {trace_meta.get('ip', 'N/A')}")
        print(f" Cloudflare : PoP={trace_meta.get('colo', 'N/A')} | Geo={trace_meta.get('loc', 'N/A')} | Cipher={trace_meta.get('tls', 'N/A')}")
        print("-" * 66)

    log_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all_ok else "FAIL",
        "trace": trace_meta,
        "checks": results
    }
    log_path = os.path.expanduser("~/projects/sentinel-growth-agent/logs/health_latest.json")
    with open(log_path, "w") as f:
        json.dump(log_payload, f, indent=2)

    print(f" Telemetry saved -> ~/projects/sentinel-growth-agent/logs/health_latest.json")
    print("=" * 66)

    if all_ok:
        print("\n[✓] ALL PIPELINE CHECKS PASSED (Exit Code: 0)\n")
        sys.exit(0)
    else:
        print("\n[✗] PIPELINE CHECKS FAILED (Exit Code: 1)\n")
        sys.exit(1)

if __name__ == "__main__":
    run_suite()

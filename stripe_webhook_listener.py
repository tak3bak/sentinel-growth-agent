#!/usr/bin/env python3
"""Nomadik Security Sentinel - Stripe Webhook Ingestion Service
Binds to port 8002 and records checkout.session.completed events into leads.db.
"""

import json
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

DB_PATH = os.path.join(os.path.dirname(__file__), "leads.db")
PORT = 8002


def record_subscription(customer_email: str, subscription_id: str, tier: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. Upsert into subscriptions table
    c.execute(
        """
        INSERT INTO subscriptions (customer_email, subscription_id, tier, status, updated_at)
        VALUES (?, ?, ?, 'ACTIVE', datetime('now'))
        ON CONFLICT(customer_email) DO UPDATE SET
            subscription_id=excluded.subscription_id,
            tier=excluded.tier,
            status='ACTIVE',
            updated_at=datetime('now')
    """,
        (customer_email, subscription_id, tier),
    )

    # 2. Update status in leads table if matching record exists
    c.execute(
        """
        UPDATE leads 
        SET status = 'CONVERTED', updated_at = datetime('now')
        WHERE email = ? OR domain = ?
    """,
        (
            customer_email,
            customer_email.split("@")[-1] if "@" in customer_email else "",
        ),
    )

    conn.commit()
    conn.close()
    print(
        f"[✓] Successfully recorded conversion: {customer_email} ({tier}) -> {subscription_id}"
    )


class WebhookHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        payload_bytes = self.rfile.read(content_length)

        try:
            event = json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        event_type = event.get("type", "")
        print(f"[*] Received Stripe webhook event: {event_type}")

        if event_type == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            customer_details = session.get("customer_details") or {}
            email = customer_details.get("email") or session.get(
                "customer_email", ""
            )
            sub_id = session.get("subscription") or session.get(
                "id", "cs_manual"
            )
            metadata = session.get("metadata") or {}
            tier = metadata.get("tier", "PRO")

            if email:
                record_subscription(email, sub_id, tier)
            else:
                print("[-] Received checkout session without customer email.")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"service":"nomadik-stripe-webhook","status":"up"}')

    def log_message(self, format, *args):
        # Clean logging format
        sys.stderr.write(
            f"[Webhook] {self.address_string()} - - [{self.log_date_time_string()}] {format % args}\n"
        )


def main():
    server = HTTPServer(("127.0.0.1", PORT), WebhookHandler)
    print(f"[*] Nomadik Stripe Webhook Listener active on http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Stopping webhook listener.")
        server.server_close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import json, os, secrets, urllib.request
from pathlib import Path
from sync_replies import load_env

load_env()
API = "https://api.cloudflare.com/client/v4"
TOK = os.environ["CF_TOK"].strip()
ENV_PATH = Path(__file__).resolve().parent / ".env"


def cf(method, path, body=None, ctype="application/json"):
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {TOK}", "Content-Type": ctype},
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        res = json.loads(r.read().decode())
    if not res.get("success"):
        raise RuntimeError(f"{method} {path} failed: {res.get('errors')}")
    return res["result"]


acc_id = cf("GET", "/accounts")[0]["id"]
zone_id = [z for z in cf("GET", "/zones?name=nomadik.site") if z["name"] == "nomadik.site"][0]["id"]
sub = cf("GET", f"/accounts/{acc_id}/workers/subdomain")["subdomain"]
print(f"[+] Account: {acc_id} | Zone: {zone_id} | Subdomain: {sub}.workers.dev")

kvs = cf("GET", f"/accounts/{acc_id}/storage/kv/namespaces")
kv = next((k for k in kvs if k["title"] == "NOMADIK_REPLIES"), None)
kv_id = kv["id"] if kv else cf("POST", f"/accounts/{acc_id}/storage/kv/namespaces", {"title": "NOMADIK_REPLIES"})["id"]
print(f"[+] KV Namespace NOMADIK_REPLIES: {kv_id}")

sync_tok = secrets.token_hex(24)

worker_js = '''export default {
  async email(m, env) {
    const s = (m.from || "").trim().toLowerCase();
    const subj = (m.headers.get("subject") || "").toLowerCase();
    const auto = (m.headers.get("auto-submitted") || "no").toLowerCase();
    if (s.includes("@") && !s.endsWith("@nomadik.site") && auto === "no" && !subj.includes("out of office") && !subj.includes("undeliverable")) {
      await env.REPLIES_KV.put(`reply:${s}`, JSON.stringify({ from: s, ts: new Date().toISOString() }), { expirationTtl: 2592000 });
    }
    await m.forward("kalen.vandenbos@gmail.com");
  },
  async fetch(req, env) {
    if (!env.SYNC_TOKEN || req.headers.get("Authorization") !== `Bearer ${env.SYNC_TOKEN}`) {
      return new Response('{"error":"Unauthorized"}', { status: 401 });
    }
    const list = await env.REPLIES_KV.list({ prefix: "reply:" });
    return new Response(JSON.stringify({ senders: list.keys.map(k => k.name.slice(6)) }), { status: 200 });
  }
};'''

meta = json.dumps({
    "main_module": "worker.js",
    "bindings": [
        {"type": "kv_namespace", "name": "REPLIES_KV", "namespace_id": kv_id},
        {"type": "secret_text", "name": "SYNC_TOKEN", "text": sync_tok},
    ],
})
bnd = "----NomadikBoundary7MA4YWxkTrZu0gW"
mp = (
    f"--{bnd}\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n{meta}\r\n"
    f"--{bnd}\r\nContent-Disposition: form-data; name=\"worker.js\"; filename=\"worker.js\"\r\nContent-Type: application/javascript+module\r\n\r\n{worker_js}\r\n"
    f"--{bnd}--\r\n"
).encode()

cf("PUT", f"/accounts/{acc_id}/workers/scripts/nomadik-reply-tracker", mp, f"multipart/form-data; boundary={bnd}")
cf("POST", f"/accounts/{acc_id}/workers/scripts/nomadik-reply-tracker/subdomain", {"enabled": True})
worker_url = f"https://nomadik-reply-tracker.{sub}.workers.dev"
print(f"[+] Worker deployed: {worker_url}")

rules = cf("GET", f"/zones/{zone_id}/email/routing/rules")
existing = next(
    (r for r in rules if any(m.get("field") == "to" and m.get("value") == "outreach@nomadik.site" for m in r.get("matchers", []))),
    None,
)
rule_body = {
    "name": "Nomadik Outreach Reply Tracker",
    "enabled": True,
    "matchers": [{"type": "literal", "field": "to", "value": "outreach@nomadik.site"}],
    "actions": [{"type": "worker", "value": ["nomadik-reply-tracker"]}],
}
if existing:
    cf("PUT", f"/zones/{zone_id}/email/routing/rules/{existing['id']}", rule_body)
    print(f"[+] Updated Email Routing rule {existing['id']} -> nomadik-reply-tracker")
else:
    created = cf("POST", f"/zones/{zone_id}/email/routing/rules", rule_body)
    print(f"[+] Created Email Routing rule {created['id']} -> nomadik-reply-tracker")

lines = [
    l for l in ENV_PATH.read_text(encoding="utf-8").splitlines()
    if not l.startswith(("CLOUDFLARE_ACCOUNT_ID=", "NOMADIK_REPLIES_KV_ID=", "REPLY_TRACKER_URL=", "REPLY_SYNC_TOKEN="))
]
lines.extend([
    f"CLOUDFLARE_ACCOUNT_ID={acc_id}",
    f"NOMADIK_REPLIES_KV_ID={kv_id}",
    f"REPLY_TRACKER_URL={worker_url}",
    f"REPLY_SYNC_TOKEN={sync_tok}",
])
ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
os.chmod(ENV_PATH, 0o600)
print("[+] Saved Cloudflare Worker & KV credentials to .env")

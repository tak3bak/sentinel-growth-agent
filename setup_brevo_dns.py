import json, os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

for f in [".env", "../.env", os.path.expanduser("~/.env")]:
    if os.path.exists(f):
        for l in open(f, encoding="utf-8"):
            l = l.strip()
            if l and not l.startswith("#") and "=" in l:
                k, v = l.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

tok = os.getenv("CLOUDFLARE_API_TOKEN") or os.getenv("CF_API_TOKEN") or input("CF Token: ").strip()
zid = os.getenv("CLOUDFLARE_ZONE_ID") or os.getenv("CF_ZONE_ID")
hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

def cf(path, method="GET", body=None):
    req = Request(f"https://api.cloudflare.com/client/v4{path}", data=json.dumps(body).encode() if body else None, headers=hdr, method=method)
    try:
        with urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        raise SystemExit(f"CF {method} {path} ({e.code}): {e.read().decode()}")

if not zid:
    zid = cf("/zones?name=nomadik.site")["result"][0]["id"]

txts = cf(f"/zones/{zid}/dns_records?type=TXT&per_page=100")["result"]
targets = [
    ("nomadik.site", "brevo-code:f07c9cc081aeb8bb9b2c11d1c11e6aa6", lambda r: r["name"] == "nomadik.site" and "brevo-code:" in r.get("content", "")),
    ("_dmarc.nomadik.site", "v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com", lambda r: r["name"] == "_dmarc.nomadik.site"),
]
for name, content, match in targets:
    hits = [r for r in txts if match(r)]
    body = {"type": "TXT", "name": name, "content": content, "ttl": 1}
    if hits:
        print("Updated", name, cf(f"/zones/{zid}/dns_records/{hits[0]['id']}", "PUT", body)["success"])
        for d in hits[1:]:
            cf(f"/zones/{zid}/dns_records/{d['id']}", "DELETE")
    else:
        print("Created", name, cf(f"/zones/{zid}/dns_records", "POST", body)["success"])

#!/usr/bin/env python3
import email, imaplib, json, os, re, sqlite3, urllib.request
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parseaddr
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "leads.db"
ENV_PATH = BASE_DIR / ".env"
ACTIVE = ("DISPATCHED", "DISPATCHED_ACTIVE", "FOLLOWUP_SENT", "CONTACTED")
FREE = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com",
    "icloud.com", "proton.me", "protonmail.com", "comcast.net", "msn.com", "live.com"
}


def load_env():
    if not ENV_PATH.exists():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def dec(val):
    if not val:
        return ""
    return "".join(
        c.decode(cs or "utf-8", errors="replace") if isinstance(c, bytes) else c
        for c, cs in decode_header(val)
    ).strip()


def _normalize_sender(raw_addr):
    snd = parseaddr(raw_addr or "")[1].strip().lower()
    if not snd or "@" not in snd or snd.endswith("@nomadik.site"):
        return ""
    return snd


def fetch_cf_worker_senders(worker_url, sync_token):
    req = urllib.request.Request(
        worker_url.strip(),
        method="GET",
        headers={
            "Authorization": f"Bearer {sync_token.strip()}",
            "Accept": "application/json",
            "User-Agent": "Nomadik-Reply-Sync/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    out = set()
    for raw in payload.get("senders", []):
        snd = _normalize_sender(raw)
        if snd:
            out.add(snd)
    return out


def fetch_cf_kv_senders(cf_token, account_id="", namespace_title="NOMADIK_REPLIES", namespace_id=""):
    api = "https://api.cloudflare.com/client/v4"
    headers = {
        "Authorization": f"Bearer {cf_token.strip()}",
        "Content-Type": "application/json",
    }

    def cf_get(path):
        req = urllib.request.Request(f"{api}{path}", method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("success"):
            raise RuntimeError(f"Cloudflare API error on {path}: {data.get('errors')}")
        return data["result"]

    acc = account_id.strip() or cf_get("/accounts")[0]["id"]
    kv_id = namespace_id.strip()
    if not kv_id:
        namespaces = cf_get(f"/accounts/{acc}/storage/kv/namespaces")
        match = next((n for n in namespaces if n.get("title") == namespace_title), None)
        if not match:
            raise RuntimeError(f"KV namespace '{namespace_title}' not found")
        kv_id = match["id"]

    out = set()
    cursor = ""
    while True:
        query = f"/accounts/{acc}/storage/kv/namespaces/{kv_id}/keys?prefix=reply:"
        if cursor:
            query += f"&cursor={cursor}"
        req = urllib.request.Request(f"{api}{query}", method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("success"):
            raise RuntimeError(f"Cloudflare KV list error: {data.get('errors')}")
        for item in data.get("result", []):
            name = item.get("name", "")
            raw_sender = name[6:] if name.startswith("reply:") else name
            snd = _normalize_sender(raw_sender)
            if snd:
                out.add(snd)
        cursor = (data.get("result_info") or {}).get("cursor", "")
        if not cursor:
            break
    return out


def fetch_senders(host, port, user, pw, days=7):
    out = set()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
    with imaplib.IMAP4_SSL(host, port) as m:
        m.login(user, pw)
        m.select("INBOX", readonly=True)
        st, d = m.search(None, f'(SINCE "{since}")')
        if st != "OK" or not d or not d[0]:
            return out
        for mid in d[0].split():
            res, md = m.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM TO DELIVERED-TO SUBJECT IN-REPLY-TO AUTO-SUBMITTED)])")
            if res != "OK" or not md:
                continue
            msg = email.message_from_bytes(b"".join(p[1] for p in md if isinstance(p, tuple)))
            snd = parseaddr(msg.get("From", ""))[1].strip().lower()
            if not snd or "@" not in snd or snd == user.lower() or snd.endswith("@nomadik.site"):
                continue
            if (msg.get("Auto-Submitted") or "no").strip().lower() != "no":
                continue
            subj = dec(msg.get("Subject"))
            blob = " ".join([msg.get("To", ""), msg.get("Delivered-To", ""), msg.get("In-Reply-To", ""), subj]).lower()
            if "nomadik.site" in blob or "perimeter exposure" in subj.lower() or msg.get("In-Reply-To"):
                out.add(snd)
    return out


def sync_replies(db_path=DB_PATH):
    load_env()
    worker_url = os.getenv("REPLY_TRACKER_URL", "").strip()
    sync_token = os.getenv("REPLY_SYNC_TOKEN", "").strip()
    cf_token = (os.getenv("CF_TOK") or os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()
    cf_acc = (os.getenv("CLOUDFLARE_ACCOUNT_ID") or os.getenv("CF_ACCOUNT_ID") or "").strip()
    cf_kv_id = (os.getenv("NOMADIK_REPLIES_KV_ID") or os.getenv("CF_KV_NAMESPACE_ID") or "").strip()
    u, pw = os.getenv("IMAP_USER", "").strip(), os.getenv("IMAP_PASSWORD", "").strip()

    senders = set()
    if worker_url and sync_token:
        try:
            senders = fetch_cf_worker_senders(worker_url, sync_token)
        except Exception as e:
            print(f"[Reply Sync] [!] Cloudflare Worker error: {e}")
            return 0
    elif cf_token:
        try:
            senders = fetch_cf_kv_senders(cf_token, account_id=cf_acc, namespace_id=cf_kv_id)
        except Exception as e:
            print(f"[Reply Sync] [!] Cloudflare KV error: {e}")
            return 0
    elif u and pw:
        try:
            senders = fetch_senders(
                os.getenv("IMAP_HOST", "imap.gmail.com").strip(),
                int(os.getenv("IMAP_PORT", "993")),
                u,
                pw,
                int(os.getenv("REPLY_LOOKBACK_DAYS", "7")),
            )
        except Exception as e:
            print(f"[Reply Sync] [!] IMAP error: {e}")
            return 0
    else:
        print("[Reply Sync] No Cloudflare Worker/KV credentials or IMAP credentials set in .env; skipping.")
        return 0

    if not senders:
        print("[Reply Sync] No new campaign replies.")
        return 0

    c = sqlite3.connect(str(db_path), timeout=30.0)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA busy_timeout=30000;")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ph = ",".join("?" for _ in ACTIVE)
    tot = 0
    for em in sorted(senders):
        dom = re.sub(r"^www\.", "", em.split("@", 1)[1].lower())
        sql = (
            f"UPDATE leads SET status='REPLIED', updated_at=? WHERE status IN ({ph}) AND LOWER(COALESCE(contact_email,email))=?"
            if dom in FREE
            else f"UPDATE leads SET status='REPLIED', updated_at=? WHERE status IN ({ph}) AND (LOWER(domain)=? OR LOWER(COALESCE(contact_email,email))=?)"
        )
        cur = c.execute(sql, (now, *ACTIVE, em) if dom in FREE else (now, *ACTIVE, dom, em))
        if cur.rowcount > 0:
            c.commit()
            tot += cur.rowcount
            print(f"[Reply Sync] [+] Marked {cur.rowcount} lead(s) REPLIED from {em}")
    c.close()
    print(f"[Reply Sync] Done. Suppressed: {tot}")
    return tot


if __name__ == "__main__":
    sync_replies()

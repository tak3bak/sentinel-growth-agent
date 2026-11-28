#!/usr/bin/env python3
import email, imaplib, os, re, sqlite3
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parseaddr
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "leads.db"
ENV_PATH = BASE_DIR / ".env"
ACTIVE = ("DISPATCHED", "DISPATCHED_ACTIVE", "FOLLOWUP_SENT", "CONTACTED")
FREE = {"gmail.com","yahoo.com","outlook.com","hotmail.com","aol.com","icloud.com","proton.me","protonmail.com","comcast.net","msn.com","live.com"}

def load_env():
    if not ENV_PATH.exists(): return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def dec(val):
    if not val: return ""
    return "".join(c.decode(cs or "utf-8", errors="replace") if isinstance(c, bytes) else c for c, cs in decode_header(val)).strip()

def fetch_senders(host, port, user, pw, days=7):
    out = set()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
    with imaplib.IMAP4_SSL(host, port) as m:
        m.login(user, pw)
        m.select("INBOX", readonly=True)
        st, d = m.search(None, f'(SINCE "{since}")')
        if st != "OK" or not d or not d[0]: return out
        for mid in d[0].split():
            res, md = m.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM TO DELIVERED-TO SUBJECT IN-REPLY-TO AUTO-SUBMITTED)])")
            if res != "OK" or not md: continue
            msg = email.message_from_bytes(b"".join(p[1] for p in md if isinstance(p, tuple)))
            snd = parseaddr(msg.get("From", ""))[1].strip().lower()
            if not snd or "@" not in snd or snd == user.lower() or snd.endswith("@nomadik.site"): continue
            if (msg.get("Auto-Submitted") or "no").strip().lower() != "no": continue
            subj = dec(msg.get("Subject"))
            blob = " ".join([msg.get("To",""), msg.get("Delivered-To",""), msg.get("In-Reply-To",""), subj]).lower()
            if "nomadik.site" in blob or "perimeter exposure" in subj.lower() or msg.get("In-Reply-To"):
                out.add(snd)
    return out

def sync_replies(db_path=DB_PATH):
    load_env()
    u, pw = os.getenv("IMAP_USER","").strip(), os.getenv("IMAP_PASSWORD","").strip()
    if not u or not pw:
        print("[Reply Sync] IMAP_USER / IMAP_PASSWORD not set in .env; skipping.")
        return 0
    try:
        senders = fetch_senders(os.getenv("IMAP_HOST","imap.gmail.com").strip(), int(os.getenv("IMAP_PORT","993")), u, pw, int(os.getenv("REPLY_LOOKBACK_DAYS","7")))
    except Exception as e:
        print(f"[Reply Sync] [!] IMAP error: {e}")
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
        sql = f"UPDATE leads SET status='REPLIED', updated_at=? WHERE status IN ({ph}) AND LOWER(COALESCE(contact_email,email))=?" if dom in FREE else f"UPDATE leads SET status='REPLIED', updated_at=? WHERE status IN ({ph}) AND (LOWER(domain)=? OR LOWER(COALESCE(contact_email,email))=?)"
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

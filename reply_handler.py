import os, re, json, imaplib, email, sqlite3, requests
from email.header import decode_header

DB_PATH = os.getenv("DB_PATH", "leads.db")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASS = os.getenv("IMAP_PASS", "")
BREVO_KEY = os.getenv("BREVO_API_KEY", "")
OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
if not OLLAMA.startswith(("http://", "https://")):
    OLLAMA = f"http://{OLLAMA}"
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
SENDER = os.getenv("ALERT_EMAIL", "kalen@nomadik.site")

def decode_str(val):
    if not val: return ""
    parts = decode_header(val)
    return "".join(b.decode(enc or "utf-8", errors="ignore") if isinstance(b, bytes) else b for b, enc in parts)

def get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                return part.get_payload(decode=True).decode(errors="ignore")[:1500]
    elif msg.get_payload(decode=True):
        return msg.get_payload(decode=True).decode(errors="ignore")[:1500]
    return ""

def draft_reply(company, domain, incoming_text):
    prompt = (
        f"You are Kalen Vandenbos at Nomadik Security Operations (nomadik.site). "
        f"A prospect from {company} ({domain}) replied to our security audit:\n---\n{incoming_text}\n---\n"
        "Write a concise, helpful plain-text reply (under 100 words). Include our checkout link https://nomadik.site "
        "and tiers ($99/mo Core, $299/mo Compliance, $499/mo Active Defense, $1,299/mo Enterprise, or $500 Security Audit) if they ask about pricing. "
        "No placeholders, no HTML. Sign off: Kalen Vandenbos / Nomadik Security Operations."
    )
    r = requests.post(f"{OLLAMA}/api/generate", json={"model": MODEL, "prompt": prompt, "stream": False}, timeout=90)
    r.raise_for_status()
    return r.json().get("response", "").strip()

def send_brevo(to_email, subject, text):
    requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": BREVO_KEY, "Content-Type": "application/json"},
        json={"sender": {"name": "Kalen Vandenbos", "email": SENDER}, "to": [{"email": to_email}], "subject": subject, "textContent": text},
        timeout=20,
    ).raise_for_status()

def main():
    if not (IMAP_USER and IMAP_PASS and BREVO_KEY):
        return
    conn = sqlite3.connect(DB_PATH)
    imap = imaplib.IMAP4_SSL(IMAP_HOST, 993)
    imap.login(IMAP_USER, IMAP_PASS)
    imap.select("INBOX")
    _, nums = imap.search(None, "UNSEEN")
    for num in nums[0].split():
        _, data = imap.fetch(num, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])
        frm = email.utils.parseaddr(msg.get("From", ""))[1].lower()
        if "@" not in frm or frm.endswith("nomadik.site"):
            continue
        dom = frm.split("@", 1)[1]
        row = conn.execute("SELECT id, company_name FROM leads WHERE domain=? AND status IN ('CONTACTED','FOLLOWUP_SENT','DISPATCHED_ACTIVE')", (dom,)).fetchone()
        if not row:
            continue
        subj = decode_str(msg.get("Subject", "Security Audit"))
        reply_subj = subj if subj.lower().startswith("re:") else f"Re: {subj}"
        body = draft_reply(row[1] or dom, dom, get_body(msg))
        if body and "[" not in body:
            send_brevo(frm, reply_subj, body)
            send_brevo(SENDER, f"[REPLY HANDLED] {dom}", f"From: {frm}\n\nAuto-reply sent:\n{body}")
            with conn:
                conn.execute("UPDATE leads SET status='REPLIED', updated_at=CURRENT_TIMESTAMP WHERE id=?", (row[0],))
            print(f"[reply] Auto-replied to {frm} ({dom})")
    imap.logout()
    conn.close()

if __name__ == "__main__":
    main()

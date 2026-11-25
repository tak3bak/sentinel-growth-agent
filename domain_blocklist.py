from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class BlockDecision:
    blocked: bool
    domain: str
    reason: Optional[str] = None
    matched_rule: Optional[str] = None
    remaining_seconds: float = 0.0


def normalize_domain(target: str) -> str:
    """Extract and normalize a lowercase hostname from a URL, email, or domain string."""
    raw = (target or "").strip().lower()
    if not raw:
        return ""

    if "@" in raw and "://" not in raw and "/" not in raw:
        raw = raw.split("@", 1)[1]

    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = parsed.hostname or raw.split("/", 1)[0].split(":", 1)[0]
    return host.strip(".")


class DomainBlocklist:
    """
    Domain filter supporting:
      1. Exact domain matches (e.g., "example.com")
      2. Subdomain suffix matches (e.g., ".amazonaws.com" or "*.amazonaws.com" matches "foo.amazonaws.com")
      3. Temporary cooldowns with TTL expiration (e.g., after HTTP 429/403/503 or WAF challenges)
    """

    def __init__(
        self,
        exact_domains: Optional[Iterable[str]] = None,
        suffix_domains: Optional[Iterable[str]] = None,
        db_path: Optional[str | Path] = None,
    ) -> None:
        self.exact_domains: dict[str, str] = {}
        self.suffix_domains: dict[str, str] = {}
        self.cooldowns: dict[str, tuple[float, str]] = {}
        self.db_path: Optional[Path] = Path(db_path) if db_path else None

        if self.db_path:
            self._init_db()
            self._load_cooldowns_from_db()

        if exact_domains:
            for item in exact_domains:
                self.add_exact(item, reason="config_exact")

        if suffix_domains:
            for item in suffix_domains:
                self.add_suffix(item, reason="config_suffix")

    def _connect(self) -> sqlite3.Connection:
        assert self.db_path is not None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS domain_cooldowns (
                    domain TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def _load_cooldowns_from_db(self) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute("DELETE FROM domain_cooldowns WHERE expires_at <= ?", (now,))
            rows = conn.execute(
                "SELECT domain, reason, expires_at FROM domain_cooldowns WHERE expires_at > ?",
                (now,),
            ).fetchall()
            conn.commit()
        for domain, reason, expires_at in rows:
            self.cooldowns[domain] = (float(expires_at), str(reason))

    def _persist_cooldown(self, domain: str, reason: str, expires_at: float) -> None:
        if not self.db_path:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO domain_cooldowns (domain, reason, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    reason = excluded.reason,
                    expires_at = excluded.expires_at
                """,
                (domain, reason, expires_at),
            )
            conn.commit()

    def _delete_cooldown(self, domain: str) -> None:
        if not self.db_path:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM domain_cooldowns WHERE domain = ?", (domain,))
            conn.commit()

    @staticmethod
    def _clean_suffix(suffix: str) -> str:
        s = suffix.strip().lower()
        if s.startswith("*."):
            s = s[1:]
        if not s.startswith("."):
            s = f".{s}"
        return s.rstrip(".") + "." if s.endswith(".") else s

    def add_exact(self, domain: str, reason: str = "blocked_exact") -> None:
        norm = normalize_domain(domain)
        if norm:
            self.exact_domains[norm] = reason

    def add_suffix(self, suffix: str, reason: str = "blocked_suffix") -> None:
        cleaned = self._clean_suffix(suffix)
        if len(cleaned) > 1:
            self.suffix_domains[cleaned] = reason

    def add_cooldown(
        self,
        target: str,
        ttl_seconds: float,
        reason: str = "cooldown",
        include_parent_domain: bool = False,
    ) -> None:
        norm = normalize_domain(target)
        if not norm or ttl_seconds <= 0:
            return

        candidate = norm
        if include_parent_domain:
            parts = norm.split(".")
            if len(parts) > 2:
                candidate = ".".join(parts[-2:])

        expires_at = time.time() + float(ttl_seconds)
        self.cooldowns[candidate] = (expires_at, reason)
        self._persist_cooldown(candidate, reason, expires_at)

    def clear_cooldown(self, target: str) -> None:
        norm = normalize_domain(target)
        if norm in self.cooldowns:
            del self.cooldowns[norm]
            self._delete_cooldown(norm)

    def purge_expired_cooldowns(self) -> int:
        now = time.time()
        expired = [d for d, (exp, _) in self.cooldowns.items() if exp <= now]
        for d in expired:
            del self.cooldowns[d]
        if expired and self.db_path:
            with self._connect() as conn:
                conn.execute("DELETE FROM domain_cooldowns WHERE expires_at <= ?", (now,))
                conn.commit()
        return len(expired)

    def check(self, target: str, check_ancestors_for_cooldown: bool = True) -> BlockDecision:
        host = normalize_domain(target)
        if not host:
            return BlockDecision(blocked=True, domain="", reason="invalid_target", matched_rule="empty")

        if host in self.exact_domains:
            return BlockDecision(
                blocked=True,
                domain=host,
                reason=self.exact_domains[host],
                matched_rule=f"exact:{host}",
            )

        for suffix, reason in self.suffix_domains.items():
            bare = suffix.lstrip(".")
            if host != bare and host.endswith(suffix):
                return BlockDecision(
                    blocked=True,
                    domain=host,
                    reason=reason,
                    matched_rule=f"suffix:{suffix}",
                )

        now = time.time()
        candidates = [host]
        if check_ancestors_for_cooldown:
            labels = host.split(".")
            for i in range(1, len(labels) - 1):
                candidates.append(".".join(labels[i:]))

        for cand in candidates:
            entry = self.cooldowns.get(cand)
            if entry is not None:
                expires_at, reason = entry
                if expires_at > now:
                    return BlockDecision(
                        blocked=True,
                        domain=host,
                        reason=reason,
                        matched_rule=f"cooldown:{cand}",
                        remaining_seconds=round(expires_at - now, 2),
                    )
                del self.cooldowns[cand]
                self._delete_cooldown(cand)

        return BlockDecision(blocked=False, domain=host)

    def is_blocked(self, target: str) -> bool:
        return self.check(target).blocked

    def filter_targets(self, targets: Iterable[str]) -> tuple[list[str], list[BlockDecision]]:
        allowed: list[str] = []
        blocked: list[BlockDecision] = []
        for t in targets:
            decision = self.check(t)
            if decision.blocked:
                blocked.append(decision)
            else:
                allowed.append(t)
        return allowed, blocked

    @classmethod
    def from_json_file(cls, path: str | Path, db_path: Optional[str | Path] = None) -> "DomainBlocklist":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        blocklist = cls(db_path=db_path)

        exact = data.get("exact", {})
        if isinstance(exact, dict):
            for dom, reason in exact.items():
                blocklist.add_exact(dom, reason=str(reason))
        elif isinstance(exact, list):
            for dom in exact:
                blocklist.add_exact(str(dom), reason="exact_list")

        suffixes = data.get("suffixes", {})
        if isinstance(suffixes, dict):
            for sfx, reason in suffixes.items():
                blocklist.add_suffix(sfx, reason=str(reason))
        elif isinstance(suffixes, list):
            for sfx in suffixes:
                blocklist.add_suffix(str(sfx), reason="suffix_list")

        return blocklist


if __name__ == "__main__":
    bl = DomainBlocklist(
        exact_domains=["google.com", "linkedin.com", "nomadik.site"],
        suffix_domains=[".amazonaws.com", ".cloudflare.com", ".gov"],
        db_path="data/scraper_cooldowns.sqlite",
    )

    bl.add_cooldown("api.target-vendor.io", ttl_seconds=30, reason="http_429_backoff")

    samples = [
        "https://www.google.com/search?q=test",
        "https://s3-us-west-2.amazonaws.com/bucket/file.json",
        "https://portal.agency.gov/info",
        "https://api.target-vendor.io/v1/items",
        "https://prospect-shop.example.org/products",
    ]

    for url in samples:
        res = bl.check(url)
        print(f"{url} -> blocked={res.blocked} reason={res.reason} rule={res.matched_rule} rem={res.remaining_seconds}s")

from __future__ import annotations

import time

from auto_scraper import record_http_cooldown
from domain_blocklist import DomainBlocklist


def test_exact_and_suffix_matching_and_normalization(tmp_path) -> None:
    cfg = tmp_path / "blocklist.json"
    cfg.write_text(
        """
        {
          "exact": {"nomadik.site": "self_domain", "cloudflare.com": "infra_noise"},
          "suffixes": {".google.com": "walled_garden", ".amazonaws.com": "cloud_infra"}
        }
        """,
        encoding="utf-8",
    )
    bl = DomainBlocklist.from_json_file(cfg)

    assert bl.check("https://nomadik.site/audit").blocked is True
    assert bl.check("https://nomadik.site/audit").matched_rule == "exact:nomadik.site"
    assert bl.check("security@cloudflare.com").blocked is True
    assert bl.check("https://sub.google.com/search").blocked is True
    assert bl.check("https://sub.google.com/search").matched_rule == "suffix:.google.com"
    assert bl.check("bucket.s3.amazonaws.com").blocked is True
    assert bl.check("https://prospect-firm.example.com").blocked is False


def test_cooldown_ttl_and_sqlite_persistence(tmp_path) -> None:
    db_file = tmp_path / "cooldowns.sqlite"
    bl1 = DomainBlocklist(db_path=db_file)
    bl1.add_cooldown("api.vendor.io", ttl_seconds=1.5, reason="http_429")

    d1 = bl1.check("https://api.vendor.io/v1/data")
    assert d1.blocked is True
    assert d1.reason == "http_429"
    assert d1.remaining_seconds > 0

    bl2 = DomainBlocklist(db_path=db_file)
    assert bl2.is_blocked("api.vendor.io") is True

    time.sleep(1.6)
    assert bl2.is_blocked("api.vendor.io") is False
    assert bl2.purge_expired_cooldowns() == 0


def test_record_http_cooldown_honors_retry_after(monkeypatch, tmp_path) -> None:
    import auto_scraper

    fresh_bl = DomainBlocklist(db_path=tmp_path / "http_cd.sqlite")
    monkeypatch.setattr(auto_scraper, "BLOCKLIST", fresh_bl)

    assert record_http_cooldown("https://example.org/test", 200) is False
    assert record_http_cooldown("https://sub.throttle.example.org/api", 429, "12") is True

    decision = fresh_bl.check("https://sub.throttle.example.org/api")
    assert decision.blocked is True
    assert decision.reason == "http_429"
    assert decision.matched_rule == "cooldown:example.org"
    assert 0 < decision.remaining_seconds <= 12.0

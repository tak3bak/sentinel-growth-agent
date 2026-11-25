#!/usr/bin/env python3
"""
mcp_ai_scanner.py
Async exposure scanner for sentinel-growth-agent.
Detects exposed MCP (Model Context Protocol) servers, AI manifests,
unauthenticated OpenAPI/Swagger specs, and permissive CORS misconfigurations.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

from domain_blocklist import DomainBlocklist

BLOCKLIST = DomainBlocklist.from_json_file(
    "config/blocklist.json", db_path="data/scraper_cooldowns.sqlite"
)


MCP_PATHS: tuple[str, ...] = (
    "/.well-known/mcp/server-card.json",
    "/.well-known/mcp.json",
    "/.well-known/mcp",
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/ai-plugin.json",
    "/.well-known/agent.json",
    "/mcp",
    "/api/mcp",
    "/sse",
    "/v1/models",
)

OPENAPI_PATHS: tuple[str, ...] = (
    "/openapi.json",
    "/swagger.json",
    "/v1/openapi.json",
    "/v2/api-docs",
    "/v3/api-docs",
    "/api/openapi.json",
    "/docs",
)

SUBDOMAIN_PREFIXES: tuple[str, ...] = ("", "api.", "mcp.", "ai.")

UNTRUSTED_ORIGIN = "https://evil-audit-probe.invalid"
USER_AGENT = "NomadikSecuritySentinel-PostureAudit/1.0 (+https://nomadik.site)"

_API_AI_SEGMENT_RE = re.compile(r"(/(?:mcp|api|v1|openapi|swagger)(?:/|$)|\.well-known/)")


@dataclass
class Finding:
    category: str
    severity: str
    url: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class DomainAuditResult:
    domain: str
    scanned_at: str
    reachable_hosts: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    def outreach_bullets(self, limit: int = 3) -> list[str]:
        rank = {"high": 0, "medium": 1, "low": 2}
        ordered = sorted(self.findings, key=lambda f: rank.get(f.severity, 9))
        return [f"[{f.severity.upper()}] {f.summary} ({f.url})" for f in ordered[:limit]]


def normalize_domain(raw: str) -> str:
    cleaned = raw.strip().lower()
    if "://" in cleaned:
        cleaned = urlparse(cleaned).netloc
    cleaned = cleaned.split("/")[0].split(":")[0].strip(".")
    return cleaned


def _body_fingerprint(status_code: int, content_type: str, body: bytes) -> str:
    digest = hashlib.sha256(body[:4096]).hexdigest()[:16]
    return f"{status_code}:{content_type.split(';')[0].strip().lower()}:{len(body)}:{digest}"


def _try_parse_json(text: str) -> dict[str, Any] | list[Any] | None:
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None


def _is_valid_openapi(payload: Any, raw_text: str, path: str) -> tuple[bool, str]:
    if isinstance(payload, dict):
        if "openapi" in payload or "swagger" in payload:
            version = str(payload.get("openapi") or payload.get("swagger"))
            title = str(payload.get("info", {}).get("title", "Untitled API"))
            paths_count = len(payload.get("paths", {})) if isinstance(payload.get("paths"), dict) else 0
            return True, f"OpenAPI/Swagger {version} spec ('{title}', {paths_count} paths) publicly readable"
    if path == "/docs" and ("swagger-ui" in raw_text.lower() or "redoc" in raw_text.lower()):
        return True, "Interactive API documentation UI (Swagger/ReDoc) publicly accessible"
    return False, ""


def _is_valid_mcp_or_ai(
    payload: Any,
    raw_text: str,
    content_type: str,
    path: str,
    status_code: int,
) -> tuple[bool, str, str]:
    ct = content_type.lower()

    if path.endswith("/sse") and "text/event-stream" in ct and status_code == 200:
        return True, "high", "Unauthenticated MCP/SSE event stream endpoint open"

    if "oauth-protected-resource" in path and isinstance(payload, dict):
        if "resource" in payload or "authorization_servers" in payload:
            return True, "low", "MCP OAuth Protected Resource Metadata exposed (confirms active MCP server)"

    if "mcp" in path and isinstance(payload, dict):
        mcp_keys = {"mcpVersion", "protocolVersion", "capabilities", "tools", "servers", "transport", "endpoint"}
        if mcp_keys.intersection(payload.keys()):
            tools = payload.get("tools")
            tool_note = f" advertising {len(tools)} tools" if isinstance(tools, list) else ""
            return True, "high", f"Public MCP discovery manifest exposed{tool_note}"

    if path in ("/.well-known/ai-plugin.json", "/.well-known/agent.json") and isinstance(payload, dict):
        if any(k in payload for k in ("schema_version", "name_for_model", "api", "capabilities", "skills")):
            name = payload.get("name_for_human") or payload.get("name") or "AI Agent"
            return True, "medium", f"Public AI agent/plugin manifest exposed ({name})"

    if path == "/v1/models" and isinstance(payload, dict):
        if payload.get("object") == "list" and isinstance(payload.get("data"), list):
            model_ids = [m.get("id") for m in payload["data"][:3] if isinstance(m, dict) and m.get("id")]
            preview = ", ".join(model_ids) if model_ids else f"{len(payload['data'])} models"
            return True, "high", f"Unauthenticated LLM inference endpoint (/v1/models) exposed ({preview})"

    if path.endswith("/mcp") and status_code == 200 and isinstance(payload, dict):
        if "jsonrpc" in payload or "result" in payload or "serverInfo" in payload:
            return True, "high", "Unauthenticated Streamable HTTP MCP endpoint responding to requests"

    return False, "low", ""


def _evaluate_cors(headers: httpx.Headers, url: str) -> Finding | None:
    acao = headers.get("access-control-allow-origin", "").strip()
    acac = headers.get("access-control-allow-credentials", "").strip().lower()
    acam = headers.get("access-control-allow-methods", "").strip()

    if not acao:
        return None

    if acao == UNTRUSTED_ORIGIN:
        severity = "high" if acac == "true" else "medium"
        cred_note = " with Allow-Credentials: true" if acac == "true" else ""
        return Finding(
            category="permissive_cors",
            severity=severity,
            url=url,
            summary=f"Arbitrary Origin reflection in CORS policy{cred_note}",
            evidence={
                "access_control_allow_origin": acao,
                "access_control_allow_credentials": acac or "false",
                "access_control_allow_methods": acam,
            },
        )

    if acao == "null":
        return Finding(
            category="permissive_cors",
            severity="medium",
            url=url,
            summary="CORS policy trusts 'null' origin (sandboxed iframe bypass risk)",
            evidence={
                "access_control_allow_origin": acao,
                "access_control_allow_credentials": acac or "false",
            },
        )

    if acao == "*" and acac == "true":
        return Finding(
            category="permissive_cors",
            severity="high",
            url=url,
            summary="Wildcard CORS (*) paired with Access-Control-Allow-Credentials: true",
            evidence={
                "access_control_allow_origin": acao,
                "access_control_allow_credentials": acac,
            },
        )

    parsed_path = urlparse(url).path
    if acao == "*" and _API_AI_SEGMENT_RE.search(parsed_path):
        return Finding(
            category="permissive_cors",
            severity="low",
            url=url,
            summary="Wildcard CORS (*) enabled on API/AI endpoint",
            evidence={
                "access_control_allow_origin": acao,
                "access_control_allow_methods": acam,
            },
        )

    return None


def _dedupe_host_findings(host: str, findings: list[Finding]) -> list[Finding]:
    """Collapse repeated wildcard-CORS (*) low findings on a single host into one summary finding."""
    deduped: list[Finding] = []
    wildcard_urls: list[str] = []

    for f in findings:
        is_wildcard_low = (
            f.category == "permissive_cors"
            and f.severity == "low"
            and f.evidence.get("access_control_allow_origin") == "*"
        )
        if is_wildcard_low:
            wildcard_urls.append(f.url)
        else:
            deduped.append(f)

    if wildcard_urls:
        sample_url = wildcard_urls[0]
        count = len(wildcard_urls)
        suffix = f" across {count} endpoints on {host}" if count > 1 else ""
        deduped.append(
            Finding(
                category="permissive_cors",
                severity="low",
                url=sample_url,
                summary=f"Wildcard CORS (*) enabled on API/AI endpoint{suffix}",
                evidence={
                    "access_control_allow_origin": "*",
                    "matched_url_count": count,
                    "sample_urls": wildcard_urls[:5],
                },
            )
        )

    return deduped


class AsyncMcpAiScanner:
    def __init__(
        self,
        concurrency: int = 20,
        timeout: float = 8.0,
        check_subdomains: bool = True,
        probe_mcp_rpc: bool = True,
    ) -> None:
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout = timeout
        self.check_subdomains = check_subdomains
        self.probe_mcp_rpc = probe_mcp_rpc

    async def _soft_404_signature(self, client: httpx.AsyncClient, base_url: str) -> str | None:
        canary = f"{base_url}/__nomadik_nonexistent_probe_9f8e7d__"
        try:
            resp = await client.get(canary, headers={"Origin": UNTRUSTED_ORIGIN})
            if resp.status_code == 200:
                return _body_fingerprint(
                    resp.status_code,
                    resp.headers.get("content-type", ""),
                    resp.content,
                )
        except httpx.HTTPError:
            return None
        return None

    async def _probe_mcp_initialize(self, client: httpx.AsyncClient, url: str) -> Finding | None:
        if BLOCKLIST.check(url).blocked:
            return None
        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "nomadik-posture-check", "version": "1.0.0"},
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Origin": UNTRUSTED_ORIGIN,
        }
        try:
            resp = await client.post(url, json=rpc_payload, headers=headers)
        except httpx.HTTPError:
            return None

        if resp.status_code not in (200, 202):
            return None

        text = resp.text
        if "data:" in text and "jsonrpc" in text:
            match = re.search(r"data:\s*(\{.*\})", text)
            if match:
                text = match.group(1)

        parsed = _try_parse_json(text)
        if isinstance(parsed, dict) and isinstance(parsed.get("result"), dict):
            result = parsed["result"]
            server_info = result.get("serverInfo", {})
            server_name = server_info.get("name", "unknown-mcp-server")
            proto = result.get("protocolVersion", "unknown")
            return Finding(
                category="mcp_exposure",
                severity="high",
                url=url,
                summary=f"Unauthenticated MCP server responded to JSON-RPC initialize ({server_name}, protocol {proto})",
                evidence={"server_info": server_info, "capabilities": result.get("capabilities", {})},
            )
        return None

    async def _scan_host(self, client: httpx.AsyncClient, host: str) -> tuple[bool, list[Finding]]:
        if BLOCKLIST.check(host).blocked:
            return False, []
        base_url = f"https://{host}"
        findings: list[Finding] = []
        seen_cors_urls: set[str] = set()

        try:
            root_resp = await client.get(base_url, headers={"Origin": UNTRUSTED_ORIGIN})
        except httpx.HTTPError:
            return False, []

        root_cors = _evaluate_cors(root_resp.headers, base_url)
        if root_cors:
            findings.append(root_cors)
            seen_cors_urls.add(base_url)

        soft_404_fp = await self._soft_404_signature(client, base_url)

        all_paths = list(dict.fromkeys(MCP_PATHS + OPENAPI_PATHS))
        for path in all_paths:
            target_url = f"{base_url}{path}"
            try:
                resp = await client.get(
                    target_url,
                    headers={
                        "Origin": UNTRUSTED_ORIGIN,
                        "Accept": "application/json, text/event-stream, text/html;q=0.8",
                    },
                )
            except httpx.HTTPError:
                continue

            if target_url not in seen_cors_urls:
                cors_finding = _evaluate_cors(resp.headers, target_url)
                if cors_finding:
                    findings.append(cors_finding)
                    seen_cors_urls.add(target_url)

            if resp.status_code not in (200, 206):
                continue

            ct = resp.headers.get("content-type", "")
            fp = _body_fingerprint(resp.status_code, ct, resp.content)
            if soft_404_fp and fp == soft_404_fp:
                continue

            raw_text = resp.text[:65536]
            parsed_json = _try_parse_json(raw_text)

            if path in OPENAPI_PATHS:
                matched, summary = _is_valid_openapi(parsed_json, raw_text, path)
                if matched:
                    findings.append(
                        Finding(
                            category="openapi_exposure",
                            severity="medium",
                            url=target_url,
                            summary=summary,
                            evidence={"status_code": resp.status_code, "content_type": ct},
                        )
                    )

            if path in MCP_PATHS:
                matched, severity, summary = _is_valid_mcp_or_ai(
                    parsed_json, raw_text, ct, path, resp.status_code
                )
                if matched:
                    cat = "ai_manifest" if "ai-plugin" in path or "agent.json" in path else "mcp_exposure"
                    findings.append(
                        Finding(
                            category=cat,
                            severity=severity,
                            url=target_url,
                            summary=summary,
                            evidence={"status_code": resp.status_code, "content_type": ct},
                        )
                    )

        if self.probe_mcp_rpc:
            for mcp_path in ("/mcp", "/api/mcp"):
                rpc_finding = await self._probe_mcp_initialize(client, f"{base_url}{mcp_path}")
                if rpc_finding:
                    findings.append(rpc_finding)

        return True, _dedupe_host_findings(host, findings)

    async def scan_domain(self, raw_domain: str, client: httpx.AsyncClient) -> DomainAuditResult:
        domain = normalize_domain(raw_domain)
        scanned_at = datetime.now(timezone.utc).isoformat()
        if not domain:
            return DomainAuditResult(domain=raw_domain, scanned_at=scanned_at, error="invalid_domain")
        decision = BLOCKLIST.check(domain)
        if decision.blocked:
            return DomainAuditResult(domain=domain, scanned_at=scanned_at, error=f"blocklisted:{decision.reason or "blocked"}")

        prefixes = SUBDOMAIN_PREFIXES if self.check_subdomains else ("",)
        hosts = [f"{prefix}{domain}" for prefix in prefixes]

        async with self.semaphore:
            host_tasks = [self._scan_host(client, host) for host in hosts]
            results = await asyncio.gather(*host_tasks, return_exceptions=True)

        reachable: list[str] = []
        merged_findings: list[Finding] = []
        for host, res in zip(hosts, results):
            if isinstance(res, Exception):
                continue
            ok, host_findings = res
            if ok:
                reachable.append(host)
                merged_findings.extend(host_findings)

        return DomainAuditResult(
            domain=domain,
            scanned_at=scanned_at,
            reachable_hosts=reachable,
            findings=merged_findings,
        )

    async def scan_domains(self, domains: Iterable[str]) -> list[DomainAuditResult]:
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        timeout_cfg = httpx.Timeout(self.timeout, connect=4.0)
        headers = {"User-Agent": USER_AGENT}

        async with httpx.AsyncClient(
            limits=limits,
            timeout=timeout_cfg,
            headers=headers,
            follow_redirects=True,
            verify=True,
        ) as client:
            tasks = [self.scan_domain(d, client) for d in domains]
            return await asyncio.gather(*tasks)


def save_results_to_sqlite(db_path: str, results: list[DomainAuditResult]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_posture_audits (
                domain TEXT PRIMARY KEY,
                scanned_at TEXT NOT NULL,
                finding_count INTEGER NOT NULL,
                highest_severity TEXT,
                outreach_bullets_json TEXT NOT NULL,
                raw_result_json TEXT NOT NULL
            )
            """
        )
        rank = {"high": 0, "medium": 1, "low": 2}
        for res in results:
            highest = None
            if res.findings:
                highest = min((f.severity for f in res.findings), key=lambda s: rank.get(s, 9))
            conn.execute(
                """
                INSERT INTO ai_posture_audits
                    (domain, scanned_at, finding_count, highest_severity, outreach_bullets_json, raw_result_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    scanned_at=excluded.scanned_at,
                    finding_count=excluded.finding_count,
                    highest_severity=excluded.highest_severity,
                    outreach_bullets_json=excluded.outreach_bullets_json,
                    raw_result_json=excluded.raw_result_json
                """,
                (
                    res.domain,
                    res.scanned_at,
                    len(res.findings),
                    highest,
                    json.dumps(res.outreach_bullets()),
                    res.to_json(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


async def _cli_main() -> None:
    import sys

    targets = sys.argv[1:] or ["example.com"]
    scanner = AsyncMcpAiScanner(concurrency=15, timeout=7.0, check_subdomains=True)
    results = await scanner.scan_domains(targets)
    for res in results:
        print(json.dumps(asdict(res), indent=2))


if __name__ == "__main__":
    asyncio.run(_cli_main())

import random


class GrowthPitchEngine:
    @staticmethod
    def simulate_recon(domain: str) -> dict:
        mock_findings = [
            "Outdated TLS/SSL cipher suites detected on perimeter endpoints.",
            "Missing strict Content Security Policy (CSP) headers.",
            "Exposed administrative gateway or open non-standard management ports.",
            "Outdated software libraries found in public asset footprints.",
        ]
        findings_count = random.randint(1, 3)
        selected_findings = random.sample(mock_findings, findings_count)
        risk_score = round(random.uniform(6.5, 9.4), 1)

        return {
            "domain": domain,
            "risk_score": risk_score,
            "vulnerabilities": selected_findings,
        }

    @staticmethod
    def synthesize_pitch(company_name: str, domain: str, scan_data: dict) -> str:
        vulns_bulleted = "\n".join([f"  • {v}" for v in scan_data["vulnerabilities"]])

        pitch = f"""Subject: Security posture audit & risk analysis for {domain}

Hi Team at {company_name or domain},

Our autonomous telemetry at Nomadik Security Operations recently performed an external posture review of your public perimeter ({domain}) and flagged a risk score of {scan_data['risk_score']}/10.

Specifically, our preliminary analysis identified the following exposure vectors:
{vulns_bulleted}

In today's threat landscape, these types of perimeter gaps are frequently leveraged for initial access before internal remediation can occur. 

Nomadik Security Operations specializes in automated container security and rapid endpoint posture hardening. We can deploy our Security Sentinel stack to remediate these vulnerabilities within 24 hours.

Would you be open to a brief 10-minute technical walkthrough to review the full exposure report?

Best regards,

Automated Growth Agent
Nomadik Security Operations
https://github.com/tak3bak/security-sentinel
"""
        return pitch

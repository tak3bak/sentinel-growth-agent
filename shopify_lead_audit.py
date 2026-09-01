#!/usr/bin/env python3
import re
import csv
import time
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table

console = Console()

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')

DEFAULT_TARGETS = [
    "https://colourpop.com",
    "https://gymshark.com",
    "https://example.com"
]

def extract_emails_from_text(text, domain):
    raw_emails = EMAIL_REGEX.findall(text)
    clean_emails = set()
    ignored_ext = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js')
    
    for email in raw_emails:
        email = email.lower()
        if not any(email.endswith(ext) for ext in ignored_ext):
            if not any(placeholder in email for placeholder in ['sentry', 'wix', 'example', 'domain', 'support@shopify.com']):
                clean_emails.add(email)
    return list(clean_emails)

def audit_and_scrape_lead(base_url):
    if not base_url.startswith('http'):
        base_url = 'https://' + base_url

    parsed = urlparse(base_url)
    domain = parsed.netloc.replace('www.', '')
    company_name = domain.split('.')[0].capitalize()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    lead_data = {
        'email': '',
        'first_name': 'Team',
        'title': 'Operations Lead',
        'company': company_name,
        'pain_point': 'e-commerce endpoint security and attack surface visibility',
        'hook_angle': 'Nomadik Security Sentinel zero-telemetry daemon and automated auditing',
        'payment_link_tier': 'Founder Launch Bundle'
    }

    try:
        response = requests.get(base_url, headers=headers, timeout=8)
        soup = BeautifulSoup(response.content, 'html.parser')
        html_text = response.text

        is_shopify = 'cdn.shopify.com' in html_text.lower() or 'shopify' in html_text.lower()
        
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        mobile_ok = bool(viewport and 'width=device-width' in viewport.get('content', '').lower())

        generic_themes = ['dawn', 'debut', 'brooklyn', 'minimal', 'boundless', 'venture', 'sense', 'craft']
        theme_found = "Custom / Optimized"
        for theme in generic_themes:
            if theme in html_text.lower():
                theme_found = f"Basic ({theme.capitalize()})"
                lead_data['pain_point'] = f"vulnerabilities in {theme.capitalize()} theme assets and client-side tracking scripts"
                break

        if not mobile_ok:
            lead_data['pain_point'] = "unoptimized mobile assets and security header leaks"

        emails = extract_emails_from_text(html_text, domain)

        if not emails:
            contact_paths = ['/pages/contact', '/contact', '/contact-us', '/pages/about', '/about-us', '/pages/about-us']
            for path in contact_paths:
                sub_url = urljoin(base_url, path)
                try:
                    sub_res = requests.get(sub_url, headers=headers, timeout=5)
                    if sub_res.status_code == 200:
                        sub_emails = extract_emails_from_text(sub_res.text, domain)
                        if sub_emails:
                            emails.extend(sub_emails)
                            break
                except Exception:
                    continue

        if emails:
            chosen_email = sorted(emails, key=lambda x: (not x.startswith('contact'), not x.startswith('info'), not x.startswith('support')))[0]
            lead_data['email'] = chosen_email

        return lead_data, is_shopify, theme_found

    except Exception as e:
        console.print(f"[red][-] Failed to audit {base_url}: {e}[/red]")
        return None, False, "Error"

def main():
    console.print("[bold cyan][*] Running Lead Auditor & Target Generator...[/bold cyan]\n")
    
    table = Table(title="Audit & Contact Discovery")
    table.add_column("Company", style="green")
    table.add_column("Shopify", style="magenta")
    table.add_column("Theme / Profile", style="cyan")
    table.add_column("Discovered Contact", style="yellow")

    leads = []
    urls = DEFAULT_TARGETS
    
    for url in urls:
        console.print(f"[dim]Auditing {url}...[/dim]")
        lead_data, is_shopify, theme = audit_and_scrape_lead(url)
        if lead_data:
            contact_display = lead_data['email'] if lead_data['email'] else "[red]No email found[/red]"
            table.add_row(lead_data['company'], str(is_shopify), theme, contact_display)
            if lead_data['email']:
                leads.append(lead_data)
        time.sleep(1)

    console.print(table)

    if leads:
        output_file = 'target_leads.csv'
        fieldnames = ['email', 'first_name', 'title', 'company', 'pain_point', 'hook_angle', 'payment_link_tier']
        
        with open(output_file, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(leads)
            
        console.print(f"\n[bold green][+] Exported {len(leads)} qualified leads directly to {output_file}[/bold green]")
    else:
        console.print("\n[yellow][!] No valid email contacts discovered. You can also append manual rows to target_leads.csv.[/yellow]")

if __name__ == '__main__':
    main()

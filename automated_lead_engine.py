import requests
from bs4 import BeautifulSoup
import csv
from rich.console import Console
from rich.table import Table
import time
from duckduckgo_search import DDGS
from urllib.parse import urlparse

console = Console()

# Target local businesses that sell physical products but might have outdated websites.
# Simplified negative keywords to ensure broad reach without triggering empty search results
SEARCH_QUERY = 'boutique OR retail OR shop "denver" -site:yelp.com -site:facebook.com'
MAX_SEARCH_RESULTS = 20

def get_target_domains(query, max_results):
    console.print(f"[bold cyan]Scraping DuckDuckGo for potential clients:[/] {query}")
    domains = set()
    try:
        ddgs = DDGS()
        # Using the official wrapper avoids the strict rate limits of Google Search
        results = ddgs.text(query, max_results=max_results)
        
        for r in results:
            if 'href' in r:
                url = r['href']
                # Extract the base domain (e.g., https://example.com)
                parsed_uri = urlparse(url)
                base_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
                
                # Double-check to exclude massive non-target platforms
                if not any(x in base_url for x in ['wikipedia.org', 'yelp.', 'yellowpages.', 'mapquest.']):
                    domains.add(base_url)
                    
    except Exception as e:
        console.print(f"[bold red]Search error: {str(e)}[/bold red]")
    
    return list(domains)

def audit_store(url):
    try:
        if not url.startswith('http'):
            url = 'https://' + url
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
            
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        html_content = response.text.lower()
        
        # Detect Current E-commerce / Web Platform
        platform = "Unknown/Custom"
        if 'cdn.shopify.com' in html_content or 'shopify' in html_content:
            platform = "Shopify"
        elif 'wp-content' in html_content or 'wordpress' in html_content:
            if 'woocommerce' in html_content:
                platform = "WooCommerce"
            else:
                platform = "WordPress (No E-com)"
        elif 'wixsite.com' in html_content or 'wix.com' in html_content or 'x-wix' in response.headers:
            platform = "Wix"
        elif 'squarespace' in html_content:
            platform = "Squarespace"
            
        # Check standard mobile optimization tag
        mobile_optimized = False
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        if viewport and 'width=device-width' in viewport.get('content', '').lower():
            mobile_optimized = True
            
        return {
            'URL': url,
            'Platform': platform,
            'Mobile_Optimized': mobile_optimized,
            'Status': 'Success'
        }
        
    except Exception as e:
        return {
            'URL': url,
            'Platform': 'N/A',
            'Mobile_Optimized': False,
            'Status': f'Failed: {str(e)}'
        }

def main():
    console.print("[bold green]Initializing Sentinel Growth Agent Lead Generator...[/bold green]\n")
    
    # Step 1: Automatically find local domains
    target_urls = get_target_domains(SEARCH_QUERY, MAX_SEARCH_RESULTS)
    
    if not target_urls:
        console.print("[bold red]No targets found. The search query may have been blocked or returned empty.[/bold red]")
        return

    console.print(f"\n[bold green]Found {len(target_urls)} unique domains. Starting audit...[/bold green]\n")
    
    # Step 2: Audit the domains for their tech stack
    results = []
    for url in target_urls:
        console.print(f"Auditing {url}...")
        data = audit_store(url)
        
        if data['Status'] == 'Success':
            # Identify prime targets: Sites NOT on Shopify (migration pitch) OR lacking mobile optimization (upgrade pitch)
            opportunity = "Yes" if (data['Platform'] != 'Shopify' or not data['Mobile_Optimized']) else "Low"
            data['Pitch_Opportunity'] = opportunity
            results.append(data)
            
        time.sleep(2) # Be polite to avoid rate limits on the targets
        
    if not results:
        console.print("\n[bold yellow]No active stores could be reached in this batch.[/bold yellow]")
        return

    # Step 3: Export to CSV
    csv_filename = "growth_agent_leads.csv"
    keys = ['URL', 'Platform', 'Mobile_Optimized', 'Pitch_Opportunity', 'Status']
    with open(csv_filename, 'w', newline='', encoding='utf-8') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(results)
        
    console.print(f"\n[bold green]Audit complete! {len(results)} prospects saved to {csv_filename}[/bold green]\n")
    
    # Step 4: Display terminal table
    table = Table(title="Qualified Outbound Leads")
    table.add_column("URL", style="cyan")
    table.add_column("Current Stack", style="magenta")
    table.add_column("High-Value Target?", style="green")
    
    for r in results:
        # Highlight strong prospects in green, low prospects in yellow
        target_color = "[bold green]Yes[/]" if r['Pitch_Opportunity'] == "Yes" else "[yellow]Low[/]"
        table.add_row(str(r['URL']), str(r['Platform']), target_color)
        
    console.print(table)

if __name__ == "__main__":
    main()

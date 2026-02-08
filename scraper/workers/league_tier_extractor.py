"""Stage A: Deterministic league tier extraction using BeautifulSoup.

This module extracts competition tiers from Transfermarkt regional league index pages
without using LLM for HTML parsing. It:
1. Parses tier headers ("First Tier", "Second Tier", etc.)
2. Extracts competition rows under each tier
3. Normalizes URLs to transfermarkt.com
4. Outputs JSONL with source-of-truth tier assignments
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()


# Tier label to numeric tier mapping
TIER_MAP = {
    "First Tier": 1,
    "Second Tier": 2,
    "Third Tier": 3,
    "Fourth Tier": 4,
    "Fifth Tier": 5,
}


def normalize_to_com(url_or_path: str) -> str:
    """Convert any Transfermarkt URL to .com domain.
    
    Args:
        url_or_path: Full URL or path like /premier-league/startseite/wettbewerb/GB1
        
    Returns:
        Full URL with transfermarkt.com domain
    """
    if url_or_path.startswith('http'):
        # Extract path from full URL
        match = re.search(r'transfermarkt\.\w+(/.*)', url_or_path)
        if match:
            path = match.group(1)
        else:
            return url_or_path
    else:
        path = url_or_path
    
    # Ensure path starts with /
    if not path.startswith('/'):
        path = '/' + path
        
    return f"https://www.transfermarkt.com{path}"


def extract_competition_code(url_path: str) -> Optional[str]:
    """Extract competition code from URL path.
    
    Example: /premier-league/startseite/wettbewerb/GB1 -> GB1
    """
    match = re.search(r'/wettbewerb/([A-Z0-9]+)', url_path)
    return match.group(1) if match else None


def extract_country_from_row(row) -> Optional[str]:
    """Extract country from table row using flag image or title attributes.
    
    Args:
        row: BeautifulSoup tr element
        
    Returns:
        Country name or None
    """
    # Look for flag images with title/alt attributes
    img = row.find('img', class_='flaggenrahmen')
    if img:
        country = img.get('title') or img.get('alt')
        if country:
            return country.strip()
    
    # Fallback: look for any img with title in the row
    for img in row.find_all('img'):
        title = img.get('title') or img.get('alt')
        if title and len(title) > 2:  # Avoid single chars
            return title.strip()
    
    return None


def extract_league_index_rows(html: str, source_url: str) -> List[Dict[str, Any]]:
    """Extract competition rows with tier assignments from league index HTML.
    
    Args:
        html: Raw HTML from Transfermarkt league index page
        source_url: Source URL (europa or amerika page)
        
    Returns:
        List of competition dictionaries ready for JSONL output
    """
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    
    # Determine confederation from URL
    if 'europa' in source_url.lower():
        confederation = 'europa'
    elif 'amerika' in source_url.lower():
        confederation = 'amerika'
    else:
        confederation = 'unknown'
    
    # Find all table rows
    all_rows = soup.find_all('tr')
    
    current_tier_label = None
    current_tier = None
    in_tier_table = False
    
    logger.info("parsing_league_index", 
                confederation=confederation, 
                total_rows=len(all_rows))
    
    for row in all_rows:
        # Check if this is a tier header row
        # Tier headers are typically in td.extrarow elements
        extrarow = row.find('td', class_='extrarow')
        if extrarow:
            tier_text = extrarow.get_text(strip=True)
            
            # Check if this is a recognized tier label
            if tier_text in TIER_MAP:
                current_tier_label = tier_text
                current_tier = TIER_MAP[tier_text]
                in_tier_table = True
                logger.debug("found_tier_header", 
                           tier_label=current_tier_label, 
                           tier=current_tier)
                continue
            else:
                # Non-tier extrarow (might be end of tier section)
                # Continue tracking current tier until we find a new one
                pass
        
        # If we're in a tier section, look for competition links
        if in_tier_table and current_tier is not None:
            # Find competition link in this row
            # Competition links follow pattern: /competition-name/startseite/wettbewerb/CODE
            links = row.find_all('a', href=True)
            
            for link in links:
                href = link['href']
                
                # Match competition URLs
                if '/wettbewerb/' in href and '/startseite/' in href:
                    competition_code = extract_competition_code(href)
                    if not competition_code:
                        continue
                    
                    # Extract competition name from link text
                    competition_name = link.get_text(strip=True)
                    if not competition_name:
                        continue
                    
                    # Build URL path (ensure it's relative)
                    if href.startswith('http'):
                        # Extract path from full URL
                        match = re.search(r'transfermarkt\.\w+(/.*)', href)
                        url_path = match.group(1) if match else href
                    else:
                        url_path = href
                    
                    # Extract country from this row
                    country = extract_country_from_row(row)
                    
                    # Build competition record
                    record = {
                        "source_url": source_url,
                        "confederation": confederation,
                        "tier_label": current_tier_label,
                        "tier": current_tier,
                        "competition": {
                            "code": competition_code,
                            "name": competition_name,
                            "url_path": url_path,
                            "url_com": normalize_to_com(url_path),
                        },
                        "country": country,
                        "extracted_at": datetime.utcnow().isoformat() + 'Z',
                    }
                    
                    rows.append(record)
                    logger.debug("extracted_competition",
                               code=competition_code,
                               name=competition_name,
                               tier=current_tier,
                               country=country)
                    
                    # Only take the first valid competition link per row
                    break
    
    logger.info("extraction_complete",
               confederation=confederation,
               total_competitions=len(rows),
               tier_distribution={tier: sum(1 for r in rows if r['tier'] == tier) 
                                for tier in range(1, 6)})
    
    return rows


def write_jsonl(output_path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write rows to JSONL file.
    
    Args:
        output_path: Path to output JSONL file
        rows: List of dictionaries to write
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open('w', encoding='utf-8') as f:
        for row in rows:
            json_line = json.dumps(row, ensure_ascii=False)
            f.write(json_line + '\n')
    
    logger.info("wrote_jsonl",
               path=str(output_path),
               row_count=len(rows))


def generate_stage_a_report(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary report for Stage A extraction.
    
    Args:
        rows: Extracted competition rows
        
    Returns:
        Dictionary with summary statistics
    """
    by_confederation = {}
    by_tier = {}
    by_country = {}
    
    for row in rows:
        conf = row['confederation']
        tier = row['tier']
        country = row.get('country', 'Unknown')
        
        by_confederation[conf] = by_confederation.get(conf, 0) + 1
        by_tier[tier] = by_tier.get(tier, 0) + 1
        by_country[country] = by_country.get(country, 0) + 1
    
    return {
        "total_competitions": len(rows),
        "by_confederation": by_confederation,
        "by_tier": dict(sorted(by_tier.items())),
        "by_country": dict(sorted(by_country.items(), key=lambda x: -x[1])[:20]),  # Top 20
        "sample_records": rows[:3] if rows else [],
    }

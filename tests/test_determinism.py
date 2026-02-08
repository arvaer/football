"""Test HTML determinism for Transfermarkt pages.

Verifies that:
1. HTML fetches are stable across multiple requests
2. Page markers are present for each page type
3. No dynamic content that would prevent deterministic parsing
"""

import asyncio
import hashlib
import re
from typing import Dict, List, Tuple
import httpx
from bs4 import BeautifulSoup


# Test URLs for each page type
TEST_URLS = {
    "PLAYER_PROFILE": [
        "https://www.transfermarkt.com/erling-haaland/profil/spieler/418560",
        "https://www.transfermarkt.com/kylian-mbappe/profil/spieler/342229",
    ],
    "PLAYER_TRANSFERS": [
        "https://www.transfermarkt.com/erling-haaland/transfers/spieler/418560",
        "https://www.transfermarkt.com/kylian-mbappe/transfers/spieler/342229",
    ],
    "CLUB_TRANSFERS": [
        "https://www.transfermarkt.com/manchester-city/transfers/verein/281",
        "https://www.transfermarkt.com/real-madrid/transfers/verein/418",
    ],
    "CLUB_PROFILE": [
        "https://www.transfermarkt.com/manchester-city/startseite/verein/281",
        "https://www.transfermarkt.com/real-madrid/startseite/verein/418",
    ],
}

# Expected markers for each page type
PAGE_MARKERS = {
    "PLAYER_PROFILE": [
        "/profil/spieler/",
        "data-header",  # Player header
    ],
    "PLAYER_TRANSFERS": [
        "/transfers/spieler/",
        "table",  # Transfer table
    ],
    "CLUB_TRANSFERS": [
        "/transfers/verein/",
        "table",  # Transfer table
    ],
    "CLUB_PROFILE": [
        "/startseite/verein/",
        "data-header",  # Club header
    ],
}


def normalize_html(html: str) -> str:
    """Normalize HTML by removing dynamic content and collapsing whitespace."""
    # Remove script tags
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.find_all('script'):
        script.decompose()
    
    # Remove style tags
    for style in soup.find_all('style'):
        style.decompose()
    
    # Remove comments
    for comment in soup.find_all(string=lambda text: isinstance(text, str) and text.strip().startswith('<!--')):
        comment.extract()
    
    # Get text
    html_str = str(soup)
    
    # Remove timestamps and dynamic IDs
    html_str = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', 'TIMESTAMP', html_str)
    html_str = re.sub(r'id="[^"]*"', 'id="NORMALIZED"', html_str)
    
    # Collapse whitespace
    html_str = re.sub(r'\s+', ' ', html_str)
    
    return html_str.strip()


def hash_html(html: str) -> str:
    """Hash normalized HTML."""
    normalized = normalize_html(html)
    return hashlib.sha256(normalized.encode()).hexdigest()


async def fetch_html(url: str) -> str:
    """Fetch HTML from URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return response.text


def check_markers(html: str, page_type: str) -> Tuple[bool, List[str]]:
    """Check if expected markers are present in HTML."""
    markers = PAGE_MARKERS.get(page_type, [])
    missing = []
    
    for marker in markers:
        if marker not in html:
            missing.append(marker)
    
    return len(missing) == 0, missing


async def test_url_determinism(url: str, page_type: str) -> Dict:
    """Test determinism for a single URL."""
    print(f"\nTesting {page_type}: {url}")
    
    # Fetch twice with small delay
    html1 = await fetch_html(url)
    await asyncio.sleep(2)
    html2 = await fetch_html(url)
    
    # Hash both
    hash1 = hash_html(html1)
    hash2 = hash_html(html2)
    
    # Check markers
    has_markers, missing_markers = check_markers(html1, page_type)
    
    # Results
    is_deterministic = hash1 == hash2
    
    result = {
        "url": url,
        "page_type": page_type,
        "is_deterministic": is_deterministic,
        "hash1": hash1[:16],
        "hash2": hash2[:16],
        "has_markers": has_markers,
        "missing_markers": missing_markers,
        "html_size": len(html1),
    }
    
    # Print results
    status = "✓" if is_deterministic and has_markers else "✗"
    print(f"{status} {page_type}: deterministic={is_deterministic}, markers={has_markers}")
    
    if not is_deterministic:
        print(f"  ⚠ Hash mismatch: {hash1[:16]} != {hash2[:16]}")
    
    if not has_markers:
        print(f"  ⚠ Missing markers: {missing_markers}")
    
    return result


async def run_determinism_tests():
    """Run all determinism tests."""
    print("=" * 80)
    print("HTML Determinism Tests")
    print("=" * 80)
    
    all_results = []
    
    for page_type, urls in TEST_URLS.items():
        for url in urls:
            try:
                result = await test_url_determinism(url, page_type)
                all_results.append(result)
            except Exception as e:
                print(f"✗ ERROR testing {url}: {e}")
                all_results.append({
                    "url": url,
                    "page_type": page_type,
                    "error": str(e),
                })
    
    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    
    total = len(all_results)
    deterministic = sum(1 for r in all_results if r.get("is_deterministic", False))
    with_markers = sum(1 for r in all_results if r.get("has_markers", False))
    errors = sum(1 for r in all_results if "error" in r)
    
    print(f"Total tests: {total}")
    print(f"Deterministic: {deterministic}/{total}")
    print(f"Has markers: {with_markers}/{total}")
    print(f"Errors: {errors}/{total}")
    
    if deterministic == total - errors and with_markers == total - errors:
        print("\n✓ All tests passed!")
        return True
    else:
        print("\n✗ Some tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_determinism_tests())
    exit(0 if success else 1)

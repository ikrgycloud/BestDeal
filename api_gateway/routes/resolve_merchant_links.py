"""
Fast resolver: Extract real merchant links from SerpAPI immersive product API data.
This bypasses Selenium entirely by directly calling the SerpAPI endpoints.

Usage:
    python resolve_merchant_links.py

Input:  serpapi_data.json (with serpapi_immersive_product_api URLs)
Output: product_links_resolved.json (with actual merchant links)

Speed: ~1-2 minutes for 100+ items (parallel API calls, no browser overhead)
"""

import json
import os
import sys
import time
import random
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, urlencode, ParseResult

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
INPUT_FILE = "serpapi_data.json"
OUTPUT_FILE = "product_links_resolved.json"
SERPAPI_API_KEY = os.getenv("SERPAPI_KEY", "")
REQUEST_TIMEOUT = 15
CONCURRENCY = 8  # parallel API requests
MAX_RETRIES = 3


def _is_image_url(url: str) -> bool:
    """Check if URL points to an image."""
    if not url:
        return False
    url_lower = url.lower()
    image_indicators = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', 
                       'encrypted-tbn', 'gstatic.com/shopping', 'serpapi.com/images']
    return any(ind in url_lower for ind in image_indicators)


def _find_first_external_link(obj) -> Optional[str]:
    """Recursively find first non-Google, non-image external link in a JSON object."""
    if not obj:
        return None

    # If dict, search values
    if isinstance(obj, dict):
        # Prioritize fields that typically contain product/merchant links
        for key in ['link', 'product_link', 'url', 'shopping_results']:
            if key in obj:
                res = _find_first_external_link(obj[key])
                if res:
                    return res
        # Then check remaining keys
        for val in obj.values():
            res = _find_first_external_link(val)
            if res:
                return res
        return None

    # If list, iterate
    if isinstance(obj, list):
        for item in obj:
            res = _find_first_external_link(item)
            if res:
                return res
        return None

    # If string, check if it's a good URL
    if isinstance(obj, str):
        if obj.startswith('http://') or obj.startswith('https://'):
            if any(bad in obj.lower() for bad in ('google.com', 'serpapi.com', 'accounts.google.com')):
                return None
            if _is_image_url(obj):
                return None
            return obj
        return None

    return None


def resolve_item(item: dict) -> dict:
    """Call SerpAPI immersive product API and extract real merchant link."""
    position = item.get("position")
    title = item.get("title", "")[:40]
    api_url = item.get("serpapi_immersive_product_api")
    
    if not api_url:
        return {"position": position, "link": None, "status": "NO_API_URL"}

    try:
        # Add API key if not present
        parsed = urlparse(api_url)
        qs = parse_qs(parsed.query)
        if "api_key" not in qs:
            qs["api_key"] = [SERPAPI_API_KEY]
            new_query = urlencode(qs, doseq=True)
            api_url = ParseResult(parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment).geturl()

        # Call API with retries
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                response = requests.get(api_url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()
                
                # Extract merchant link from response
                link = _find_first_external_link(data)
                if link:
                    print(f"  ✓ Position {position}: {title} → {link[:60]}...")
                    return {"position": position, "link": link, "status": "RESOLVED"}
                else:
                    print(f"  ✗ Position {position}: {title} → No link found in API response")
                    return {"position": position, "link": None, "status": "NO_LINK_IN_RESPONSE"}
                    
            except requests.exceptions.Timeout:
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    wait = min(5 * (2 ** (retry_count - 1)), 30)
                    print(f"  ⏱ Position {position}: Timeout (retry {retry_count}/{MAX_RETRIES}, waiting {wait}s)")
                    time.sleep(wait)
                else:
                    print(f"  ✗ Position {position}: Timeout after {MAX_RETRIES} retries")
                    return {"position": position, "link": None, "status": "TIMEOUT"}
            except requests.exceptions.RequestException as e:
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    wait = min(3 * (2 ** (retry_count - 1)), 20)
                    print(f"  ⏱ Position {position}: API error: {str(e)[:50]} (retry {retry_count}/{MAX_RETRIES}, waiting {wait}s)")
                    time.sleep(wait)
                else:
                    print(f"  ✗ Position {position}: API error: {str(e)[:50]}")
                    return {"position": position, "link": None, "status": "API_ERROR"}
                    
    except Exception as e:
        print(f"  ✗ Position {position}: Unexpected error: {e}")
        return {"position": position, "link": None, "status": "ERROR"}


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        sys.exit(1)

    print(f"📥 Loading {INPUT_FILE}...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        items = json.load(f)
    
    print(f"📊 Found {len(items)} items. Starting parallel resolution with {CONCURRENCY} workers...")
    print(f"⏰ Est. time: 1-2 minutes for {len(items)} items\n")

    start_time = time.time()
    results = []
    stats = {"RESOLVED": 0, "NO_LINK_IN_RESPONSE": 0, "TIMEOUT": 0, "API_ERROR": 0, "NO_API_URL": 0, "ERROR": 0}

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(resolve_item, item): item for item in items}
        for fut in as_completed(futures):
            try:
                result = fut.result()
                results.append(result)
                stats[result["status"]] += 1
            except Exception as e:
                print(f"  ✗ Task failed: {e}")
                stats["ERROR"] += 1

    # Sort by position
    results.sort(key=lambda x: x["position"])

    # Save results
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    elapsed = time.time() - start_time
    print(f"\n✅ Done! Completed in {elapsed:.1f} seconds ({elapsed/60:.2f} minutes)")
    print(f"\n📈 Summary:")
    print(f"   ✓ Resolved:          {stats['RESOLVED']}/{len(items)}")
    print(f"   ✗ No link found:     {stats['NO_LINK_IN_RESPONSE']}")
    print(f"   ⏱ Timeout:           {stats['TIMEOUT']}")
    print(f"   ✗ API errors:        {stats['API_ERROR']}")
    print(f"   ✗ No API URL:        {stats['NO_API_URL']}")
    print(f"   ✗ Other errors:      {stats['ERROR']}")
    print(f"\n💾 Results saved to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()

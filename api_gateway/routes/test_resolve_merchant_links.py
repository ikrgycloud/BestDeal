"""
Test suite for resolve_merchant_links.py

Tests:
  1. File loading (serpapi_data.json exists and is valid JSON)
  2. Link extraction (_find_first_external_link finds valid URLs)
  3. Image URL filtering (_is_image_url filters out images)
  4. API resolution (resolves items correctly)
  5. Output validation (product_links_resolved.json has valid structure)

Run: python test_resolve_merchant_links.py
"""

import json
import os
import sys
import time
from urllib.parse import urlparse

# Import functions from resolve_merchant_links
sys.path.insert(0, os.path.dirname(__file__))
from resolve_merchant_links import _is_image_url, _find_first_external_link, resolve_item


def test_file_loading():
    """Test 1: serpapi_data.json loads correctly."""
    print("\n🔍 Test 1: File Loading")
    if not os.path.exists("serpapi_data.json"):
        print("  ✗ FAILED: serpapi_data.json not found")
        return False
    
    try:
        with open("serpapi_data.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list) or len(data) == 0:
            print("  ✗ FAILED: serpapi_data.json is empty or not a list")
            return False
        print(f"  ✓ PASSED: Loaded {len(data)} items from serpapi_data.json")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


def test_image_url_filtering():
    """Test 2: _is_image_url correctly identifies image URLs."""
    print("\n🔍 Test 2: Image URL Filtering")
    test_cases = [
        ("https://encrypted-tbn1.gstatic.com/shopping?q=test.jpg", True, "encrypted-tbn image"),
        ("https://example.com/image.png", True, "PNG image"),
        ("https://serpapi.com/images/something.jpg", True, "SerpAPI image"),
        ("https://www.amazon.com/product/123", False, "product page"),
        ("https://www.jiomart.com/product", False, "merchant page"),
    ]
    
    passed = 0
    for url, should_be_image, desc in test_cases:
        result = _is_image_url(url)
        if result == should_be_image:
            print(f"  ✓ {desc}: {url[:50]}... → {result}")
            passed += 1
        else:
            print(f"  ✗ {desc}: expected {should_be_image}, got {result}")
    
    print(f"  {passed}/{len(test_cases)} image filtering tests passed")
    return passed == len(test_cases)


def test_link_extraction():
    """Test 3: _find_first_external_link extracts valid links."""
    print("\n🔍 Test 3: Link Extraction")
    
    test_data = {
        "link": "https://ovantica.com/product",
        "product_link": "https://www.google.com/search?...",  # should skip google
        "thumbnail": "https://encrypted-tbn.com/image.jpg",  # should skip image
        "nested": {
            "url": "https://cliktodeal.com/product"
        }
    }
    
    link = _find_first_external_link(test_data)
    if link == "https://ovantica.com/product":
        print(f"  ✓ PASSED: Extracted correct link: {link}")
        return True
    else:
        print(f"  ✗ FAILED: Expected ovantica.com link, got {link}")
        return False


def test_google_link_skipping():
    """Test 4: Google URLs are skipped."""
    print("\n🔍 Test 4: Google URL Skipping")
    
    test_data = {
        "product_link": "https://www.google.com/search?ibp=oshop&q=test",
        "shopping_results": [
            {"link": "https://accounts.google.com/login"},  # skip
            {"link": "https://www.amazon.com/product"}     # use this
        ]
    }
    
    link = _find_first_external_link(test_data)
    if link == "https://www.amazon.com/product":
        print(f"  ✓ PASSED: Skipped Google links, found: {link}")
        return True
    else:
        print(f"  ✗ FAILED: Expected amazon.com, got {link}")
        return False


def test_output_file():
    """Test 5: product_links_resolved.json has valid structure."""
    print("\n🔍 Test 5: Output File Validation")
    
    if not os.path.exists("product_links_resolved.json"):
        print("  ✗ FAILED: product_links_resolved.json not found")
        print("           Run resolve_merchant_links.py first")
        return False
    
    try:
        with open("product_links_resolved.json", 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        if not isinstance(results, list):
            print("  ✗ FAILED: Output is not a list")
            return False
        
        if len(results) == 0:
            print("  ✗ FAILED: Output is empty")
            return False
        
        # Validate first few items
        issues = 0
        for i, item in enumerate(results[:5]):
            if "position" not in item:
                print(f"  ✗ Item {i}: Missing 'position'")
                issues += 1
            if "link" not in item:
                print(f"  ✗ Item {i}: Missing 'link'")
                issues += 1
            if "status" not in item:
                print(f"  ✗ Item {i}: Missing 'status'")
                issues += 1
            
            # Validate URL format
            if item.get("link"):
                try:
                    parsed = urlparse(item["link"])
                    if not parsed.scheme or not parsed.netloc:
                        print(f"  ✗ Item {i}: Invalid URL format: {item['link'][:50]}")
                        issues += 1
                except Exception as e:
                    print(f"  ✗ Item {i}: URL parsing error: {e}")
                    issues += 1
        
        if issues == 0:
            resolved_count = sum(1 for r in results if r.get("link"))
            print(f"  ✓ PASSED: {len(results)} items, {resolved_count} resolved")
            print(f"           Sample: {results[0]['link'][:60]}...")
            return True
        else:
            print(f"  ✗ FAILED: Found {issues} validation issues")
            return False
            
    except json.JSONDecodeError as e:
        print(f"  ✗ FAILED: Invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


def test_sample_resolution():
    """Test 6: Resolve a single item (requires API)."""
    print("\n🔍 Test 6: Sample Item Resolution (Live API)")
    
    try:
        with open("serpapi_data.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if len(data) == 0:
            print("  ⊘ SKIPPED: No items in serpapi_data.json")
            return True
        
        # Test first item
        item = data[0]
        print(f"  Testing: {item.get('title', 'Unknown')[:50]}...")
        
        result = resolve_item(item)
        
        if result["status"] == "RESOLVED" and result["link"]:
            print(f"  ✓ PASSED: Resolved to {result['link'][:60]}...")
            return True
        elif result["status"] == "NO_API_URL":
            print(f"  ⊘ SKIPPED: No API URL in item")
            return True
        else:
            print(f"  ✗ FAILED: Status={result['status']}")
            return False
            
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


def test_url_validity():
    """Test 7: All resolved links are valid HTTP/HTTPS URLs."""
    print("\n🔍 Test 7: URL Validity Check")
    
    if not os.path.exists("product_links_resolved.json"):
        print("  ⊘ SKIPPED: product_links_resolved.json not found")
        return True
    
    try:
        with open("product_links_resolved.json", 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        invalid_count = 0
        for item in results:
            link = item.get("link")
            if link:
                try:
                    parsed = urlparse(link)
                    if parsed.scheme not in ['http', 'https']:
                        print(f"  ✗ Invalid scheme: {link[:60]}")
                        invalid_count += 1
                    if not parsed.netloc:
                        print(f"  ✗ Missing domain: {link[:60]}")
                        invalid_count += 1
                except Exception as e:
                    print(f"  ✗ Parse error: {link[:60]} - {e}")
                    invalid_count += 1
        
        if invalid_count == 0:
            print(f"  ✓ PASSED: All {len(results)} URLs are valid")
            return True
        else:
            print(f"  ✗ FAILED: {invalid_count} invalid URLs")
            return False
            
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


def test_no_google_links():
    """Test 8: No Google Shopping links in output."""
    print("\n🔍 Test 8: Google Link Elimination")
    
    if not os.path.exists("product_links_resolved.json"):
        print("  ⊘ SKIPPED: product_links_resolved.json not found")
        return True
    
    try:
        with open("product_links_resolved.json", 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        google_count = 0
        for item in results:
            link = item.get("link", "")
            if "google.com" in link.lower():
                print(f"  ✗ Found Google link: {link[:60]}")
                google_count += 1
        
        if google_count == 0:
            print(f"  ✓ PASSED: No Google Shopping links in {len(results)} items")
            return True
        else:
            print(f"  ✗ FAILED: Found {google_count} Google links")
            return False
            
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


if __name__ == '__main__':
    print("=" * 70)
    print("MERCHANT LINK RESOLVER - TEST SUITE")
    print("=" * 70)
    
    tests = [
        test_file_loading,
        test_image_url_filtering,
        test_link_extraction,
        test_google_link_skipping,
        test_output_file,
        test_sample_resolution,
        test_url_validity,
        test_no_google_links,
    ]
    
    start_time = time.time()
    results = []
    
    for test_func in tests:
        try:
            result = test_func()
            results.append((test_func.__name__, result))
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append((test_func.__name__, False))
    
    elapsed = time.time() - start_time
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test_name}")
    
    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} tests passed (⏱ {elapsed:.2f}s)")
    print("=" * 70)
    
    sys.exit(0 if passed == total else 1)

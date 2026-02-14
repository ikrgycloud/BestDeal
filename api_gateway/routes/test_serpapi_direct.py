#!/usr/bin/env python3
"""
Quick test: Verify SerpAPI works with the embedded key
"""

import os
import sys

# Test 1: Check if SerpAPI package is installed
print("TEST 1: Checking if SerpAPI is installed...")
try:
    from serpapi import GoogleSearch
    print("  ✓ SerpAPI imported successfully")
except ImportError as e:
    print(f"  ✗ SerpAPI not installed: {e}")
    print("  Install with: pip install google-search-results")
    sys.exit(1)

# Test 2: Check API key
print("\nTEST 2: Checking embedded API key...")
api_key = "f5d068e7bd4a90adcfc1198937a7cf64f02a3b8ddfd11a453c214092306043fd"
print(f"  API Key: {api_key[:20]}...{api_key[-10:]}")

# Test 3: Make a simple search
print("\nTEST 3: Testing SerpAPI with a simple search...")
try:
    params = {
        "engine": "google_shopping",
        "q": "laptop",
        "location": "India",
        "hl": "en",
        "gl": "in",
        "api_key": api_key
    }
    print(f"  Calling SerpAPI with params: {params}")
    search = GoogleSearch(params)
    results = search.get_dict()
    
    print(f"  Response keys: {list(results.keys())}")
    
    if "error" in results:
        print(f"  ✗ ERROR from SerpAPI: {results['error']}")
        sys.exit(1)
    
    shopping_results = results.get("shopping_results", [])
    print(f"  ✓ Got {len(shopping_results)} shopping results")
    
    if shopping_results:
        first = shopping_results[0]
        print(f"\n  First result:")
        print(f"    Title: {first.get('title')}")
        print(f"    Price: {first.get('price')}")
        print(f"    Source: {first.get('source')}")
        print(f"    Position: {first.get('position')}")
        print(f"    Product Link: {first.get('product_link', 'N/A')[:60]}...")
    else:
        print("  ⚠ No shopping results returned")
        if "related_searches" in results:
            print(f"    But got {len(results['related_searches'])} related searches")
        if "knowledge_graph" in results:
            print(f"    And knowledge_graph data")
    
    print("\n✅ SerpAPI TEST PASSED")
    
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

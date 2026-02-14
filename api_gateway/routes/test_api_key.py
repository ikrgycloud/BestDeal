#!/usr/bin/env python3
"""Test the SerpAPI key to verify it's working."""

from serpapi import GoogleSearch

SERPAPI_KEY = "f5d068e7bd4a90adcfc1198937a7cf64f02a3b8ddfd11a453c214092306043fd"

params = {
    "engine": "google_shopping",
    "q": "iPhone 13",
    "location": "India",
    "hl": "en",
    "gl": "in",
    "api_key": SERPAPI_KEY
}

print("Testing SerpAPI with your key...")
search = GoogleSearch(params)
results = search.get_dict()

if "error" in results:
    print(f"ERROR: {results['error']}")
elif "shopping_results" in results:
    count = len(results["shopping_results"])
    print(f"✓ SUCCESS: Found {count} products")
    if count > 0:
        first = results["shopping_results"][0]
        print(f"  First result: {first.get('title', 'N/A')[:70]}")
        print(f"  Price: {first.get('price', 'N/A')}")
else:
    print(f"Response keys: {list(results.keys())}")

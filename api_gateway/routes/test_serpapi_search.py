from serpapi import GoogleSearch
import json

params = {
  "engine": "google_shopping",
  "q": "iphone",
  "location": "India",
  "hl": "en",
  "gl": "in",
  "api_key": "bbbc428409fd1b5ca4f895d1839ff9c5ce2ce72f1995133218dce1a56ed894a2"
}

search = GoogleSearch(params)
results = search.get_dict()
shopping_results = results.get("shopping_results", [])

with open("serpapi_data.json", "w") as f:
    json.dump(shopping_results, f, indent=4)
    print("Data saved to serpapi_data.json")
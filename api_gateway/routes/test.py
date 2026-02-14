import json
import requests
from bs4 import BeautifulSoup
import time
import os
import random

def main():
    input_filename = "serpapi_data.json"
    output_filename = "product_links.json"

    # Check if the input file exists
    if not os.path.exists(input_filename):
        print(f"Error: {input_filename} not found.")
        return

    # Load the JSON data
    with open(input_filename, 'r', encoding='utf-8') as f:
        data = json.load(f)

    extracted_results = []
    
    # List of User-Agents to rotate
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.5790.170 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"
    ]

    # Rotate Accept-Language values as another small fingerprint variation
    accept_languages = [
        "en-US,en;q=0.5",
        "en-GB,en;q=0.5",
        "en;q=0.8"
    ]

    # Use a session for connection pooling
    session = requests.Session()

    print(f"Starting scraping for {len(data)} items...")

    for item in data:
        position = item.get("position")
        product_link = item.get("link")

        if product_link and "google.com" in product_link:
            print(f"Processing Position {position}...")
            
            # Rotate headers for each request (UA + Accept-Language)
            headers = {
                "User-Agent": random.choice(user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": random.choice(accept_languages),
                "Referer": "https://www.google.com/"
            }

            # Retry loop with exponential backoff + jitter
            max_retries = 5
            backoff_base = 5  # seconds
            response = None
            for attempt in range(1, max_retries + 1):
                try:
                    response = session.get(product_link, headers=headers, timeout=15)

                    if response.status_code == 200:
                        break

                    if response.status_code == 429:
                        wait = min(backoff_base * (2 ** (attempt - 1)), 300)
                        # add jitter
                        wait += random.uniform(0, wait * 0.25)
                        print(f"  [!] 429 Too Many Requests. Backing off {wait:.1f}s (attempt {attempt}/{max_retries})")
                        time.sleep(wait)
                        # rotate headers for the next attempt
                        headers["User-Agent"] = random.choice(user_agents)
                        headers["Accept-Language"] = random.choice(accept_languages)
                        continue

                    print(f"  Failed to load page. Status: {response.status_code}")
                    break

                except requests.RequestException as e:
                    wait = min(backoff_base * (2 ** (attempt - 1)), 60)
                    print(f"  Request error: {e}. Retrying in {wait:.1f}s (attempt {attempt}/{max_retries})")
                    time.sleep(wait)
                    # rotate headers and retry
                    headers["User-Agent"] = random.choice(user_agents)
                    headers["Accept-Language"] = random.choice(accept_languages)
                    continue

            if response and response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Search for the specific div class provided by the user
                # <div class="sCXXQd" ...>
                target_div = soup.find("div", class_="sCXXQd")

                if target_div:
                    # Find the anchor tag inside the div
                    a_tag = target_div.find("a")
                    if a_tag and a_tag.get("href"):
                        href = a_tag.get("href")
                        print(f"  Found href: {href}")

                        extracted_results.append({
                            "position": position,
                            "link": href
                        })

                        # Save partial results every 5 items to avoid losing progress
                        if len(extracted_results) % 5 == 0:
                            with open(output_filename, 'w', encoding='utf-8') as f:
                                json.dump(extracted_results, f, indent=4)
                    else:
                        print("  Anchor tag or href not found in target div.")
                else:
                    print("  Target div (class='sCXXQd') not found.")
            else:
                print("  Skipping item due to repeated failures.")

            # Polite delay (randomized, increased)
            delay = random.uniform(6, 15)
            time.sleep(delay)

    # Save the extracted data to a new JSON file
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(extracted_results, f, indent=4)
    
    print(f"Scraping complete. Results saved to {output_filename}")

if __name__ == "__main__":
    main()
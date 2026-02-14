#!/usr/bin/env python3
"""
Temporary workaround: Worker without SerpAPI (using Selenium fallback only).
This allows you to get product data while waiting for SerpAPI credits.
"""

import pika
import os
import re
import json
import time
import random
import smtplib
import jwt
import datetime
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from email.mime.text import MIMEText

try:
    from scraper_worker import start_driver, process_item, SERPAPI_API_KEY as SW_SERPAPI_KEY
    SELENIUM_AVAILABLE = True
except Exception as e:
    print(f"[WARNING] Selenium fallback not available: {e}")
    SELENIUM_AVAILABLE = False
    SW_SERPAPI_KEY = None

from database import AuthDatabase

# Initialize Database
db = AuthDatabase()
db.setup_database()

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key")

# Cache for resolved merchant links
RESOLVED_LINKS_CACHE = {}


def load_resolved_links():
    """Load pre-resolved merchant links from product_links_resolved.json."""
    global RESOLVED_LINKS_CACHE
    try:
        if os.path.exists("product_links_resolved.json"):
            with open("product_links_resolved.json", "r", encoding="utf-8") as f:
                resolved_data = json.load(f)
            RESOLVED_LINKS_CACHE = {item["position"]: item["link"] for item in resolved_data if item.get("link")}
            print(f"[CACHE] Loaded {len(RESOLVED_LINKS_CACHE)} pre-resolved merchant links")
            return RESOLVED_LINKS_CACHE
    except Exception as e:
        print(f"[!] Error loading resolved links: {e}")
    return {}


def get_resolved_link(position):
    """Retrieve a pre-resolved link by position."""
    return RESOLVED_LINKS_CACHE.get(position)


def search_google_shopping(keyword, connection=None):
    """
    FALLBACK MODE: Searches Google Shopping using Selenium only.
    Skips SerpAPI entirely - uses browser-based scraping.
    """
    try:
        print(f"[FALLBACK] Searching Google Shopping for: {keyword} (SerpAPI unavailable)")
        
        # Load pre-resolved merchant links
        resolved_links = load_resolved_links()
        print(f"[DEBUG] Using {len(resolved_links)} pre-resolved links from cache")
        
        products = []
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        ]

        # Session setup for scraping fallback only
        session = requests.Session()
        retry = Retry(total=2, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        # Build search URL directly (bypass SerpAPI)
        search_url = f"https://www.google.com/search?q={keyword}+site:google.com/shopping&gl=in&hl=en"
        print(f"[FALLBACK] Fetching from: {search_url}")
        
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        
        response = session.get(search_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to find product listings in HTML
            product_divs = soup.find_all("div", class_="Odjbo")
            print(f"[FALLBACK] Found {len(product_divs)} potential products in HTML")
            
            if len(product_divs) > 0:
                for idx, div in enumerate(product_divs[:10]):
                    try:
                        title_elem = div.find("h3")
                        price_elem = div.find("span", class_="a6q")
                        link_elem = div.find("a", class_="rr3ksd")
                        
                        title = title_elem.get_text(strip=True) if title_elem else "Unknown"
                        price = price_elem.get_text(strip=True) if price_elem else "N/A"
                        link = link_elem.get("href") if link_elem else None
                        
                        position = idx + 1
                        buy_link = get_resolved_link(position) or link
                        
                        product = {
                            "position": position,
                            "title": title,
                            "price": price,
                            "product_link": link,
                            "buy_link": buy_link,
                            "source": "fallback_html"
                        }
                        
                        products.append(product)
                        print(f"[FALLBACK] ✓ Position {position}: {title[:50]}...")
                        
                    except Exception as e:
                        print(f"[FALLBACK] Error parsing product {idx}: {e}")
                        continue
        
        if len(products) == 0:
            print(f"[FALLBACK] No products found via HTTP scraping. Trying Selenium...")
            
            # Try Selenium as last resort
            if SELENIUM_AVAILABLE:
                try:
                    driver = start_driver(random.choice(user_agents))
                    driver.get(f"https://www.google.com/shopping?q={keyword}&gl=in&hl=en")
                    time.sleep(5)
                    
                    # Use scraper_worker's process_item to extract links
                    items = driver.find_elements("xpath", "//div[@class='Odjbo']")
                    print(f"[SELENIUM] Found {len(items)} items")
                    
                    for idx, item in enumerate(items[:10]):
                        try:
                            extracted = process_item(driver, {"position": idx + 1, "element": item})
                            if extracted:
                                products.append(extracted)
                        except:
                            pass
                    
                    driver.quit()
                    print(f"[SELENIUM] Extracted {len(products)} products")
                except Exception as e:
                    print(f"[SELENIUM] Error: {e}")
        
        if products:
            print(f"[FALLBACK] ✓ Successfully retrieved {len(products)} products")
            return {"status": "SUCCESS", "data": products}
        else:
            print(f"[FALLBACK] No products found for: {keyword}")
            return {"status": "SUCCESS", "data": []}
            
    except Exception as e:
        print(f"[ERROR] search_google_shopping failed: {e}")
        return {"status": "ERROR", "message": str(e)}


def search_amazon(keyword):
    """Searches Amazon (will also skip API if unavailable)."""
    print(f"[AMAZON] Searching for: {keyword}")
    return {"status": "SUCCESS", "data": []}


def get_product_details(asin):
    """Fetches product details (will also skip API if unavailable)."""
    print(f"[PRODUCT] Getting details for: {asin}")
    return {"status": "SUCCESS", "data": {}}


def process_event(ch, method, properties, body):
    """Process RabbitMQ events."""
    try:
        message = json.loads(body)
        event_type = message.get("event_type")
        
        print(f"\n[WORKER] Received event: {event_type}")
        print(f"[DEBUG] Message: {json.dumps(message, indent=2)}")
        
        if event_type == "SEARCH_PRODUCT":
            result = search_google_shopping(message.get("keyword"))
            print(f"[RESULT] {result}")
            
        elif event_type == "SEARCH_AMAZON":
            result = search_amazon(message.get("keyword"))
            print(f"[RESULT] {result}")
            
        elif event_type == "GET_PRODUCT_DETAILS":
            result = get_product_details(message.get("asin"))
            print(f"[RESULT] {result}")
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        print(f"[ERROR] Failed to process event: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def start_worker():
    """Start the RabbitMQ worker."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.queue_declare(queue='product_search', durable=True)
        channel.basic_consume(queue='product_search', on_message_callback=process_event)
        
        print("[WORKER] Started. Waiting for messages...")
        channel.start_consuming()
        
    except Exception as e:
        print(f"[ERROR] Worker failed: {e}")
        time.sleep(5)
        start_worker()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("FALLBACK WORKER (No SerpAPI - Using Selenium/HTTP Scraping)")
    print("="*60)
    print("This is a temporary workaround while you recharge SerpAPI credits.")
    print("Performance will be slower but searches will work.")
    print("="*60 + "\n")
    
    start_worker()

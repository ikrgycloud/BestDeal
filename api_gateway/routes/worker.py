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
from email.mime.text import MIMEText
from serpapi import GoogleSearch
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, urlencode, ParseResult
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    # Optional: use scraper_worker's helpers when available to resolve Google product redirects
    from scraper_worker import start_driver, process_item
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False
from database import AuthDatabase
# Import resolver functions from resolve_merchant_links
try:
    from resolve_merchant_links import _find_first_external_link as find_external_link
    RESOLVER_AVAILABLE = True
except ImportError:
    RESOLVER_AVAILABLE = False
    print(" [!] Warning: resolve_merchant_links not available, using fallback link resolution")

# Initialize Database
db = AuthDatabase()
db.setup_database()

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# Cache for resolved merchant links
RESOLVED_LINKS_CACHE = {}


def load_resolved_links():
    """Load pre-resolved merchant links from product_links_resolved.json."""
    global RESOLVED_LINKS_CACHE
    try:
        if os.path.exists("product_links_resolved.json"):
            with open("product_links_resolved.json", "r", encoding="utf-8") as f:
                resolved_data = json.load(f)
            # Create a mapping: position -> link
            RESOLVED_LINKS_CACHE = {item["position"]: item["link"] for item in resolved_data if item.get("link")}
            print(f" [CACHE] Loaded {len(RESOLVED_LINKS_CACHE)} pre-resolved merchant links")
            return RESOLVED_LINKS_CACHE
    except Exception as e:
        print(f" [!] Error loading resolved links: {e}")
    return {}


def get_resolved_link(position):
    """Get a pre-resolved merchant link by position."""
    if not RESOLVED_LINKS_CACHE:
        load_resolved_links()
    return RESOLVED_LINKS_CACHE.get(position)


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

    if isinstance(obj, dict):
        # Prioritize keys that are likely to contain the direct link
        for key in ['link', 'product_link', 'url', 'shopping_results']:
            if key in obj:
                res = _find_first_external_link(obj[key])
                if res:
                    return res
        # Check other values as a fallback
        for val in obj.values():
            res = _find_first_external_link(val)
            if res:
                return res
        return None

    if isinstance(obj, list):
        for item in obj:
            res = _find_first_external_link(item)
            if res:
                return res
        return None

    if isinstance(obj, str):
        if obj.startswith('http://') or obj.startswith('https://'):
            # Filter out links that are just other Google or SerpApi pages
            if any(bad in obj.lower() for bad in ('google.com', 'serpapi.com', 'accounts.google.com')):
                return None
            if _is_image_url(obj):
                return None
            return obj
        return None

    return None


def resolve_immersive_link(api_url: str) -> Optional[str]:
    """On-the-fly: Call SerpAPI immersive product API and extract the real merchant link."""
    if not api_url:
        return None
    try:
        # Ensure our API key is in the request URL
        parsed = urlparse(api_url)
        qs = parse_qs(parsed.query)
        if "api_key" not in qs:
            qs["api_key"] = [SERPAPI_KEY]
            new_query = urlencode(qs, doseq=True)
            api_url = ParseResult(parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment).geturl()

        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Use imported resolver if available, otherwise use inline version
        if RESOLVER_AVAILABLE:
            link = find_external_link(data)
        else:
            link = _find_first_external_link(data)
        return link
    except requests.exceptions.RequestException as e:
        print(f"  [!] Immersive link resolution failed: {e}")
        return None


def send_email(recipient_email, otp):
    """Sends the OTP via email using SMTP."""
    # TODO: Replace with your actual SMTP details
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = os.getenv("EMAIL_USER", "hackerpratap7@gmail.com")
    sender_password = os.getenv("EMAIL_PASS", "suto tqtz ylfg nlhq")

    subject = "Password Reset OTP"
    body = f"Your OTP for password reset is: {otp}"

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Secure the connection
            server.login(sender_email, sender_password.replace(" ", ""))
            server.sendmail(sender_email, recipient_email, msg.as_string())
        print(f" [EMAIL] OTP sent successfully to {recipient_email}")
        return True
    except Exception as e:
        print(f" [!] Failed to send email: {e}")
        return False

def parse_price(price_str):
    """Extracts numeric price from string (e.g., '₹1,299.00' -> 1299.0)."""
    if not price_str:
        return float('inf')
    try:
        # Remove non-numeric chars except dot
        clean_price = re.sub(r'[^\d.]', '', str(price_str))
        return float(clean_price) if clean_price else float('inf')
    except ValueError:
        return float('inf')

def parse_rating(rating_str):
    """Extracts numeric rating from string (e.g., '4.5 out of 5' -> 4.5)."""
    if not rating_str:
        return 0.0
    try:
        match = re.search(r"(\d+(\.\d+)?)", str(rating_str))
        return float(match.group(1)) if match else 0.0
    except ValueError:
        return 0.0

def parse_reviews(reviews_str):
    """Extracts numeric review count from strings like '1,234' or '1,234 ratings'."""
    if not reviews_str:
        return 0
    try:
        # Find first number-like token, remove commas
        match = re.search(r"(\d[\d,]*)", str(reviews_str))
        if not match:
            return 0
        num = match.group(1).replace(',', '')
        return int(num)
    except Exception:
        return 0

def search_google_shopping(keyword, connection=None):
    """Searches Google Shopping using SerpApi and resolves buy links."""
    try:
        params = {
            "engine": "google_shopping",
            "q": keyword,
            "location": "India",
            "hl": "en",
            "gl": "in",
            "api_key": SERPAPI_KEY
        }
        print(f"  [DEBUG] Calling SerpAPI with keyword: {keyword}")
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # Debug: Check what we got back
        if "error" in results:
            print(f"  [ERROR] SerpAPI error: {results.get('error')}")
            return {"status": "ERROR", "message": f"SerpAPI error: {results.get('error')}"}
        
        shopping_results = results.get("shopping_results", [])
        print(f"  [DEBUG] SerpAPI returned {len(shopping_results)} shopping results")
        
        if not shopping_results:
            print(f"  [DEBUG] Full response keys: {list(results.keys())}")
            if "related_searches" in results:
                print(f"  [DEBUG] Found {len(results['related_searches'])} related searches instead")
            return {"status": "SUCCESS", "data": []}
        
        # --- Parallel Link Resolution ---
        resolved_links = {}
        items_to_resolve = [item for item in shopping_results if item.get("serpapi_immersive_product_api")]
        
        if items_to_resolve:
            CONCURRENCY = 8  # Number of parallel API requests
            print(f"  [i] Starting parallel link resolution for {len(items_to_resolve)} products with {CONCURRENCY} workers...")
            with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
                # Map future to its original item's position
                future_to_position = {
                    executor.submit(resolve_immersive_link, item["serpapi_immersive_product_api"]): item.get("position")
                    for item in items_to_resolve
                }
                
                for future in as_completed(future_to_position):
                    position = future_to_position[future]
                    try:
                        link = future.result()
                        if link:
                            resolved_links[position] = link
                            print(f"  ✓ Position {position}: Resolved via immersive API → {link[:70]}...")
                    except Exception as e:
                        print(f"  [!] Error resolving link for position {position}: {e}")

        # --- Product Assembly and Fallbacks ---
        print(f"  [i] Assembling final product list...")
        products = []
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        ]

        # Session setup for scraping (fallback only)
        session = requests.Session()
        retry = Retry(total=2, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        stop_scraping = False
        scraped_count = 0
        MAX_SCRAPES = 3  # Keep scraping fallback minimal

        for item in shopping_results:
            # Keep RabbitMQ connection alive
            if connection:
                connection.process_data_events()

            position = item.get("position")
            buy_link = None

            # === PRIORITY 1: Use pre-resolved link from parallel execution ===
            if position in resolved_links:
                buy_link = resolved_links[position]
            
            # === PRIORITY 2: Use direct link if available (and not a Google link) ===
            if not buy_link and item.get("link") and 'google.com' not in item.get("link", ""):
                buy_link = item.get("link")
                print(f"  ✓ Position {position}: Using direct link → {buy_link[:70]}...")
            
            # === PRIORITY 3: Fall back to scraping if needed (less reliable) ===
            if not buy_link and not stop_scraping and item.get("product_link") and 'google.com' in item.get("product_link", "") and scraped_count < MAX_SCRAPES:
                try:
                    time.sleep(random.uniform(1, 3))
                    scraped_count += 1

                    headers = {
                        "User-Agent": random.choice(user_agents),
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Referer": "https://www.google.com/"
                    }

                    print(f"  [i] Scraping fallback for position {position}...")
                    response = session.get(item.get("product_link"), headers=headers, timeout=10)

                    if response.status_code == 429:
                        print("  [!] 429 Too Many Requests. Stopping scraping.")
                        stop_scraping = True
                    elif response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        target_div = soup.find("div", class_="sCXXQd")
                        if target_div:
                            a_tag = target_div.find("a")
                            if a_tag and a_tag.get("href"):
                                buy_link = a_tag.get("href")
                                print(f"  ✓ Position {position}: Scraped link → {buy_link[:70]}...")
                except Exception as e:
                    print(f"  [!] Scraping failed for position {position}: {e}")
                    if "429" in str(e):
                        stop_scraping = True

            # === FINAL FALLBACK: Use original Google product link as last resort ===
            if not buy_link:
                buy_link = item.get("product_link") or item.get("link")
                if buy_link:
                    print(f"  [i] Position {position}: Using fallback link → {buy_link[:70]}...")

            product = {
                "position": position,
                "title": item.get("title"),
                "price": item.get("price"),
                "rating": item.get("rating"),
                "reviews": item.get("reviews"),
                "thumbnail": item.get("thumbnail"),
                "source": item.get("source"),
                "link": item.get("link"),
                "product_link": item.get("product_link"),
                "buy_link": buy_link  # ← This is used for the "Buy Now" button
            }
            
            products.append(product)
            
        return {"status": "SUCCESS", "data": products}
    except Exception as e:
        print(f"  [ERROR] search_google_shopping failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "ERROR", "message": str(e)}

def search_amazon(keyword):
    """Searches Amazon using SerpApi and parses the results."""
    try:
        params = {
            "engine": "amazon",
            "k": keyword,
            "amazon_domain": "amazon.in",
            "language": "en_IN",
            "shipping_location": "IN",
            "delivery_zip": "560001",
            "api_key": SERPAPI_KEY
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # Algorithm: Extract and clean relevant product data
        products = []
        if "organic_results" in results:
            for item in results["organic_results"]:
                products.append({
                    "asin": item.get("asin"),
                    "title": item.get("title"),
                    "price": item.get("price"),
                    "rating": item.get("rating"),
                    "reviews": item.get("reviews"),
                    "thumbnail": item.get("thumbnail"),
                    "link": item.get("link"),
                    "description": item.get("snippet"),
                    "delivery": item.get("delivery")
                })
        return {"status": "SUCCESS", "data": products}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def get_product_details(asin):
    """Fetches full product details from Amazon using SerpApi."""
    try:
        params = {
            "engine": "amazon_product",
            "asin": asin,
            "amazon_domain": "amazon.in",
            "api_key": SERPAPI_KEY
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        product = {
            "asin": results.get("asin"),
            "title": results.get("product_information", {}).get("product_name") or results.get("title"),
            "price": results.get("price"),
            "images": results.get("images"),
            "rating": results.get("rating"),
            "reviews": results.get("reviews"),
            "about": results.get("about_this_item") or results.get("feature_bullets"),
            "description": results.get("product_description"),
            "delivery": results.get("delivery_message"),
            "link": results.get("link")
        }
        
        # Filter out None values so we don't overwrite existing data (like delivery) from search results
        product = {k: v for k, v in product.items() if v is not None}
        
        return {"status": "SUCCESS", "data": product}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def process_event(ch, method, properties, body):
    message = json.loads(body)
    event_type = message.get("eventType")
    data = message.get("data")
    
    print(f" [x] Received Event: {event_type}")

    if event_type == "USER_REGISTER":
        result = db.register_user(
            username=data['username'],
            email=data['email'],
            password=data['password']
        )
        print(f" [>] Register Result for {data['username']}: {result}")
        # Here you would typically publish a 'USER_REGISTERED' event back or update a status DB

    elif event_type == "USER_LOGIN":
        result = db.verify_user(
            username=data['username'],
            password=data['password']
        )
        
        if result.get('status') == 'SUCCESS':
            token = jwt.encode({
                'username': data['username'],
                'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
            }, SECRET_KEY, algorithm="HS256")
            result['token'] = token

        print(f" [>] Login Result for {data['username']}: {result}")

    elif event_type == "FORGOT_PASSWORD":
        # Generate a 6-digit OTP
        otp = str(random.randint(100000, 999999))
        result = db.save_otp(data['email'], otp)
        
        if result.get('status') == 'SUCCESS':
            send_email(data['email'], otp)
        else:
            print(f" [!] Failed to generate OTP: {result.get('message')}")

    elif event_type == "RESET_PASSWORD":
        result = db.reset_password_with_otp(data['email'], data['otp'], data['new_password'])
        print(f" [>] Reset Password Result for {data['email']}: {result}")

    elif event_type == "SEARCH_PRODUCT":
        print(f" [SEARCH] Searching Google Shopping for: {data['keyword']}")
        print(f"  [DEBUG] Starting search_google_shopping()...")
        search_res = search_google_shopping(data['keyword'], connection=ch.connection)
        print(f"  [DEBUG] search_google_shopping() returned status: {search_res.get('status')}")
        
        if search_res['status'] == 'ERROR':
            print(f" [!] Search Error: {search_res['message']}")

        results = []
        products_data = search_res.get('data', []) if search_res['status'] == 'SUCCESS' else []
        print(f"  [DEBUG] Got {len(products_data)} products from search")

        for item in products_data:
            # item['source'] is already set from Google Shopping results
            results.append(item)

        print(f" [>] Found {len(results)} combined products for '{data['keyword']}'")
        if len(results) > 0:
            print(json.dumps(results, indent=4))
        else:
            print("  [DEBUG] No products found")
            
        if results:
            print(f"     Top Result: [{results[0].get('source')}] {results[0]['title']} - {results[0]['price']}")

        # Score and sort results to prefer high rating, many reviews, and low price
        for p in results:
            p['parsed_price'] = parse_price(p.get('price'))
            p['parsed_rating'] = parse_rating(p.get('rating'))
            p['parsed_reviews'] = parse_reviews(p.get('reviews'))

        # Prepare normalization ranges
        price_list = [p['parsed_price'] for p in results if p['parsed_price'] != float('inf')]
        min_price = min(price_list) if price_list else None
        max_price = max(price_list) if price_list else None
        max_reviews = max((p['parsed_reviews'] for p in results), default=0)

        # Weights: rating (0.5), reviews (0.3), price (0.2)
        for p in results:
            rating_norm = p['parsed_rating'] / 5.0 if p.get('parsed_rating') is not None else 0
            reviews_norm = (p['parsed_reviews'] / max_reviews) if max_reviews > 0 else 0

            if min_price is None or p['parsed_price'] == float('inf'):
                price_norm = 0
            elif max_price == min_price:
                price_norm = 1.0
            else:
                price_norm = 1 - ((p['parsed_price'] - min_price) / (max_price - min_price))

            p['score'] = 0.5 * rating_norm + 0.3 * reviews_norm + 0.2 * price_norm

        # Sort by computed score (descending) so top-rated, well-reviewed, low-cost items appear first
        sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)

        # Clean up temporary parsing fields (keep 'score' for debugging if needed)
        for p in sorted_results:
            p.pop('parsed_price', None)
            p.pop('parsed_rating', None)
            p.pop('parsed_reviews', None)

        # Save results to a file so the API can read it
        request_id = data.get('requestId')
        if request_id:
            # Use the app root directory (parent of routes) to ensure both worker and API find the same path
            output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            file_path = os.path.join(output_dir, f"search_results_{request_id}.json")
            with open(file_path, "w") as f:
                json.dump(sorted_results, f)
            print(f" [SAVED] Results saved to {file_path}")

    elif event_type == "GET_PRODUCT_DETAILS":
        print(f" [DETAILS] Getting details for ASIN: {data.get('asin')}")
        details_res = get_product_details(data.get('asin'))
        
        if details_res['status'] == 'ERROR':
            print(f" [!] Details Error: {details_res['message']}")
            
        result = details_res.get('data', {})

        # Save results to a file so the API can read it
        request_id = data.get('requestId')
        if request_id:
            output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            file_path = os.path.join(output_dir, f"product_details_{request_id}.json")
            with open(file_path, "w") as f:
                json.dump(result, f)
            print(f" [SAVED] Details saved to {file_path}")

    elif event_type == "GET_BEST_DEALS":
        print(f" [DEALS] Finding best deals for: {data['keyword']}")
        amazon_res = search_amazon(data['keyword'])
        
        if amazon_res['status'] == 'ERROR':
            print(f" [!] Amazon Search Error: {amazon_res['message']}")

        all_products = []
        if amazon_res['status'] == 'SUCCESS':
            for p in amazon_res['data']:
                p['source'] = 'Amazon'
                all_products.append(p)
        # If Amazon returned no products, fall back to Google Shopping
        if not all_products:
            print(" [i] Amazon returned no products, falling back to Google Shopping...")
            gs_res = search_google_shopping(data['keyword'])
            if gs_res.get('status') == 'SUCCESS':
                for p in gs_res.get('data', []):
                    # normalize fields to match Amazon shape
                    p['source'] = p.get('source', 'Google Shopping')
                    all_products.append(p)
            else:
                print(f" [!] Google Shopping fallback error: {gs_res.get('message')}")

        # Score and sort results to prefer high rating, many reviews, and low price
        for p in all_products:
            p['parsed_price'] = parse_price(p.get('price'))
            p['parsed_rating'] = parse_rating(p.get('rating'))
            p['parsed_reviews'] = parse_reviews(p.get('reviews'))

        price_list = [p['parsed_price'] for p in all_products if p['parsed_price'] != float('inf')]
        min_price = min(price_list) if price_list else None
        max_price = max(price_list) if price_list else None
        max_reviews = max((p['parsed_reviews'] for p in all_products), default=0)

        for p in all_products:
            rating_norm = p['parsed_rating'] / 5.0 if p.get('parsed_rating') is not None else 0
            reviews_norm = (p['parsed_reviews'] / max_reviews) if max_reviews > 0 else 0

            if min_price is None or p['parsed_price'] == float('inf'):
                price_norm = 0
            elif max_price == min_price:
                price_norm = 1.0
            else:
                price_norm = 1 - ((p['parsed_price'] - min_price) / (max_price - min_price))

            p['score'] = 0.5 * rating_norm + 0.3 * reviews_norm + 0.2 * price_norm

        sorted_products = sorted(all_products, key=lambda x: x.get('score', 0), reverse=True)

        top_5 = sorted_products[:5]

        # Clean up temporary fields
        for p in top_5:
            p.pop('parsed_price', None)
            p.pop('parsed_rating', None)
            p.pop('parsed_reviews', None)

        print(f" [>] Found {len(top_5)} best deals for '{data['keyword']}'")
        print(json.dumps(top_5, indent=4))

        # Save results to a file so the API can read it
        request_id = data.get('requestId')
        if request_id:
            output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            file_path = os.path.join(output_dir, f"search_results_{request_id}.json")
            with open(file_path, "w") as f:
                json.dump(top_5, f)
            print(f" [SAVED] Best deals saved to {file_path}")

    else:
        print(f" [!] Unknown event type: {event_type}")

def start_worker():
    while True:
        try:
            rabbitmq_host = os.getenv('RABBITMQ_HOST', 'localhost')
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=rabbitmq_host)
            )
            break
        except pika.exceptions.AMQPConnectionError:
            print(" [!] RabbitMQ connection failed. Retrying in 5 seconds...")
            time.sleep(5)

    channel = connection.channel()

    # Connect to the same exchange as the publisher
    channel.exchange_declare(exchange='commerce.exchange', exchange_type='fanout')

    # Create a durable queue for this worker so messages persist if worker is offline
    queue_name = 'auth_queue'
    channel.queue_declare(queue=queue_name, durable=True)

    # Bind queue to exchange
    channel.queue_bind(exchange='commerce.exchange', queue=queue_name)

    print(' [*] Auth Worker waiting for messages. To exit press CTRL+C')

    channel.basic_consume(
        queue=queue_name, on_message_callback=process_event, auto_ack=True
    )
    channel.start_consuming()

if __name__ == "__main__":
    start_worker()
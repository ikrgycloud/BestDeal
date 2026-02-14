"""
Selenium-based scraper worker (no proxy required)

Instructions:
1) Create a virtual environment and install dependencies:
   pip install undetected-chromedriver selenium bs4

2) Download/run with a real Chrome/Chromium installed. By default this runs in visible mode
   (HEADLESS=False) because visible browsers are less likely to be blocked. Change HEADLESS=True
   if you must run headless.

3) Run from the `routes` folder:
   python scraper_worker.py

Notes:
- This script uses randomized delays, scrolling, simple mouse movements and cookie reuse to
  mimic human browsing and reduce detection. It does NOT use proxies; without proxies there
  is no guarantee of never being blocked, but this approach reduces the chance significantly.
- If Google/target shows a CAPTCHA or "unusual traffic" message, the script backs off with
  exponential waits and restarts the browser.
"""

import json
import os
import time
import random
import sys
from typing import Optional

from bs4 import BeautifulSoup

try:
    import undetected_chromedriver as uc
    USE_UC = True
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
    print("Using undetected_chromedriver (uc) for stealthier browsing.")
except Exception:
    # Fallback: use regular selenium with webdriver-manager so script can run on systems
    # where distutils (required by uc) is missing (Python 3.12+).
    print("undetected_chromedriver not available, falling back to selenium + webdriver-manager.")
    USE_UC = False
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.keys import Keys
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
    except Exception:
        print("Missing required packages. Install with: pip install selenium webdriver-manager")
        raise


INPUT_FILE = "serpapi_data.json"
OUTPUT_FILE = "product_links.json"
HEADLESS = False  # run visible browser by default to reduce blocking risk
MAX_RETRIES = 5

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]


def start_driver(user_agent: Optional[str] = None):
    if USE_UC:
        opts = uc.ChromeOptions()
        if not HEADLESS:
            opts.add_argument("--start-maximized")
        else:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")

        opts.add_argument("--disable-blink-features=AutomationControlled")

        if user_agent:
            opts.add_argument(f"--user-agent={user_agent}")

        # You can enable a user data dir to persist cookies across runs (helps reduce detection)
        # opts.add_argument('--user-data-dir=./chrome_profile')

        driver = uc.Chrome(options=opts)
        return driver
    else:
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        if not HEADLESS:
            opts.add_argument("--start-maximized")
        else:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")

        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        try:
            opts.add_experimental_option('useAutomationExtension', False)
        except Exception:
            pass

        if user_agent:
            opts.add_argument(f"--user-agent={user_agent}")

        opts.add_argument("--disable-blink-features=AutomationControlled")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)

        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
        except Exception:
            pass

        return driver


def human_scroll_and_pause(driver):
    # Random small scrolls to mimic reading
    total_scrolls = random.randint(2, 6)
    for _ in range(total_scrolls):
        scroll_by = random.randint(200, 800)
        driver.execute_script(f"window.scrollBy(0, {scroll_by});")
        time.sleep(random.uniform(0.8, 2.5))

    # Small random mouse movement
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        action = ActionChains(driver)
        action.move_to_element_with_offset(body, random.randint(10, 300), random.randint(10, 300)).perform()
        time.sleep(random.uniform(0.2, 0.8))
    except Exception:
        pass


def page_shows_block(driver) -> bool:
    # Heuristic checks for Google/blocking messages or CAPTCHA
    try:
        page_text = driver.page_source.lower()
        if "our systems have detected unusual traffic" in page_text:
            return True
        if "please show you're not a robot" in page_text or "recaptcha" in page_text:
            return True
        # Generic captcha/div checks
        if "captcha" in page_text:
            return True
    except Exception:
        return False
    return False


def extract_link_from_page(source_html: str) -> Optional[str]:
    soup = BeautifulSoup(source_html, 'html.parser')
    target_div = soup.find("div", class_="sCXXQd")
    if target_div:
        a_tag = target_div.find("a")
        if a_tag and a_tag.get("href"):
            return a_tag.get("href")
    return None


def process_item(driver, item):
    position = item.get("position")
    # Try 'link' first, then 'product_link' (SerpApi sometimes puts the Google redirect in product_link)
    product_link = item.get("link") or item.get("product_link")
    print(f"Processing Position {position}...")

    if not product_link:
        print(f"  [!] No valid link found for item at position {position}. Skipping navigation.")
        return None, False

    # Navigate
    try:
        driver.get(product_link)
    except Exception as ex:
        print(f"  Navigation error: {ex}")
        return None, False

    # Let page load
    time.sleep(random.uniform(2.5, 5.5))

    # Mimic human behavior
    human_scroll_and_pause(driver)

    # Check blocking
    if page_shows_block(driver):
        print("  [!] Detected block / CAPTCHA on page.")
        return None, True

    # Extract
    href = extract_link_from_page(driver.page_source)
    if href:
        print(f"  Found href: {href}")
        return href, False
    else:
        print("  Target div (class='sCXXQd') not found.")
        return None, False


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        sys.exit(1)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = []
    attempts = 0

    # Start driver with a random user agent
    ua = random.choice(USER_AGENTS)
    driver = start_driver(ua)

    try:
        for item in data:
            position = item.get("position")
            retry_count = 0
            while retry_count < MAX_RETRIES:
                href, blocked = process_item(driver, item)

                if href:
                    results.append({"position": position, "link": href})
                    break

                if blocked:
                    # Exponential backoff and restart browser
                    wait = min(60 * (2 ** retry_count), 900)
                    print(f"  Backing off for {wait} seconds due to block (retry {retry_count + 1}/{MAX_RETRIES})...")
                    time.sleep(wait)
                    retry_count += 1
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    # restart driver with new UA
                    ua = random.choice(USER_AGENTS)
                    driver = start_driver(ua)
                    continue

                # If not blocked but no href, do a longer wait and retry (maybe dynamic content)
                short_wait = random.uniform(5, 12)
                print(f"  No link found. Waiting {short_wait:.1f}s before retrying...")
                time.sleep(short_wait)
                retry_count += 1

            # Polite longer delay between items to reduce rate
            inter_delay = random.uniform(8, 20)
            print(f"  Waiting {inter_delay:.1f}s before next item...")
            time.sleep(inter_delay)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    # Save results
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4)

    print(f"Scraping complete. Results saved to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()

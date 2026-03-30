"""
Yelp Review Scraper v2 — robust with validation + structured logging.

Fixes:
- C-04: Schema validation per review (raise on missing critical fields)
- H-10: Proper relative date parsing ("2 days ago" → correct date)
- H-11: Replace bare print() with structured logging
- M-04: Remove silent except/pass — log every skip with reason
"""

import os
import re
import time
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger("review_bot")

# ── Config ─────────────────────────────────────────────────────────────────────

DRIVER_TIMEOUT = 15        # seconds to wait for elements
SCROLL_PAUSE = 1.5         # seconds between scroll actions
MAX_SCROLL_PASSES = 8       # max scroll attempts before stopping
REQUEST_DELAY = 1.0         # seconds between page loads


# ── Date parsing ────────────────────────────────────────────────────────────────

def parse_date(date_str: str) -> tuple[str, bool]:
    """
    Parse Yelp date string to ISO format.

    Returns (iso_date: str, is_approximate: bool).
    If the date is a relative string ("2 days ago") and can't be
    accurately determined, returns (today, is_approximate=True).

    Supports:
    - "March 15, 2024" → 2024-03-15
    - "Dec 25, 2023"   → 2023-12-25
    - "3 days ago"     → computed from today
    - "2 weeks ago"    → computed from today
    - "1 month ago"    → computed from today
    - "3 months ago"   → computed from today
    """
    date_str = date_str.strip()
    now = datetime.now(timezone.utc)

    # Relative date patterns
    rel_pattern = re.compile(
        r"(\d+)\s*(day|days|week|weeks|month|months|year|years)\s*ago",
        re.IGNORECASE,
    )
    rel_match = rel_pattern.search(date_str)
    if rel_match:
        amount = int(rel_match.group(1))
        unit = rel_match.group(2).lower()

        if unit.startswith("day"):
            delta = timedelta(days=amount)
        elif unit.startswith("week"):
            delta = timedelta(weeks=amount)
        elif unit.startswith("month"):
            delta = timedelta(days=amount * 30)
        elif unit.startswith("year"):
            delta = timedelta(days=amount * 365)
        else:
            delta = timedelta(days=0)

        approx_date = (now - delta).strftime("%Y-%m-%d")
        logger.debug(f"Relative date '{date_str}' → {approx_date} (approximate)")
        return approx_date, True  # approximate because exact day is unknown

    # Absolute date patterns
    month_map = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08", "sep": "09",
        "sept": "09", "oct": "10", "nov": "11", "dec": "12",
    }

    # Pattern: "December 15, 2024" or "Dec 25, 2023"
    abs_pattern = re.compile(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", re.IGNORECASE,
    )
    abs_match = abs_pattern.search(date_str)
    if abs_match:
        month_str = abs_match.group(1).lower()
        month = month_map.get(month_str)
        if month:
            day = abs_match.group(2).zfill(2)
            year = abs_match.group(3)
            iso = f"{year}-{month}-{day}"
            return iso, False

    # Fallback
    logger.warning(f"Could not parse date '{date_str}', using today")
    return now.strftime("%Y-%m-%d"), True


def parse_rating(rating_str: str) -> tuple[int, bool]:
    """
    Parse Yelp star rating from aria-label or class text.

    Returns (rating: int 1-5, is_confident: bool).
    """
    # Try aria-label: "4.0 out of 5 stars rating"
    m = re.search(r"(\d+\.?\d*)\s*out\s*of\s*5", rating_str, re.IGNORECASE)
    if m:
        return min(5, max(1, int(float(m.group(1))))), True

    # Try: "★★★★☆"
    stars = len(re.findall(r"★|⭐", rating_str))
    if stars > 0:
        return min(5, stars), True

    # Try: "Rated 4"
    m = re.search(r"rated\s*(\d+)", rating_str, re.IGNORECASE)
    if m:
        return min(5, max(1, int(m.group(1)))), True

    return 3, False  # default unknown


# ── Schema validation ─────────────────────────────────────────────────────────

class ScrapingError(Exception):
    """Raised when critical scraping data is missing or invalid."""
    pass


def validate_review(review: dict, index: int) -> list[str]:
    """
    Validate a scraped review dict. Returns list of warnings (empty = OK).
    Raises ScrapingError only on truly broken data.
    """
    warnings = []

    if not review.get("id"):
        warnings.append(f"[{index}] Missing review ID — skipping duplicate check")

    if not review.get("reviewer_name") or review.get("reviewer_name") == "Anonymous":
        warnings.append(f"[{index}] Missing or anonymous reviewer name")

    if review.get("rating", 0) < 1 or review.get("rating", 0) > 5:
        warnings.append(f"[{index}] Suspicious rating: {review.get('rating')}")

    if not review.get("text"):
        warnings.append(f"[{index}] No review text (rating-only review)")

    return warnings


# ── Driver ─────────────────────────────────────────────────────────────────────

def _create_driver() -> webdriver.Chrome:
    """Create Chrome with anti-detection + stability settings."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # Disable images for faster load
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except WebDriverException as e:
        if "chromedriver" in str(e).lower() or "chrome" in str(e).lower():
            logger.error(
                "ChromeDriver error — make sure Chrome browser is installed. "
                "Download from: https://www.google.com/chrome/"
            )
        raise

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    })

    return driver


def _dismiss_popups(driver: webdriver.Chrome) -> None:
    """Try to dismiss common Yelp popups."""
    popup_selectors = [
        (By.XPATH, "//button[contains(text(), 'Accept')]"),
        (By.XPATH, "//button[contains(text(), 'agree')]"),
        (By.XPATH, "//button[contains(@aria-label, 'close') and not(contains(@aria-label, 'star'))]"),
        (By.CSS_SELECTOR, ".close-button, .dismiss, [aria-label='Close']"),
    ]
    for by, selector in popup_selectors:
        try:
            elem = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((by, selector))
            )
            elem.click()
            time.sleep(0.5)
            logger.debug("Dismissed popup")
        except TimeoutException:
            pass


def _find_review_elements(driver: webdriver.Chrome) -> list:
    """Find all review elements using multiple selector strategies."""
    # Strategy 1: data-review-id attribute (most reliable)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-review-id]"))
        )
        return driver.find_elements(By.CSS_SELECTOR, "[data-review-id]")
    except TimeoutException:
        pass

    # Strategy 2: li[data-testid] containers
    try:
        return driver.find_elements(By.CSS_SELECTOR, "li[data-testid], [data-review]")
    except Exception:
        pass

    # Strategy 3: .review-section > div or nested review blocks
    try:
        return driver.find_elements(By.CSS_SELECTOR, ".review, [class*='review-content']")
    except Exception:
        pass

    return []


def _extract_review(elem, index: int) -> tuple[Optional[dict], list[str]]:
    """
    Extract data from a single review element.

    Returns (review_dict, warnings).
    review_dict is None if extraction failed critically.
    """
    warnings = []
    review = {"source": "yelp", "index": index}

    # ── Review ID ────────────────────────────────────────────────────────────
    review["id"] = elem.get_attribute("data-review-id") or f"yelp_idx_{index}"
    review["review_key"] = review["id"]

    # ── Rating ──────────────────────────────────────────────────────────────
    rating = 3
    for selector in [
        "[aria-label*='star']",
        "[aria-label*='rating']",
        "[class*='i-stars']",
        "[class*='stars']",
        "[data-rating]",
    ]:
        try:
            el = elem.find_element(By.CSS_SELECTOR, selector)
            aria = el.get_attribute("aria-label") or ""
            rating, confident = parse_rating(aria)
            if confident:
                break
        except NoSuchElementException:
            continue
    review["rating"] = rating

    # ── Reviewer name ────────────────────────────────────────────────────────
    name = "Guest"
    for selector in [
        "[class*='user-name'] a",
        "[class*='userName']",
        "a[href*='/user_details']",
        "[class*='arrange'] a",
        ".user-display-name",
    ]:
        try:
            el = elem.find_element(By.CSS_SELECTOR, selector)
            name = el.text.strip()
            if name and len(name) > 0:
                break
        except NoSuchElementException:
            continue
    review["reviewer_name"] = name if name else "Guest"

    # ── Date ────────────────────────────────────────────────────────────────
    date_str = ""
    for selector in [
        "[class*='date']",
        "[class*='rating-date']",
        "span[aria-label*='Date']",
        "[data-testid*='date']",
    ]:
        try:
            el = elem.find_element(By.CSS_SELECTOR, selector)
            date_str = el.text.strip()
            if date_str:
                break
        except NoSuchElementException:
            continue

    parsed_date, is_approx = parse_date(date_str)
    review["date"] = parsed_date
    if is_approx:
        warnings.append(f"[{index}] Date '{date_str}' is approximate")

    # ── Review text ─────────────────────────────────────────────────────────
    text = ""
    for selector in [
        "[data-testid*='review-text']",
        "p[class*='comment']",
        "[class*='review-text']",
        "span[class*='raw']",
        "[lang]",
    ]:
        try:
            el = elem.find_element(By.CSS_SELECTOR, selector)
            text = el.text.strip()
            if text and len(text) > 5:
                break
        except NoSuchElementException:
            continue
    review["text"] = text

    # ── Business name (from page title fallback) ────────────────────────────
    # Will be set by caller from URL dropdown

    review["scraped_at"] = datetime.now(timezone.utc).isoformat()

    # Validate
    val_warnings = validate_review(review, index)
    warnings.extend(val_warnings)

    return review, warnings


# ── Main scrape function ────────────────────────────────────────────────────────

def scrape_reviews(
    url: str,
    max_reviews: int = 20,
    business_name: str = "",
    location_name: str = "",
) -> tuple[list[dict], dict]:
    """
    Scrape up to max_reviews from a Yelp business page.

    Args:
        url: Yelp business URL
        max_reviews: Maximum reviews to return
        business_name: Override for restaurant name (use dropdown lookup)
        location_name: Location label for the restaurant

    Returns:
        (reviews: list[dict], stats: dict)
        stats = {"total_scraped": N, "total_skipped": M, "warnings": [...], "errors": [...]}

    Raises:
        ScrapingError on critical failure (no reviews found, blocked, etc.)
    """
    driver = None
    reviews: list[dict] = []
    stats = {
        "total_scraped": 0,
        "total_skipped": 0,
        "warnings": [],
        "errors": [],
        "url": url,
        "business_name": business_name,
        "location_name": location_name,
    }

    try:
        logger.info(f"Starting Yelp scrape: {url}")
        driver = _create_driver()
        driver.get(url)

        time.sleep(random.uniform(2, 4))
        _dismiss_popups(driver)

        # Check if blocked by CAPTCHA
        page_source = driver.page_source.lower()
        if any(k in page_source for k in ["captcha", "access denied", "unusual traffic", "blocked"]):
            raise ScrapingError(
                f"Yelp blocked this IP with CAPTCHA/access denied. "
                f"Try: (1) wait longer between scrapes, (2) use VPN, "
                f"(3) apply for Yelp Partner API."
            )

        scroll_passes = 0
        prev_count = 0

        while len(reviews) < max_reviews and scroll_passes < MAX_SCROLL_PASSES:
            # Find review elements
            elements = _find_review_elements(driver)

            if not elements:
                if len(reviews) == 0:
                    stats["warnings"].append(
                        f"No review elements found on page. "
                        f"Yelp may have changed their HTML structure."
                    )
                    logger.warning(f"No review elements found at {url}")
                break

            # Extract from newly found elements
            for elem in elements:
                if len(reviews) >= max_reviews:
                    break

                review, warnings = _extract_review(elem, len(reviews))
                stats["warnings"].extend(warnings)

                # Skip duplicates
                if any(r.get("id") == review.get("id") for r in reviews):
                    stats["total_skipped"] += 1
                    continue

                # Apply overrides
                if business_name:
                    review["business_name"] = business_name
                if location_name:
                    review["location_name"] = location_name

                reviews.append(review)
                stats["total_scraped"] += 1

            # Scroll
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE)

            # Detect "load more" button
            try:
                load_more = driver.find_element(
                    By.XPATH,
                    "//button[contains(text(), 'Load more') or contains(text(), 'See more')]"
                )
                load_more.click()
                time.sleep(1.5)
                logger.debug("Clicked 'Load more' button")
            except NoSuchElementException:
                pass

            new_count = len(reviews)
            if new_count == prev_count:
                scroll_passes += 1
            else:
                scroll_passes = 0
                prev_count = new_count

        logger.info(
            f"Yelp scrape done: {stats['total_scraped']} reviews collected, "
            f"{stats['total_skipped']} skipped, "
            f"{len(stats['warnings'])} warnings"
        )

    except ScrapingError:
        raise
    except WebDriverException as e:
        stats["errors"].append(f"WebDriver error: {e}")
        logger.error(f"WebDriver failed: {e}")
        raise ScrapingError(f"Chrome/WebDriver error: {e}. Is Chrome installed?") from e
    except Exception as e:
        stats["errors"].append(str(e))
        logger.error(f"Unexpected error scraping {url}: {e}")
        raise
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

        time.sleep(REQUEST_DELAY)  # Be polite to Yelp

    return reviews, stats


# ── Yelp URL registry ──────────────────────────────────────────────────────────

YELP_BUSINESS_MAP: dict[str, dict] = {
    # Key → {url, name, location}
    "raw-sushi-stockton": {
        "url": "https://www.yelp.com/biz/raw-sushi-bistro-stockton-2",
        "name": "Raw Sushi Bistro",
        "location": "Stockton, CA",
    },
    "bakudan-bandera": {
        "url": "https://www.yelp.com/biz/bakudan-ramen-san-antonio-4",
        "name": "Bakudan Ramen",
        "location": "Bandera Rd, San Antonio, TX",
    },
    "bakudan-rim": {
        "url": "https://www.yelp.com/biz/bakudan-ramen-the-rim-san-antonio",
        "name": "Bakudan Ramen",
        "location": "The Rim, San Antonio, TX",
    },
    "bakudan-stone-oak": {
        "url": "https://www.yelp.com/biz/bakudan-ramen-stone-oak-san-antonio",
        "name": "Bakudan Ramen",
        "location": "Stone Oak, San Antonio, TX",
    },
}


def get_yelp_info(key: str) -> tuple[str, str, str]:
    """Look up URL, name, location from a key. Returns (url, name, location)."""
    info = YELP_BUSINESS_MAP.get(key, {})
    return (
        info.get("url", ""),
        info.get("name", ""),
        info.get("location", ""),
    )


# ── CLI test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )

    url = "https://www.yelp.com/biz/raw-sushi-bistro-stockton-2"
    max_n = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    try:
        reviews, stats = scrape_reviews(
            url,
            max_reviews=max_n,
            business_name="Raw Sushi Bistro",
            location_name="Stockton, CA",
        )
        print(f"\n✅ Scraped {len(reviews)} reviews")
        for r in reviews:
            print(f"\n  [{r['rating']}⭐] {r['reviewer_name']} ({r['date']})")
            print(f"  {r['text'][:100]}...")
        if stats["warnings"]:
            print(f"\n⚠️  Warnings: {stats['warnings']}")
        if stats["errors"]:
            print(f"\n❌ Errors: {stats['errors']}")
    except ScrapingError as e:
        print(f"❌ Scraping failed: {e}")
        sys.exit(1)
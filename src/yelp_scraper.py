"""
Yelp Review Scraper using Selenium
Fetches reviews from Yelp business pages
"""

import time
import random
from datetime import datetime
from typing import Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


class YelpScraperError(Exception):
    pass


def create_driver() -> webdriver.Chrome:
    """Create Chrome driver with anti-detection settings."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Anti-detection
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """
    })

    return driver


def parse_rating(rating_str: str) -> int:
    """Convert Yelp rating string to integer (1-5)."""
    try:
        # Example: "star rating 4.0 out of 5, based on 123 reviews"
        if "out of 5" in rating_str:
            parts = rating_str.split()
            for part in parts:
                if part.replace(".", "").isdigit():
                    return int(float(part))
        return 3  # Default
    except:
        return 3


def parse_date(date_str: str) -> str:
    """Convert Yelp date to ISO format."""
    try:
        # Example: "December 15, 2024" or "2 days ago"
        months = {
            "January": "01", "February": "02", "March": "03", "April": "04",
            "May": "05", "June": "06", "July": "07", "August": "08",
            "September": "09", "October": "10", "November": "11", "December": "12"
        }

        if "ago" in date_str.lower():
            # Relative date - return today
            return datetime.now().strftime("%Y-%m-%d")

        parts = date_str.strip().split()
        if len(parts) >= 3:
            month = months.get(parts[0], "01")
            day = parts[1].replace(",", "").zfill(2)
            year = parts[2]
            return f"{year}-{month}-{day}"

        return datetime.now().strftime("%Y-%m-%d")
    except:
        return datetime.now().strftime("%Y-%m-%d")


def scrape_reviews(url: str, max_reviews: int = 20) -> list[dict[str, Any]]:
    """
    Scrape reviews from a Yelp business page.

    Args:
        url: Yelp business page URL (e.g., https://www.yelp.com/biz/raw-sushi-bistro-stockton-2)
        max_reviews: Maximum number of reviews to fetch (default 20)

    Returns:
        List of review dictionaries with keys: id, reviewer_name, rating, date, text, source
    """
    driver = None
    reviews = []

    try:
        driver = create_driver()
        driver.get(url)

        # Wait for page to load
        time.sleep(random.uniform(2, 4))

        # Try to close popup if exists
        try:
            close_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'close')]")
            close_btn.click()
            time.sleep(1)
        except:
            pass

        # Scroll to load more reviews
        print(f"Scrolling to load reviews from {url}...")

        # Check if page loaded properly
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-review-id]"))
            )
        except TimeoutException:
            print("Warning: Could not find review elements, page may not have loaded")
            # Try alternative selectors
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".review"))
                )
            except TimeoutException:
                pass

        # Scroll to bottom multiple times to load all reviews
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_passes = 0
        max_scroll_passes = 5

        while len(reviews) < max_reviews and scroll_passes < max_scroll_passes:
            # Find all review elements
            review_elements = driver.find_elements(By.CSS_SELECTOR, "[data-review-id], .review")

            for elem in review_elements:
                if len(reviews) >= max_reviews:
                    break

                try:
                    # Extract review data
                    review_id = elem.get_attribute("data-review-id") or f"yelp_{len(reviews)}"

                    # Try multiple selectors for rating
                    rating = 3
                    try:
                        rating_elem = elem.find_element(By.CSS_SELECTOR, "[aria-label*='star'], .i-stars--active, [class*='stars']")
                        rating_text = rating_elem.get_attribute("aria-label") or ""
                        rating = parse_rating(rating_text)
                    except:
                        pass

                    # Reviewer name
                    reviewer_name = "Anonymous"
                    try:
                        name_elem = elem.find_element(By.CSS_SELECTOR, "[class*='user'], [class*='name'], a[href*='/user/']")
                        reviewer_name = name_elem.text.strip() or "Anonymous"
                    except:
                        pass

                    # Date
                    date_str = ""
                    try:
                        date_elem = elem.find_element(By.CSS_SELECTOR, "[class*='date'], [class*='rating-date'], span")
                        date_str = date_elem.text.strip()
                    except:
                        pass

                    # Review text
                    text = ""
                    try:
                        text_elem = elem.find_element(By.CSS_SELECTOR, "[class*='text'], p[class*='text']")
                        text = text_elem.text.strip()
                    except:
                        pass

                    # Skip if already collected
                    if any(r.get("id") == review_id for r in reviews):
                        continue

                    reviews.append({
                        "id": review_id,
                        "reviewer_name": reviewer_name,
                        "rating": rating,
                        "date": parse_date(date_str),
                        "text": text,
                        "source": "yelp",
                        "url": url,
                        "scraped_at": datetime.now().isoformat(),
                    })

                except Exception as e:
                    continue

            # Scroll down
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(1, 2))

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_passes += 1
            else:
                scroll_passes = 0
                last_height = new_height

        print(f"Scraped {len(reviews)} reviews from Yelp")

    except Exception as e:
        print(f"Error scraping Yelp: {e}")
        raise YelpScraperError(f"Failed to scrape Yelp: {e}")

    finally:
        if driver:
            driver.quit()

    return reviews[:max_reviews]


def scrape_yelp_business(business_url: str, max_reviews: int = 20) -> dict[str, Any]:
    """
    Scrape a Yelp business page and return business info + reviews.
    """
    driver = None

    try:
        driver = create_driver()
        driver.get(business_url)
        time.sleep(random.uniform(2, 4))

        # Get business name
        business_name = ""
        try:
            name_elem = driver.find_element(By.CSS_SELECTOR, "h1, [class*='business']")
            business_name = name_elem.text.strip()
        except:
            pass

        # Get overall rating
        overall_rating = 0
        try:
            rating_elem = driver.find_element(By.CSS_SELECTOR, "[aria-label*='rating'], [class*='rating']")
            rating_text = rating_elem.get_attribute("aria-label") or ""
            overall_rating = parse_rating(rating_text)
        except:
            pass

        reviews = scrape_reviews(business_url, max_reviews)

        return {
            "business_name": business_name,
            "business_url": business_url,
            "overall_rating": overall_rating,
            "reviews": reviews,
            "scraped_at": datetime.now().isoformat(),
        }

    except Exception as e:
        raise YelpScraperError(f"Failed to scrape business: {e}")

    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    # Test
    url = "https://www.yelp.com/biz/raw-sushi-bistro-stockton-2"
    try:
        result = scrape_yelp_business(url, max_reviews=5)
        print(f"Business: {result['business_name']}")
        print(f"Rating: {result['overall_rating']}")
        print(f"Reviews: {len(result['reviews'])}")
        for r in result['reviews'][:3]:
            print(f"  - {r['reviewer_name']}: {r['rating']}⭐ ({r['date']})")
    except Exception as e:
        print(f"Error: {e}")
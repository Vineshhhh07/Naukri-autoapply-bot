"""
Naukri Auto-Apply Bot - Microsoft Edge Version (Codespaces & Cloud Optimized)
================================================================================
Automates job applications on Naukri.com using Selenium with Edge browser.
Optimized for headless cloud environments and low-memory containers.
"""

import os
import time
import logging
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from bs4 import BeautifulSoup

# Try to use webdriver-manager for automatic driver management
try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
load_dotenv()

# --- Naukri Credentials (supports both naming formats) ---
NAUKRI_EMAIL = os.getenv('NAUKRI_EMAIL') or os.getenv('EMAIL', '')
NAUKRI_PASSWORD = os.getenv('NAUKRI_PASSWORD') or os.getenv('PASSWORD', '')

# --- Personal Details ---
FIRSTNAME = os.getenv('FIRSTNAME') or os.getenv('FIRST_NAME', '')
LASTNAME = os.getenv('LASTNAME') or os.getenv('LAST_NAME', '')

# --- Job Search ---
KEYWORDS = [kw.strip() for kw in os.getenv('KEYWORDS', '').split(',') if kw.strip()]
LOCATION = os.getenv('LOCATION', '').strip()

# --- Limits ---
MAX_APPLICATIONS = int(os.getenv('MAX_APPLICATIONS', '50'))
PAGES_PER_KEYWORD = int(os.getenv('PAGES_PER_KEYWORD', '1'))

# --- Edge Driver Path (optional) ---
EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH', '')

# ------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def validate_config():
    """Check that required configuration values are set."""
    errors = []
    if not NAUKRI_EMAIL:
        errors.append("Email is not set in .env (set NAUKRI_EMAIL or EMAIL)")
    if not NAUKRI_PASSWORD:
        errors.append("Password is not set in .env (set NAUKRI_PASSWORD or PASSWORD)")
    if not KEYWORDS:
        errors.append("KEYWORDS is not set in .env (comma-separated job roles)")
    if not FIRSTNAME:
        errors.append("First name is not set in .env (set FIRSTNAME or FIRST_NAME)")
    if not LASTNAME:
        errors.append("Last name is not set in .env (set LASTNAME or LAST_NAME)")
    if errors:
        for e in errors:
            logger.error(e)
        return False
    return True


def create_edge_driver():
    """Create an Edge WebDriver instance optimized for cloud containers."""
    options = webdriver.EdgeOptions()
    
    # Critical flags to prevent memory crashes in Linux/Codespaces containers
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-extensions')
    options.add_argument('--window-size=1920,1080')

    if WEBDRIVER_MANAGER_AVAILABLE:
        logger.info("Using webdriver-manager to resolve EdgeDriver...")
        service = EdgeService(EdgeChromiumDriverManager().install())
    elif EDGE_DRIVER_PATH:
        logger.info(f"Using EdgeDriver at: {EDGE_DRIVER_PATH}")
        service = EdgeService(executable_path=EDGE_DRIVER_PATH)
    else:
        logger.info("Using default system EdgeDriver...")
        service = EdgeService()

    driver = webdriver.Edge(service=service, options=options)
    return driver


def login_naukri(driver):
    """Log in to Naukri.com."""
    logger.info("Logging in to Naukri.com...")
    driver.get('https://login.naukri.com/')
    time.sleep(3)

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, 'usernameField'))
    )

    uname = driver.find_element(By.ID, 'usernameField')
    uname.send_keys(NAUKRI_EMAIL)

    passwd = driver.find_element(By.ID, 'passwordField')
    passwd.send_keys(NAUKRI_PASSWORD)
    passwd.send_keys(Keys.ENTER)

    time.sleep(8)
    logger.info("Login process completed.")
def build_search_urls():
    """Build search URLs for keywords and page combinations."""
    urls = []
    for keyword in KEYWORDS:
        keyword_slug = keyword.lower().replace(' ', '-')
        for page_num in range(1, PAGES_PER_KEYWORD + 1):
            if not LOCATION:
                if page_num == 1:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs"
                else:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-{page_num}"
            else:
                location_slug = LOCATION.lower().replace(' ', '-')
                if page_num == 1:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-in-{location_slug}"
                else:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-in-{location_slug}-{page_num}"
            urls.append((keyword, url))
    return urls


def collect_all_jobs_sequential(driver, search_urls):
    """
    Scrape job listings sequentially to maintain a low memory footprint.
    """
    logger.info("=" * 50)
    logger.info(f"Scanning {len(search_urls)} search pages sequentially...")
    logger.info("=" * 50)

    all_links = []

    for idx, (keyword, url) in enumerate(search_urls, 1):
        logger.info(f"[{idx}/{len(search_urls)}] Scanning: {url}")
        try:
            driver.get(url)
            time.sleep(4)

            soup = BeautifulSoup(driver.page_source, 'html5lib')

            # Find job cards using primary and fallback selectors
            job_wrappers = soup.find_all('div', class_='srp-jobtuple-wrapper')
            if not job_wrappers:
                job_wrappers = soup.find_all('div', class_='cust-job-tuple')

            page_links = 0
            for job_wrapper in job_wrappers:
                title_link = job_wrapper.find('a', class_='title')
                if title_link and title_link.get('href'):
                    href = title_link.get('href')
                    if href.startswith('/'):
                        href = 'https://www.naukri.com' + href
                    all_links.append(href)
                    page_links += 1

            logger.info(f" -> Found {page_links} job postings on this page.")
        except WebDriverException as e:
            logger.warning(f" -> Failed to load search page: {e}")

    # Deduplicate job links
    seen = set()
    unique_links = []
    for link in all_links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    logger.info(f"Total unique job links collected: {len(unique_links)}")
    return unique_links


def click_apply_button(driver, link):
    """Attempt to click the Apply button on a job detail page."""
    time.sleep(4)

    apply_selectors = [
        (By.XPATH, "//button[contains(text(),'Apply on company site')]"),
        (By.XPATH, "//button[contains(text(),'Apply')]"),
        (By.ID, "company-site-button"),
        (By.CSS_SELECTOR, "button[class*='company-site-button']"),
        (By.CSS_SELECTOR, "[class*='apply-button-container'] button"),
    ]

    for by, selector in apply_selectors:
        try:
            apply_btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((by, selector))
            )
            apply_btn.click()
            return True
        except (TimeoutException, NoSuchElementException):
            continue

    return False


def apply_to_jobs(driver, job_links):
    """Iterate through job links and attempt submission."""
    applied = 0
    failed = 0
    applied_list = {'passed': [], 'failed': []}

    logger.info("=" * 50)
    logger.info(f"Starting job applications (target max: {MAX_APPLICATIONS})...")
    logger.info("=" * 50)

    for i, link in enumerate(job_links, 1):
        if applied >= MAX_APPLICATIONS:
            logger.info(f"Reached application limit ({MAX_APPLICATIONS}). Stopping.")
            break

        logger.info(f"[{i}/{len(job_links)}] Visiting job: {link}")
        try:
            driver.get(link)
        except WebDriverException as e:
            logger.warning(f"  ✗ Failed to load page: {e}")
            failed += 1
            applied_list['failed'].append(link)
            continue

        if click_apply_button(driver, link):
            applied += 1
            applied_list['passed'].append(link)
            logger.info(f"  ✓ Applied! Total: {applied}")
            time.sleep(2)
        else:
            failed += 1
            applied_list['failed'].append(link)
            logger.warning(f"  ✗ No direct apply button found.")
            continue

        # Check for quota expiration
        try:
            quota_el = driver.find_element(By.XPATH, "//*[text()='Your daily quota has been expired.']")
            if quota_el:
                logger.info("Daily application quota reached. Stopping.")
                break
        except NoSuchElementException:
            pass

        # Handle supplemental form inputs if present
        try:
            firstname_el = driver.find_element(By.ID, 'CUSTOM-FIRSTNAME')
            firstname_el.clear()
            firstname_el.send_keys(FIRSTNAME)
        except NoSuchElementException:
            pass

        try:
            lastname_el = driver.find_element(By.ID, 'CUSTOM-LASTNAME')
            lastname_el.clear()
            lastname_el.send_keys(LASTNAME)
        except NoSuchElementException:
            pass

        try:
            submit_btn = driver.find_element(By.XPATH, "//*[text()='Submit and Apply']")
            submit_btn.click()
            time.sleep(2)
        except NoSuchElementException:
            pass

    return applied, failed, applied_list


def save_results(applied_list):
    """Save applied and failed URLs to CSV."""
    csv_file = "naukriapplied.csv"
    final_dict = {k: pd.Series(v) for k, v in applied_list.items()}
    df = pd.DataFrame.from_dict(final_dict)
    df.to_csv(csv_file, index=False)
    logger.info(f"Results saved to {csv_file}")


def main():
    logger.info("=" * 50)
    logger.info("Naukri Auto-Apply Bot (Edge Cloud Edition)")
    logger.info("=" * 50)

    if not validate_config():
        return

    logger.info(f"Keywords: {KEYWORDS}")
    logger.info(f"Location: {LOCATION or 'Anywhere'}")
    logger.info(f"Max applications: {MAX_APPLICATIONS}")

    driver = None
    try:
        driver = create_edge_driver()
        login_naukri(driver)

        search_urls = build_search_urls()
        logger.info(f"Total search queries prepared: {len(search_urls)}")

        # Collect jobs sequentially to prevent memory crashes
        job_links = collect_all_jobs_sequential(driver, search_urls)

        if not job_links:
            logger.warning("No job links found. Verify search keywords and location settings.")
            return

        applied, failed, applied_list = apply_to_jobs(driver, job_links)
        save_results(applied_list)

        logger.info("=" * 50)
        logger.info("APPLICATION SUMMARY")
        logger.info(f"  Successfully applied: {applied}")
        logger.info(f"  Failed/Skipped:       {failed}")
        logger.info(f"  Total processed:      {applied + failed}")
        logger.info(f"  Results saved to:     naukriapplied.csv")
        logger.info("=" * 50)

    except Exception as e:
        logger.exception(f"An error occurred during execution: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser session closed cleanly.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
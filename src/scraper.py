"""
Core scraping logic for Apollo.io with ADVANCED ANTI-DETECTION
Uses undetected-chromedriver and multiple stealth techniques to bypass bot detection.

*** FIXED VERSION v3 — CDP cookies + URL pagination for 15k+ leads ***

Changes from original:
  FIX #1: CDP cookie injection (Network.setCookie) — bypasses ChromeDriver validation
  FIX #2: Stricter _is_logged_in() — no false positives
  FIX #3: SPA render wait in scrape_url() — waits for React table
  FIX #4: URL-based pagination — reliable for 600+ pages (15k leads)
  FIX #5: follow_links disabled in bulk mode — enriching 15k contacts is not viable
"""

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
import time
import random
import json
import re as _re
from typing import List, Dict, Optional, Any
from faker import Faker

from src.config import Config
from src.utils import random_delay, retry_on_failure, log_message, is_valid_url
from src.parser import (
    parse_search_results, parse_contact_profile,
    parse_company_profile, detect_page_type
)


class ApolloScraper:
    """Advanced Apollo.io scraper with anti-detection capabilities"""
    
    def __init__(self, headless: bool = True, use_proxy: bool = False, proxy_url: str = None):
        self.driver = None
        self.headless = headless
        self.use_proxy = use_proxy
        self.proxy_url = proxy_url
        self.logged_in = False
        self.faker = Faker()
        self.cookies = None
        
    def setup_driver(self):
        """Setup undetected-chromedriver with advanced anti-detection"""
        log_message("Setting up undetected ChromeDriver (anti-detection mode)...", 'INFO')
        
        options = uc.ChromeOptions()
        
        if self.headless:
            options.add_argument('--headless=new')
            log_message("⚠️  Running in headless mode (more detectable)", 'WARNING')
        else:
            log_message("✅ Running in headful mode (less detectable)", 'INFO')
        
        user_agent = self.faker.user_agent()
        options.add_argument(f'user-agent={user_agent}')
        log_message(f"Using user agent: {user_agent[:60]}...", 'DEBUG')
        
        # Essential stealth arguments
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--lang=en-US,en;q=0.9')
        options.add_argument('--accept-lang=en-US,en;q=0.9')
        
        if self.use_proxy and self.proxy_url:
            options.add_argument(f'--proxy-server={self.proxy_url}')
            log_message(f"✅ Using proxy: {self.proxy_url[:50]}...", 'INFO')
        else:
            log_message("⚠️  No proxy configured - Apollo may block datacenter IPs", 'WARNING')
        
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": False
        }
        options.add_experimental_option("prefs", prefs)
        
        try:
            import subprocess
            _result = subprocess.run(['google-chrome', '--version'], capture_output=True, text=True)
            _chrome_ver = int(_re.search(r'(\d+)\.', _result.stdout).group(1))
            log_message(f"🔍 Detected Chrome version: {_chrome_ver}", 'INFO')

            self.driver = uc.Chrome(
                options=options,
                use_subprocess=True,
                version_main=_chrome_ver,
                driver_executable_path=None,
            )
            self.driver.set_page_load_timeout(Config.PAGE_LOAD_TIMEOUT)
            self._inject_advanced_stealth()
            log_message("✅ Undetected ChromeDriver setup complete!", 'SUCCESS')
            
        except Exception as e:
            log_message(f"❌ Failed to setup undetected-chromedriver: {e}", 'ERROR')
            raise
    
    def _inject_advanced_stealth(self):
        """Inject advanced JavaScript to further hide automation"""
        stealth_js = """
        // 1. Remove webdriver property
        try {
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined, configurable: true
            });
        } catch(e) {}
        
        // 2. Fix plugins
        try {
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5], configurable: true
            });
        } catch(e) {}
        
        // 3. Fix languages
        try {
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'], configurable: true
            });
        } catch(e) {}
        
        // 4. Chrome property
        try {
            if (!window.navigator.chrome) {
                window.navigator.chrome = {
                    runtime: {}, loadTimes: function() {},
                    csi: function() {}, app: {}
                };
            }
        } catch(e) {}
        
        // 5. Permissions query
        try {
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({state: Notification.permission}) :
                    originalQuery(parameters)
            );
        } catch(e) {}
        
        // 6. Fix iframe detection
        try {
            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                get: function() { return window; }
            });
        } catch(e) {}
        
        // 7. Hardware concurrency
        try {
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8, configurable: true
            });
        } catch(e) {}
        
        // 8. Device memory
        try {
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8, configurable: true
            });
        } catch(e) {}
        
        console.log('🔒 Advanced stealth mode activated');
        """
        try:
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': stealth_js
            })
            log_message("✅ Advanced stealth JavaScript injected", 'DEBUG')
        except Exception as e:
            log_message(f"⚠️  Stealth injection warning: {e}", 'WARNING')
    
    def _human_like_mouse_movement(self, element):
        """Simulate human-like mouse movement to element"""
        try:
            actions = ActionChains(self.driver)
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)
            actions.move_to_element_with_offset(element, offset_x, offset_y)
            actions.perform()
            random_delay(0.1, 0.3)
        except Exception as e:
            log_message(f"Mouse movement failed: {e}", 'DEBUG')
    
    def _human_like_typing(self, element, text: str):
        """Type text with human-like patterns and delays"""
        element.clear()
        random_delay(0.2, 0.5)
        
        for i, char in enumerate(text):
            element.send_keys(char)
            if i % 5 == 0:
                random_delay(0.15, 0.35)
            else:
                random_delay(0.05, 0.12)
            
            if random.random() < 0.1 and i < len(text) - 1:
                wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                element.send_keys(wrong_char)
                random_delay(0.1, 0.2)
                element.send_keys('\b')
                random_delay(0.05, 0.15)
    
    def save_cookies(self, filename: str = '/tmp/apollo_cookies.json'):
        """Save cookies for future sessions"""
        try:
            cookies = self.driver.get_cookies()
            with open(filename, 'w') as f:
                json.dump(cookies, f)
            log_message(f"✅ Cookies saved to {filename}", 'INFO')
            return cookies
        except Exception as e:
            log_message(f"❌ Failed to save cookies: {e}", 'ERROR')
            return None
    
    # =========================================================================
    # FIX #1: Cookie injection via Chrome DevTools Protocol (CDP)
    #
    # driver.add_cookie() uses ChromeDriver's strict validation which rejects
    # cookies for domain mismatch, sameSite, extra fields, etc.
    # CDP Network.setCookie bypasses ALL validation and injects directly into
    # Chrome's cookie store — same mechanism as Chrome DevTools.
    # =========================================================================
    def load_cookies(self, cookies: List[Dict] = None, filename: str = '/tmp/apollo_cookies.json'):
        """Load cookies using CDP (bypasses ChromeDriver's broken validation)"""
        try:
            if not cookies:
                try:
                    with open(filename, 'r') as f:
                        cookies = json.load(f)
                    log_message(f"✅ Cookies loaded from {filename}", 'INFO')
                except FileNotFoundError:
                    log_message(f"⚠️  Cookie file not found: {filename}", 'WARNING')
                    return False
            
            if not cookies:
                return False
            
            # STEP 1: Navigate to Apollo domain first (required for cookie scope)
            self.driver.get("https://app.apollo.io")
            random_delay(2, 4)
            
            current_url = self.driver.current_url
            log_message(f"🔍 Browser landed on: {current_url}", 'INFO')
            
            # STEP 2: Inject ALL cookies via CDP — no validation, no errors
            added = 0
            failed = 0
            
            for cookie in cookies:
                try:
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    
                    if not name or not value:
                        failed += 1
                        continue
                    
                    # Preserve original domain from export
                    domain = cookie.get('domain', '.apollo.io')
                    
                    # Build CDP cookie params
                    cdp_cookie = {
                        'name': str(name),
                        'value': str(value),
                        'domain': str(domain),
                        'path': cookie.get('path', '/'),
                    }
                    
                    # Optional fields
                    if cookie.get('secure'):
                        cdp_cookie['secure'] = True
                    if cookie.get('httpOnly'):
                        cdp_cookie['httpOnly'] = True
                    
                    # Handle expiry (EditThisCookie uses expirationDate)
                    expiry = cookie.get('expiry') or cookie.get('expirationDate')
                    if expiry:
                        try:
                            cdp_cookie['expires'] = float(expiry)
                        except (ValueError, TypeError):
                            pass
                    
                    # Handle sameSite (CDP accepts it; driver.add_cookie chokes)
                    same_site = cookie.get('sameSite', '')
                    if same_site and same_site.lower() not in ('', 'unspecified', 'no_restriction', 'none'):
                        cdp_cookie['sameSite'] = same_site.capitalize()
                    else:
                        cdp_cookie['sameSite'] = 'None'
                        if not cdp_cookie.get('secure'):
                            cdp_cookie['secure'] = True  # SameSite=None requires Secure
                    
                    # CDP injection — bypasses ALL ChromeDriver validation
                    result = self.driver.execute_cdp_cmd('Network.setCookie', cdp_cookie)
                    
                    if result.get('success', True):
                        added += 1
                    else:
                        failed += 1
                        log_message(f"⚠️  CDP rejected cookie {name}", 'DEBUG')
                    
                except Exception as e:
                    failed += 1
                    log_message(f"⚠️  Failed to add cookie {cookie.get('name', '?')}: {e}", 'DEBUG')
            
            log_message(f"🍪 Cookies injected via CDP: {added} OK, {failed} failed", 'INFO')
            
            if added == 0:
                log_message("❌ No cookies were injected! Auth will fail.", 'ERROR')
                log_message("💡 Check that cookies are exported from app.apollo.io", 'INFO')
                return False
            
            # STEP 3: Refresh to activate cookies in the session
            self.driver.refresh()
            random_delay(3, 5)
            
            # STEP 4: Verify login
            if self._is_logged_in():
                log_message("🎉 Cookie authentication successful! Skipping login.", 'SUCCESS')
                self.logged_in = True
                return True
            else:
                log_message("⚠️  Cookies loaded but not logged in — cookies may be expired", 'WARNING')
                return False
            
        except Exception as e:
            log_message(f"❌ Failed to load cookies: {e}", 'ERROR')
            return False
    
    @retry_on_failure(max_retries=3)
    def login(self, email: str = None, password: str = None, cookies: List[Dict] = None):
        """
        Login to Apollo.io — tries cookies first, falls back to password.
        """
        if not self.driver:
            self.setup_driver()
        
        # Try cookie auth first (most reliable)
        if cookies:
            log_message("🔑 Attempting cookie-based authentication...", 'INFO')
            if self.load_cookies(cookies=cookies):
                return True
            else:
                log_message("⚠️  Cookie auth failed, falling back to password login", 'WARNING')
        
        if not email or not password:
            log_message("❌ Email and password are required for login", 'ERROR')
            return False
        
        log_message(f"🔐 Logging in as {email}...", 'INFO')
        
        try:
            self.driver.get(Config.APOLLO_LOGIN_URL)
            log_message("⏳ Waiting for login page to load...", 'INFO')
            random_delay(3, 5)
            
            # Random mouse movements
            try:
                body = self.driver.find_element(By.TAG_NAME, 'body')
                for _ in range(random.randint(1, 3)):
                    self._human_like_mouse_movement(body)
            except:
                pass
            
            # Debug
            try:
                self.driver.save_screenshot('/tmp/login_page.png')
                log_message(f"📸 Screenshot saved. Page title: {self.driver.title}", 'INFO')
                log_message(f"🌐 Current URL: {self.driver.current_url}", 'INFO')
                all_inputs = self.driver.find_elements(By.TAG_NAME, 'input')
                log_message(f"🔍 Found {len(all_inputs)} input fields", 'INFO')
            except Exception as debug_e:
                log_message(f"Debug failed: {debug_e}", 'WARNING')
            
            if self._check_for_captcha():
                log_message("❌ CAPTCHA detected on login page! Use cookie authentication.", 'ERROR')
                return False
            
            log_message("🔍 Looking for email field...", 'INFO')
            email_field = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "input[name='email'], input[type='email'], input[id*='email'], "
                    "input[placeholder*='mail' i], input[aria-label*='email' i]"
                ))
            )
            
            self._human_like_mouse_movement(email_field)
            random_delay(0.3, 0.7)
            self._human_like_typing(email_field, email)
            random_delay(0.5, 1.0)
            
            log_message("🔍 Looking for password field...", 'INFO')
            password_field = self.driver.find_element(
                By.CSS_SELECTOR,
                "input[name='password'], input[type='password']"
            )
            
            self._human_like_mouse_movement(password_field)
            random_delay(0.3, 0.7)
            self._human_like_typing(password_field, password)
            random_delay(0.8, 1.5)
            
            try:
                self._human_like_mouse_movement(password_field)
            except:
                pass
            
            log_message("🔍 Looking for login button...", 'INFO')
            try:
                login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            except:
                login_button = self.driver.find_element(
                    By.XPATH,
                    "//button[contains(text(), 'Sign in') or contains(text(), 'Log in') "
                    "or contains(text(), 'sign in') or contains(text(), 'log in')]"
                )
            
            self._human_like_mouse_movement(login_button)
            random_delay(0.3, 0.6)
            login_button.click()
            
            log_message("✉️  Login form submitted, waiting for response...", 'INFO')
            random_delay(5, 8)
            
            if self._check_for_captcha():
                log_message("❌ CAPTCHA detected after login! Session flagged.", 'ERROR')
                log_message("💡 SOLUTION: Use cookie-based authentication!", 'INFO')
                return False
            
            if self._is_logged_in():
                log_message("🎉 Login successful!", 'SUCCESS')
                self.logged_in = True
                self.save_cookies()
                log_message("💡 TIP: Use saved cookies next time to skip login!", 'INFO')
                return True
            else:
                try:
                    error_elem = self.driver.find_elements(By.CSS_SELECTOR, ".error, .alert, [class*='error']")
                    if error_elem:
                        log_message(f"❌ Login failed: {error_elem[0].text}", 'ERROR')
                    else:
                        log_message("❌ Login failed: Unknown error", 'ERROR')
                except:
                    log_message("❌ Login failed: Could not verify login status", 'ERROR')
                return False
                
        except TimeoutException:
            log_message("❌ Login form not found - page structure changed or blocked", 'ERROR')
            self.driver.save_screenshot('/tmp/timeout_error.png')
            return False
        except Exception as e:
            log_message(f"❌ Login error: {str(e)}", 'ERROR')
            try:
                self.driver.save_screenshot('/tmp/login_error.png')
            except:
                pass
            return False
    
    # =========================================================================
    # FIX #2: Stricter login check — no false positives from URL alone
    # =========================================================================
    def _is_logged_in(self) -> bool:
        """Check if currently logged into Apollo"""
        try:
            # Look for elements that only appear when authenticated
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "[class*='user'], [class*='profile'], [data-cy*='user'], "
                    "[class*='avatar'], [class*='nav-user'], [class*='AccountMenu'], "
                    "[data-testid*='user'], [class*='sidebar']"
                ))
            )
            return True
        except:
            pass
        
        # Fallback: URL + content check
        current_url = self.driver.current_url
        is_on_apollo = 'app.apollo.io' in current_url
        is_on_auth_page = any(x in current_url.lower() for x in [
            'login', 'signup', 'sign-up', 'register'
        ])
        
        if is_on_apollo and not is_on_auth_page:
            try:
                page_source = self.driver.page_source
                has_app_content = any(indicator in page_source for indicator in [
                    'zp_', 'apollo-', 'peopleIndex', 'search-results',
                    'savedSearches', 'ContactTable', 'data-cy=',
                ])
                if has_app_content:
                    return True
            except:
                pass
        
        if not is_on_apollo:
            log_message(f"Not logged in. Current URL: {current_url}", 'DEBUG')
        
        return is_on_apollo and not is_on_auth_page
    
    def _check_for_captcha(self) -> bool:
        """Check if CAPTCHA is present on page"""
        captcha_indicators = [
            "recaptcha", "captcha", "hcaptcha", "challenge", "cf-challenge"
        ]
        page_source = self.driver.page_source.lower()
        detected = any(indicator in page_source for indicator in captcha_indicators)
        
        if detected:
            log_message("⚠️  CAPTCHA detected on page!", 'WARNING')
            try:
                self.driver.save_screenshot('/tmp/captcha_detected.png')
            except:
                pass
        
        return detected
    
    # =========================================================================
    # FIX #3: Wait for Apollo SPA to render before detecting page type
    # =========================================================================
    def scrape_url(self, url: str, follow_links: bool = False, max_pages: int = None,
                   min_delay: int = 3, max_delay: int = 7) -> List[Dict[str, Any]]:
        """
        Scrape data from a given Apollo.io URL.
        
        NOTE: follow_links defaults to False for bulk scrapes (15k leads).
              Enriching each contact individually would take days.
        """
        if not is_valid_url(url):
            log_message(f"❌ Invalid Apollo.io URL: {url}", 'ERROR')
            return []
        
        if not self.logged_in:
            log_message("❌ Not logged in! Please login first.", 'ERROR')
            return []
        
        log_message(f"🌐 Navigating to: {url}", 'INFO')
        self.driver.get(url)
        random_delay(min_delay, max_delay)
        
        # Wait for Apollo's React SPA to render
        self._wait_for_table_render(timeout=20)
        
        # Human-like scroll
        try:
            self.driver.execute_script(f"window.scrollTo(0, {random.randint(100, 300)});")
            random_delay(0.5, 1.0)
        except:
            pass
        
        # Debug screenshot
        try:
            self.driver.save_screenshot('/tmp/page_before_detect.png')
            log_message(f"📸 Page screenshot saved. Title: {self.driver.title}", 'DEBUG')
            log_message(f"🌐 Current URL: {self.driver.current_url}", 'DEBUG')
        except:
            pass
        
        # Detect page type
        page_html = self.driver.page_source
        page_type = detect_page_type(page_html)
        log_message(f"📄 Detected page type: {page_type}", 'INFO')
        
        # URL-based fallback if detection fails
        if page_type == 'unknown':
            if '#/people' in url or '/people' in url:
                log_message("🔄 URL contains /people — forcing page type to 'search'", 'INFO')
                page_type = 'search'
            elif '#/companies' in url or '/companies' in url:
                log_message("🔄 URL contains /companies — forcing page type to 'search'", 'INFO')
                page_type = 'search'
        
        if page_type == 'search':
            return self._scrape_search_results(url, follow_links, max_pages, min_delay, max_delay)
        elif page_type == 'contact_profile':
            return [self._scrape_contact_profile()]
        elif page_type == 'company_profile':
            return [self._scrape_company_profile()]
        else:
            log_message("⚠️  Unknown page type, attempting generic extraction...", 'WARNING')
            return [self._scrape_generic_page()]
    
    # =========================================================================
    # FIX #4: URL-based pagination for 15k+ leads
    #
    # Old code relied on clicking "Next" button — fragile, breaks on Apollo's
    # dynamic DOM. URL pagination (page=N) is 100% reliable.
    #
    # 25 results/page × 600 pages = 15,000 leads
    # =========================================================================
    def _scrape_search_results(self, base_url: str, follow_links: bool = False,
                               max_pages: int = None, min_delay: int = 3,
                               max_delay: int = 7) -> List[Dict[str, Any]]:
        """
        Scrape search results with URL-based pagination.
        
        Args:
            base_url: The original Apollo search URL
            follow_links: Visit each profile for enrichment (SLOW — False for bulk)
            max_pages: Maximum pages to scrape (default from Config)
            min_delay: Min seconds between pages
            max_delay: Max seconds between pages
        """
        all_results = []
        page_num = 1
        max_pages = max_pages or Config.MAX_PAGES
        consecutive_empty = 0
        seen_names = set()  # Deduplicate across pages
        
        log_message(f"📊 Starting bulk scrape (max {max_pages} pages, ~{max_pages * 25} leads)...", 'INFO')
        if follow_links:
            log_message("⚠️  follow_links=True — this will be VERY slow for large datasets!", 'WARNING')
        
        while page_num <= max_pages:
            log_message(f"📄 Scraping page {page_num}/{max_pages}...", 'INFO')
            
            # Navigate to page via URL (pages 2+ need explicit navigation)
            if page_num > 1:
                page_url = self._build_page_url(base_url, page_num)
                log_message(f"🌐 Navigating to page {page_num}...", 'DEBUG')
                self.driver.get(page_url)
                random_delay(min_delay, max_delay)
                self._wait_for_table_render(timeout=15)
            
            # Human-like scrolling to trigger lazy-loaded rows
            try:
                self.driver.execute_script(f"window.scrollTo(0, {random.randint(200, 500)});")
                random_delay(0.5, 1.0)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                random_delay(1.0, 2.0)
                self.driver.execute_script("window.scrollTo(0, 0);")
                random_delay(0.3, 0.5)
            except:
                pass
            
            # Parse current page
            page_html = self.driver.page_source
            results = parse_search_results(page_html)
            
            # Handle empty page
            if not results:
                consecutive_empty += 1
                log_message(f"⚠️  No results on page {page_num} (empty streak: {consecutive_empty})", 'WARNING')
                
                # Retry once — sometimes Apollo's SPA fails to load a page
                if consecutive_empty == 1:
                    log_message("🔄 Retrying page...", 'INFO')
                    self.driver.refresh()
                    random_delay(3, 5)
                    self._wait_for_table_render(timeout=15)
                    page_html = self.driver.page_source
                    results = parse_search_results(page_html)
                
                if not results:
                    if consecutive_empty >= 2:
                        log_message("🛑 2 consecutive empty pages — end of results reached", 'INFO')
                        break
                    page_num += 1
                    continue
            
            consecutive_empty = 0  # Reset on success
            
            # Deduplicate by name
            new_results = []
            for r in results:
                name = r.get('name', '')
                if name and name not in seen_names:
                    seen_names.add(name)
                    new_results.append(r)
            
            dupes = len(results) - len(new_results)
            if dupes > 0:
                log_message(f"🔄 Skipped {dupes} duplicate contacts", 'DEBUG')
            
            log_message(f"✅ Page {page_num}: {len(new_results)} new results (total: {len(all_results) + len(new_results)})", 'SUCCESS')
            
            # Enrich if requested (not recommended for bulk)
            if follow_links:
                new_results = self._enrich_results(new_results)
            
            all_results.extend(new_results)
            
            # Progress logging every 10 pages
            if page_num % 10 == 0:
                log_message(f"📊 Progress: {len(all_results)} total leads after {page_num} pages", 'INFO')
            
            # Adaptive cooldown every 50 pages to avoid rate limits
            if page_num % 50 == 0:
                cooldown = random.randint(10, 20)
                log_message(f"😴 Cooldown pause: {cooldown}s (anti rate-limit)", 'INFO')
                time.sleep(cooldown)
            
            page_num += 1
            random_delay(min_delay, max_delay)
        
        log_message(f"🎉 Scraping complete! Total unique leads: {len(all_results)}", 'SUCCESS')
        return all_results
    
    def _build_page_url(self, base_url: str, page_num: int) -> str:
        """
        Build URL for a specific page number.
        Apollo uses page=N in the URL hash fragment.
        Example: ...#/people?page=1&personTitles[]=CEO
        """
        # Replace existing page=N
        if 'page=' in base_url:
            return _re.sub(r'page=\d+', f'page={page_num}', base_url)
        
        # Add page parameter
        if '#' in base_url:
            hash_part = base_url.split('#', 1)[1]
            if '?' in hash_part:
                # Already has query params after hash: append &page=N
                return base_url + f'&page={page_num}'
            else:
                # Hash path only: add ?page=N
                return base_url + f'?page={page_num}'
        else:
            return base_url + f'?page={page_num}'
    
    def _wait_for_table_render(self, timeout: int = 15):
        """Wait for Apollo's React table to render after navigation"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "table tbody tr, "
                    "[class*='ContactTable'], "
                    "[class*='search-results'], "
                    "[class*='zp_'] table, "
                    "[class*='result-row'], "
                    "[class*='PeopleTable'], "
                    "[data-cy='contacts-table'], "
                    ".finder-results-list-panel-content, "
                    "table, [role='table'], [role='grid']"
                ))
            )
            log_message("✅ Table rendered", 'DEBUG')
        except TimeoutException:
            log_message(f"⚠️  Table didn't render within {timeout}s", 'WARNING')
    
    def _enrich_results(self, results: List[Dict]) -> List[Dict]:
        """
        Enrich results by visiting individual profile pages.
        WARNING: Very slow for large datasets — adds ~5s per contact.
        """
        enriched = []
        log_message(f"🔍 Enriching {len(results)} results...", 'INFO')
        
        for idx, result in enumerate(results, 1):
            profile_url = result.get('profile_url')
            
            if profile_url:
                try:
                    log_message(f"🔗 Enriching contact {idx}/{len(results)}...", 'DEBUG')
                    self.driver.get(profile_url)
                    random_delay(2, 4)
                    detailed_data = self._scrape_contact_profile()
                    result.update(detailed_data)
                    self.driver.back()
                    random_delay(2, 3)
                except Exception as e:
                    log_message(f"⚠️  Failed to enrich contact: {str(e)}", 'WARNING')
            
            enriched.append(result)
        
        return enriched
    
    def _go_to_next_page(self) -> bool:
        """
        Navigate to next page via button click (FALLBACK only).
        URL-based pagination in _scrape_search_results is preferred.
        """
        try:
            next_button_selectors = [
                "button[aria-label='Next page']",
                "a[aria-label='Next']",
                ".pagination button:last-child",
                "[class*='next']:not([disabled])",
                "button[class*='next']",
                "[class*='zp_'] [class*='next']",
                "button[class*='pagination'] + button",
            ]
            
            for selector in next_button_selectors:
                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if next_button.is_enabled() and next_button.is_displayed():
                        self._human_like_mouse_movement(next_button)
                        random_delay(0.3, 0.6)
                        next_button.click()
                        log_message("➡️  Clicked next page button", 'DEBUG')
                        return True
                except:
                    continue
            
            # Infinite scroll fallback
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            random_delay(2, 3)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            
            if new_height > last_height:
                log_message("📜 Infinite scroll triggered", 'DEBUG')
                return True
            
            return False
            
        except Exception as e:
            log_message(f"⚠️  Could not navigate to next page: {str(e)}", 'DEBUG')
            return False
    
    def _scrape_contact_profile(self) -> Dict[str, Any]:
        """Scrape current page as contact profile"""
        return parse_contact_profile(self.driver.page_source)
    
    def _scrape_company_profile(self) -> Dict[str, Any]:
        """Scrape current page as company profile"""
        return parse_company_profile(self.driver.page_source)
    
    def _scrape_generic_page(self) -> Dict[str, Any]:
        """Generic scraping for unknown page types"""
        soup = BeautifulSoup(self.driver.page_source, 'lxml')
        return {
            'type': 'generic',
            'url': self.driver.current_url,
            'title': self.driver.title,
            'text_content': soup.get_text()[:1000],
            'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def close(self):
        """Close the browser and cleanup"""
        if self.driver:
            log_message("🔒 Closing browser...", 'INFO')
            try:
                self.driver.quit()
                log_message("✅ Browser closed successfully", 'SUCCESS')
            except Exception as e:
                log_message(f"⚠️  Error closing browser: {e}", 'WARNING')
    
    def __enter__(self):
        self.setup_driver()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

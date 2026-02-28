"""
Core scraping logic for Apollo.io with ADVANCED ANTI-DETECTION
Uses undetected-chromedriver and multiple stealth techniques to bypass bot detection.
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
        """
        Initialize the Apollo scraper with anti-detection.
        
        Args:
            headless: Run browser in headless mode (Note: headless is more detectable)
            use_proxy: Use proxy settings
            proxy_url: Proxy URL to use
        """
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
        
        # Prepare options for undetected-chromedriver
        options = uc.ChromeOptions()
        
        # Note: Headless mode is MORE detectable. Only use if absolutely necessary.
        if self.headless:
            options.add_argument('--headless=new')
            log_message("⚠️  Running in headless mode (more detectable)", 'WARNING')
        else:
            log_message("✅ Running in headful mode (less detectable)", 'INFO')
        
        # Generate realistic user agent using Faker
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
        
        # Disable automation flags
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        
        # Language settings (looks more human)
        options.add_argument('--lang=en-US,en;q=0.9')
        options.add_argument('--accept-lang=en-US,en;q=0.9')
        
        # Proxy configuration
        if self.use_proxy and self.proxy_url:
            options.add_argument(f'--proxy-server={self.proxy_url}')
            log_message(f"✅ Using proxy: {self.proxy_url[:50]}...", 'INFO')
        else:
            log_message("⚠️  No proxy configured - Apollo may block datacenter IPs", 'WARNING')
        
        # Additional prefs to avoid detection
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
        # Note: excludeSwitches and useAutomationExtension are handled automatically by undetected-chromedriver
        # No need to set them manually - uc.Chrome() does this for us!
        
        try:
            # Initialize undetected-chromedriver
        
            # Auto-detect installed Chrome major version
            import subprocess, re
            _result = subprocess.run(['google-chrome', '--version'], capture_output=True, text=True)
            _chrome_ver = int(re.search(r'(\d+)\.', _result.stdout).group(1))
            log_message(f"🔍 Detected Chrome version: {_chrome_ver}", 'INFO')

            self.driver = uc.Chrome(
                options=options,
                use_subprocess=True,  # Better for avoiding detection
                version_main=_chrome_ver,  # Match installed Chrome version
                driver_executable_path=None,  # Let uc find it
            )
            # Set page load timeout
            self.driver.set_page_load_timeout(Config.PAGE_LOAD_TIMEOUT)
            
            # Additional stealth measures
            self._inject_advanced_stealth()
            
            log_message("✅ Undetected ChromeDriver setup complete!", 'SUCCESS')
            
        except Exception as e:
            log_message(f"❌ Failed to setup undetected-chromedriver: {e}", 'ERROR')
            raise
    
    def _inject_advanced_stealth(self):
        """Inject advanced JavaScript to further hide automation"""
        stealth_js = """
        // Advanced stealth script - handles multiple detection vectors
        
        // 1. Remove webdriver property
        try {
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
        } catch(e) {}
        
        // 2. Fix plugins (make it look populated)
        try {
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
                configurable: true
            });
        } catch(e) {}
        
        // 3. Fix languages (common detection point)
        try {
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
                configurable: true
            });
        } catch(e) {}
        
        // 4. Chrome property
        try {
            if (!window.navigator.chrome) {
                window.navigator.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
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
                get: function() {
                    return window;
                }
            });
        } catch(e) {}
        
        // 7. Mock hardware concurrency (common detection)
        try {
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8,
                configurable: true
            });
        } catch(e) {}
        
        // 8. Mock device memory
        try {
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8,
                configurable: true
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
            # Move to element with a slight random offset
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
            
            # Variable typing speed - humans don't type at constant speed
            if i % 5 == 0:  # Occasional pause (thinking)
                random_delay(0.15, 0.35)
            else:
                random_delay(0.05, 0.12)
            
            # Random typo and correction (10% chance)
            if random.random() < 0.1 and i < len(text) - 1:
                wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                element.send_keys(wrong_char)
                random_delay(0.1, 0.2)
                element.send_keys('\b')  # Backspace
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
    
    def load_cookies(self, cookies: List[Dict] = None, filename: str = '/tmp/apollo_cookies.json'):
        """Load cookies from file or list"""
        try:
            if not cookies:
                # Try to load from file
                try:
                    with open(filename, 'r') as f:
                        cookies = json.load(f)
                    log_message(f"✅ Cookies loaded from {filename}", 'INFO')
                except FileNotFoundError:
                    log_message(f"⚠️  Cookie file not found: {filename}", 'WARNING')
                    return False
            
            if cookies:
                # Navigate to domain first (required for setting cookies)
                self.driver.get("https://app.apollo.io")
                random_delay(1, 2)
                
                # Add cookies
                for cookie in cookies:
                    try:
                        # Remove expiry if it's in the past
                        if 'expiry' in cookie:
                            cookie['expiry'] = int(cookie['expiry'])
                        self.driver.add_cookie(cookie)
                    except Exception as e:
                        log_message(f"⚠️  Failed to add cookie: {e}", 'DEBUG')
                
                log_message("✅ Cookies loaded successfully!", 'SUCCESS')
                
                # Refresh to apply cookies
                self.driver.refresh()
                random_delay(2, 3)
                
                # Check if cookies worked (are we logged in?)
                if self._is_logged_in():
                    log_message("🎉 Cookie authentication successful! Skipping login.", 'SUCCESS')
                    self.logged_in = True
                    return True
                else:
                    log_message("⚠️  Cookies loaded but not logged in", 'WARNING')
                    return False
            
            return False
            
        except Exception as e:
            log_message(f"❌ Failed to load cookies: {e}", 'ERROR')
            return False
    
    @retry_on_failure(max_retries=3)
    def login(self, email: str = None, password: str = None, cookies: List[Dict] = None):
        """
        Login to Apollo.io account with cookie support.
        
        Args:
            email: Apollo email
            password: Apollo password
            cookies: Pre-saved cookies to skip login (RECOMMENDED)
        
        Returns:
            True if login successful
        """
        if not self.driver:
            self.setup_driver()
        
        # BEST PRACTICE: Try cookie-based authentication first
        if cookies:
            log_message("🔑 Attempting cookie-based authentication...", 'INFO')
            if self.load_cookies(cookies=cookies):
                return True
            else:
                log_message("⚠️  Cookie auth failed, falling back to password login", 'WARNING')
        
        # Fallback to password-based login
        if not email or not password:
            log_message("❌ Email and password are required for login", 'ERROR')
            return False
        
        log_message(f"🔐 Logging in as {email}...", 'INFO')
        
        try:
            # Navigate to login page
            self.driver.get(Config.APOLLO_LOGIN_URL)
            
            # Wait for page to load with human-like delay
            log_message("⏳ Waiting for login page to load...", 'INFO')
            random_delay(3, 5)
            
            # Random mouse movements (humans move mouse around)
            try:
                body = self.driver.find_element(By.TAG_NAME, 'body')
                for _ in range(random.randint(1, 3)):
                    self._human_like_mouse_movement(body)
            except:
                pass
            
            # Debug logging
            try:
                self.driver.save_screenshot('/tmp/login_page.png')
                log_message(f"📸 Screenshot saved. Page title: {self.driver.title}", 'INFO')
                log_message(f"🌐 Current URL: {self.driver.current_url}", 'INFO')
                
                all_inputs = self.driver.find_elements(By.TAG_NAME, 'input')
                log_message(f"🔍 Found {len(all_inputs)} input fields", 'INFO')
            except Exception as debug_e:
                log_message(f"Debug failed: {debug_e}", 'WARNING')
            
            # Check for CAPTCHA before attempting login
            if self._check_for_captcha():
                log_message("❌ CAPTCHA detected on login page! Use cookie authentication instead.", 'ERROR')
                return False
            
            # Wait for email field with multiple selectors
            log_message("🔍 Looking for email field...", 'INFO')
            email_field = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR, 
                    "input[name='email'], input[type='email'], input[id*='email'], input[placeholder*='mail' i], input[aria-label*='email' i]"
                ))
            )
            
            # Human-like interaction with email field
            self._human_like_mouse_movement(email_field)
            random_delay(0.3, 0.7)
            self._human_like_typing(email_field, email)
            random_delay(0.5, 1.0)
            
            # Find and fill password field
            log_message("🔍 Looking for password field...", 'INFO')
            password_field = self.driver.find_element(
                By.CSS_SELECTOR, 
                "input[name='password'], input[type='password']"
            )
            
            self._human_like_mouse_movement(password_field)
            random_delay(0.3, 0.7)
            self._human_like_typing(password_field, password)
            random_delay(0.8, 1.5)
            
            # Random mouse movement before clicking submit
            try:
                self._human_like_mouse_movement(password_field)
            except:
                pass
            
            # Find and click login button
            log_message("🔍 Looking for login button...", 'INFO')
            try:
                login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            except:
                login_button = self.driver.find_element(
                    By.XPATH, 
                    "//button[contains(text(), 'Sign in') or contains(text(), 'Log in') or contains(text(), 'sign in') or contains(text(), 'log in')]"
                )
            
            self._human_like_mouse_movement(login_button)
            random_delay(0.3, 0.6)
            login_button.click()
            
            log_message("✉️  Login form submitted, waiting for response...", 'INFO')
            random_delay(5, 8)
            
            # Check for CAPTCHA after submission
            if self._check_for_captcha():
                log_message("❌ CAPTCHA detected after login! Apollo has flagged this session.", 'ERROR')
                log_message("💡 SOLUTION: Use cookie-based authentication instead!", 'INFO')
                return False
            
            # Verify login success
            if self._is_logged_in():
                log_message("🎉 Login successful!", 'SUCCESS')
                self.logged_in = True
                
                # Save cookies for future use
                self.save_cookies()
                log_message("💡 TIP: Use saved cookies next time to skip login!", 'INFO')
                
                return True
            else:
                # Check for error messages
                try:
                    error_elem = self.driver.find_elements(By.CSS_SELECTOR, ".error, .alert, [class*='error']")
                    if error_elem:
                        error_text = error_elem[0].text
                        log_message(f"❌ Login failed: {error_text}", 'ERROR')
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
    
    def _is_logged_in(self) -> bool:
        """Check if currently logged into Apollo"""
        try:
            # Check for elements that only appear when logged in
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR, 
                    "[class*='user'], [class*='profile'], [data-cy*='user'], [class*='avatar']"
                ))
            )
            return True
        except:
            # Check URL as fallback
            current_url = self.driver.current_url
            is_logged = 'login' not in current_url.lower() and 'app.apollo.io' in current_url
            
            if not is_logged:
                log_message(f"Not logged in. Current URL: {current_url}", 'DEBUG')
            
            return is_logged
    
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
                log_message("📸 CAPTCHA screenshot saved to /tmp/captcha_detected.png", 'INFO')
            except:
                pass
        
        return detected
    
    def scrape_url(self, url: str, follow_links: bool = True, max_pages: int = None, min_delay: int = 3, max_delay: int = 7) -> List[Dict[str, Any]]:
        """
        Scrape data from a given Apollo.io URL.
        
        Args:
            url: Apollo.io URL to scrape
            follow_links: Follow links to detail pages for enrichment
            max_pages: Maximum number of pages to scrape (for search results)
            min_delay: Minimum delay between requests (seconds)
            max_delay: Maximum delay between requests (seconds)
        
        Returns:
            List of extracted data dictionaries
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
        
        # Random human-like behavior
        try:
            # Scroll a bit (humans scroll)
            self.driver.execute_script(f"window.scrollTo(0, {random.randint(100, 300)});")
            random_delay(0.5, 1.0)
        except:
            pass
        
        # Detect page type
        page_html = self.driver.page_source
        page_type = detect_page_type(page_html)
        log_message(f"📄 Detected page type: {page_type}", 'INFO')
        
        if page_type == 'search':
            return self._scrape_search_results(follow_links, max_pages, min_delay, max_delay)
        elif page_type == 'contact_profile':
            return [self._scrape_contact_profile()]
        elif page_type == 'company_profile':
            return [self._scrape_company_profile()]
        else:
            log_message("⚠️  Unknown page type, attempting generic extraction...", 'WARNING')
            return [self._scrape_generic_page()]
    
    def _scrape_search_results(self, follow_links: bool = True, max_pages: int = None, min_delay: int = 3, max_delay: int = 7) -> List[Dict[str, Any]]:
        """
        Scrape search results page with pagination.
        
        Args:
            follow_links: Follow links to enrich contact data
            max_pages: Maximum pages to scrape
            min_delay: Minimum delay between pages
            max_delay: Maximum delay between pages
        
        Returns:
            List of all scraped results
        """
        all_results = []
        page_num = 1
        max_pages = max_pages or Config.MAX_PAGES
        log_message(f"📊 Starting search results scraping (max {max_pages} pages)...", 'INFO')
        
        while page_num <= max_pages:
            log_message(f"📄 Scraping page {page_num}/{max_pages}...", 'INFO')
            
            # Human-like behavior before scraping
            try:
                scroll_amount = random.randint(200, 500)
                self.driver.execute_script(f"window.scrollTo(0, {scroll_amount});")
                random_delay(0.5, 1.0)
            except:
                pass
            
            # Wait for results to load
            random_delay(min_delay, max_delay)
            
            # Get current page HTML
            page_html = self.driver.page_source
            
            # Parse results from current page
            results = parse_search_results(page_html)
            
            if not results:
                log_message("⚠️  No results found on this page, stopping pagination.", 'WARNING')
                break
            
            log_message(f"✅ Found {len(results)} results on page {page_num}", 'SUCCESS')
            
            # Enrich results by visiting detail pages
            if follow_links:
                results = self._enrich_results(results)
            
            all_results.extend(results)
            
            # Try to go to next page
            if not self._go_to_next_page():
                log_message("📄 No more pages available", 'INFO')
                break
            
            page_num += 1
            random_delay(min_delay, max_delay)
        
        log_message(f"🎉 Total results scraped: {len(all_results)}", 'SUCCESS')
        return all_results
    
    def _enrich_results(self, results: List[Dict]) -> List[Dict]:
        """
        Enrich results by following links to detail pages.
        
        Args:
            results: List of basic result dictionaries
        
        Returns:
            Enriched results
        """
        enriched = []
        
        log_message(f"🔍 Enriching {len(results)} results...", 'INFO')
        
        for idx, result in enumerate(results, 1):
            profile_url = result.get('profile_url')
            
            if profile_url:
                try:
                    log_message(f"🔗 Enriching contact {idx}/{len(results)}...", 'DEBUG')
                    
                    # Visit profile page
                    self.driver.get(profile_url)
                    random_delay(2, 4)
                    
                    # Parse detailed profile
                    detailed_data = self._scrape_contact_profile()
                    
                    # Merge with basic data
                    result.update(detailed_data)
                    
                    # Go back
                    self.driver.back()
                    random_delay(2, 3)
                    
                except Exception as e:
                    log_message(f"⚠️  Failed to enrich contact: {str(e)}", 'WARNING')
            
            enriched.append(result)
        
        return enriched
    
    def _go_to_next_page(self) -> bool:
        """
        Navigate to next page in search results.
        
        Returns:
            True if successfully navigated to next page, False otherwise
        """
        try:
            # Try different selectors for next button
            next_button_selectors = [
                "button[aria-label='Next page']",
                "a[aria-label='Next']",
                ".pagination button:last-child",
                "[class*='next']:not([disabled])",
                "button[class*='next']"
            ]
            
            for selector in next_button_selectors:
                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if next_button.is_enabled() and next_button.is_displayed():
                        # Human-like interaction
                        self._human_like_mouse_movement(next_button)
                        random_delay(0.3, 0.6)
                        next_button.click()
                        log_message("➡️  Clicked next page button", 'DEBUG')
                        return True
                except:
                    continue
            
            # Try infinite scroll as fallback
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
        page_html = self.driver.page_source
        return parse_contact_profile(page_html)
    
    def _scrape_company_profile(self) -> Dict[str, Any]:
        """Scrape current page as company profile"""
        page_html = self.driver.page_source
        return parse_company_profile(page_html)
    
    def _scrape_generic_page(self) -> Dict[str, Any]:
        """Generic scraping for unknown page types"""
        soup = BeautifulSoup(self.driver.page_source, 'lxml')
        
        return {
            'type': 'generic',
            'url': self.driver.current_url,
            'title': self.driver.title,
            'text_content': soup.get_text()[:1000],  # First 1000 chars
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
        """Context manager entry"""
        self.setup_driver()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


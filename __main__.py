"""
Apollo.io Scraper - Apify Actor
Main entry point for the Apify Actor

This actor scrapes Apollo.io using a free account (no paid API required).
Works forever with free accounts - no credits needed!
"""

from apify import Actor
from src.scraper import ApolloScraper
from src.utils import log_message, is_valid_url
import json


async def main():
    """
    Main Apify Actor entrypoint.
    
    Gets input from Apify input, scrapes Apollo.io, and pushes results to dataset.
    """
    async with Actor:
        # Get input
        actor_input = await Actor.get_input() or {}
        
        # Validate required inputs
        apollo_email = actor_input.get('apolloEmail')
        apollo_password = actor_input.get('apolloPassword')
        start_urls = actor_input.get('startUrls', [])
        
        if not apollo_email or not apollo_password:
            raise ValueError('Apollo.io email and password are required!')
        
        if not start_urls:
            raise ValueError('At least one start URL is required!')
        
        # Get configuration
        max_pages = actor_input.get('maxPages', 10)
        enrich_profiles = actor_input.get('enrichProfiles', True)
        min_delay = actor_input.get('minDelay', 3)
        max_delay = actor_input.get('maxDelay', 7)
        proxy_config = actor_input.get('proxyConfiguration')
        
        log_message(f"Starting Apollo scraper with {len(start_urls)} URLs")
        log_message(f"Max pages per URL: {max_pages}, Enrich profiles: {enrich_profiles}")
        
        # NOTE: Apollo.io detects Apify proxy - trying WITHOUT proxy first!
        # Get proxy URL if configured
        # Get proxy URL - supports direct proxyUrl OR proxyConfiguration
        proxy_url = actor_input.get('proxyUrl')
        
        if proxy_url:
            log_message(f"✅ Using direct proxy: {proxy_url[:50]}...", 'INFO')
        elif proxy_config:
            try:
                proxy_urls = proxy_config.get('proxyUrls', [])
                if proxy_urls and not proxy_config.get('useApifyProxy'):
                    # Use first custom proxy URL directly
                    proxy_url = proxy_urls[0]
                    log_message(f"✅ Using custom proxy: {proxy_url[:50]}...", 'INFO')
                elif proxy_config.get('useApifyProxy'):
                    log_message("⚠️  Apify proxy skipped - Apollo blocks datacenter IPs", 'WARNING')
                    proxy_url = None
            except Exception as e:
                log_message(f"Proxy setup failed: {e}", 'WARNING')
                proxy_url = None
        else:
            log_message("⚠️  No proxy configured - Apollo may block datacenter IPs", 'WARNING')
        
        # Initialize scraper
        scraper = None
        total_results = 0
        
        try:
            # Create scraper instance
            scraper = ApolloScraper(
                headless=True,  # Always headless on Apify
                use_proxy=proxy_url is not None,
                proxy_url=proxy_url
            )
            
            # Setup browser
            scraper.setup_driver()
            
            # Login to Apollo with cookie support
            log_message("🔐 Attempting to login to Apollo.io...")
            
            # Try to load saved cookies from Apify Key-Value Store
            saved_cookies = None
            try:
                kvs = await Actor.open_key_value_store()
                saved_cookies = await kvs.get_value('apollo_cookies')
                if saved_cookies:
                    log_message("✅ Found saved cookies in Key-Value Store", 'SUCCESS')
                else:
                    log_message("⚠️  No saved cookies found, will use password login", 'WARNING')
            except Exception as e:
                log_message(f"⚠️  Could not access Key-Value Store: {e}", 'WARNING')
            
            # Attempt login (will try cookies first if available)
            login_success = scraper.login(
                email=apollo_email,
                password=apollo_password,
                cookies=saved_cookies  # Pass cookies to new login method
            )
            
            if not login_success:
                raise RuntimeError('❌ Login to Apollo.io failed! Check credentials or try manual cookies.')
            
            # Save/update cookies to Key-Value Store for future runs
            if scraper.logged_in:
                try:
                    kvs = await Actor.open_key_value_store()
                    current_cookies = scraper.driver.get_cookies()
                    await kvs.set_value('apollo_cookies', current_cookies)
                    log_message("💾 Saved cookies to Key-Value Store for future runs", 'SUCCESS')
                    log_message("💡 TIP: Next run will use cookies and skip login!", 'INFO')
                except Exception as e:
                    log_message(f"⚠️  Could not save cookies: {e}", 'WARNING')
            
            # Process each URL
            for idx, url_obj in enumerate(start_urls):
                url = url_obj.get('url') if isinstance(url_obj, dict) else url_obj
                
                if not is_valid_url(url):
                    log_message(f"Skipping invalid URL: {url}", 'WARNING')
                    continue
                
                log_message(f"Processing URL {idx + 1}/{len(start_urls)}: {url}")
                
                try:
                    # Scrape the URL
                    results = scraper.scrape_url(
                        url=url,
                        follow_links=enrich_profiles,
                        max_pages=max_pages,
                        min_delay=min_delay,
                        max_delay=max_delay
                    )
                    
                    log_message(f"Scraped {len(results)} results from {url}", 'SUCCESS')
                    
                    # Push results to Apify dataset
                    if results:
                        await Actor.push_data(results)
                        total_results += len(results)
                    
                except Exception as e:
                    log_message(f"Error scraping {url}: {str(e)}", 'ERROR')
                    continue
            
            log_message(f"Scraping complete! Total results: {total_results}", 'SUCCESS')
            
        except Exception as e:
            log_message(f"Fatal error: {str(e)}", 'ERROR')
            raise
        
        finally:
            # Cleanup
            if scraper:
                scraper.close()
            
            log_message("Actor finished")


# Run the actor
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())



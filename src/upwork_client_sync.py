"""Upwork browser automation client using Playwright (Sync API)"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from .config import get_config, get_credentials, get_project_root
from .models import JobPosting, ClientInfo
from .logger import get_logger

logger = get_logger()


class UpworkClientSync:
    """Browser-based Upwork client for searching and scraping jobs (Sync version)"""
    
    UPWORK_LOGIN_URL = "https://www.upwork.com/ab/account-security/login"
    UPWORK_JOBS_URL = "https://www.upwork.com/nx/search/jobs"
    
    def __init__(self, headless: bool = True):
        self.config = get_config()
        self.credentials = get_credentials()
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None
        self.headless = headless
        
        # Browser state directory for persistent sessions
        self.state_dir = get_project_root() / "browser_state"
        self.state_dir.mkdir(exist_ok=True)
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def start(self):
        """Start the browser - connects to user's actual Chrome if available"""
        logger.info(f"Starting browser (headless={self.headless})...")
        self._playwright = sync_playwright().start()
        
        # Try to connect to user's actual Chrome first (best for avoiding detection)
        # User needs to start Chrome with: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
        try:
            self.browser = self._playwright.chromium.connect_over_cdp("http://localhost:9222")
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            logger.info("Connected to your Chrome browser via CDP")
        except Exception as e:
            logger.info(f"Could not connect to Chrome CDP ({e}), using Playwright browser")
            # Fallback to persistent context
            chrome_user_data = self.state_dir / "chrome_profile"
            chrome_user_data.mkdir(exist_ok=True)
            
            # Use channel="chrome" to use the installed Chrome instead of bundled Chromium
            try:
                self.context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(chrome_user_data),
                    headless=self.headless,
                    channel="chrome",  # Use installed Chrome
                    slow_mo=100 if not self.headless else 50,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1920, "height": 1080},
                )
                logger.info("Using installed Chrome with persistent profile")
            except Exception as e2:
                logger.warning(f"Chrome not available ({e2}), falling back to Chromium")
                self.context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(chrome_user_data),
                    headless=self.headless,
                    slow_mo=100 if not self.headless else 50,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1920, "height": 1080},
                )
            self.browser = None
        
        # Get first page or create new one
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()
        
        logger.info("Browser started successfully")
    
    def close(self):
        """Close the browser - state is saved automatically in persistent profile"""
        try:
            if self.context:
                self.context.close()
        except Exception as e:
            logger.warning(f"Error closing context: {e}")
        
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error stopping playwright: {e}")
        
        logger.info("Browser closed (session saved in profile)")
    
    def _random_delay(self, min_ms: int = 500, max_ms: int = 2000):
        """Add random delay to simulate human behavior"""
        import random
        delay = random.randint(min_ms, max_ms)
        self.page.wait_for_timeout(delay)
    
    def is_logged_in(self) -> bool:
        """Check if currently logged in to Upwork"""
        try:
            self.page.goto("https://www.upwork.com/nx/find-work/", timeout=30000)
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            
            # Give page a moment to redirect if not logged in
            self.page.wait_for_timeout(2000)
            
            current_url = self.page.url.lower()
            
            # If redirected to login page, not logged in
            if "login" in current_url or "account-security" in current_url:
                logger.info("Redirected to login page - not logged in")
                return False
            
            # If we're on find-work or any authenticated page, we're logged in
            if "find-work" in current_url or "nx/" in current_url:
                logger.info("Already logged in (session restored)")
                return True
            
            # Check for various logged-in indicators
            selectors = [
                '[data-test="nav-dropdown-button"]',
                '[data-test="user-menu"]', 
                '.nav-right .user-menu',
                '[data-cy="nav-user-dropdown"]',
                'button[aria-label*="Account"]',
            ]
            
            for selector in selectors:
                if self.page.locator(selector).count() > 0:
                    logger.info(f"Found logged-in indicator: {selector}")
                    return True
            
            # Last check - if URL doesn't contain login and page loaded, assume logged in
            if "login" not in current_url:
                logger.info("Page loaded without login redirect - assuming logged in")
                return True
                
            return False
        except Exception as e:
            logger.warning(f"Error checking login status: {e}")
            # If there's an error but we're not on login page, might still be logged in
            try:
                if "login" not in self.page.url.lower():
                    return True
            except:
                pass
            return False
    
    def login(self) -> bool:
        """Log in to Upwork"""
        logger.info("Attempting to log in to Upwork...")
        
        if not self.credentials.upwork_username or not self.credentials.upwork_password:
            logger.error("Upwork credentials not configured")
            return False
        
        try:
            self.page.goto(self.UPWORK_LOGIN_URL, timeout=30000)
            self.page.wait_for_load_state("networkidle")
            
            # Enter username
            self.page.fill('#login_username', self.credentials.upwork_username)
            self.page.click('#login_password_continue')
            
            # Wait for password field
            self.page.wait_for_selector('#login_password', timeout=10000)
            
            # Enter password
            self.page.fill('#login_password', self.credentials.upwork_password)
            self.page.click('#login_control_continue')
            
            # Wait for navigation
            self.page.wait_for_load_state("networkidle", timeout=30000)
            
            # Check for security question
            if self.page.locator('[data-test="deviceAuth-answer"]').count() > 0:
                if self.credentials.upwork_security_answer:
                    logger.info("Answering security question...")
                    self.page.fill('[data-test="deviceAuth-answer"]', self.credentials.upwork_security_answer)
                    self.page.click('[data-test="deviceAuth-submit"]')
                    self.page.wait_for_load_state("networkidle", timeout=30000)
            
            is_logged_in = self.is_logged_in()
            if is_logged_in:
                logger.info("Successfully logged in to Upwork")
                return True
            else:
                logger.error("Login failed - could not verify logged in state")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def ensure_logged_in(self) -> bool:
        """Ensure we're logged in"""
        if self.is_logged_in():
            logger.info("Already logged in to Upwork")
            return True
        return self.login()
    
    def search_jobs(self, keyword: str) -> list[JobPosting]:
        """Search for jobs matching the keyword"""
        logger.info(f"Searching for jobs: {keyword}")
        
        if not self.ensure_logged_in():
            logger.error("Cannot search - not logged in")
            return []
        
        search_config = self.config.search
        jobs = []
        
        try:
            # Build search URL
            params = {"q": keyword, "sort": "recency"}
            
            if search_config.experience_levels:
                level_map = {"entry": "1", "intermediate": "2", "expert": "3"}
                levels = [level_map.get(l, l) for l in search_config.experience_levels]
                params["contractor_tier"] = ",".join(levels)
            
            if search_config.job_types:
                type_map = {"hourly": "hourly", "fixed": "fixed-price"}
                types = [type_map.get(t, t) for t in search_config.job_types]
                params["t"] = ",".join(types)
            
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            search_url = f"{self.UPWORK_JOBS_URL}?{query_string}"
            
            self.page.goto(search_url, timeout=60000)
            self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            
            # Wait a moment for dynamic content to load
            self.page.wait_for_timeout(3000)
            
            # Try multiple selectors for job listings (Upwork changes their UI)
            job_list_selectors = [
                '[data-test="job-tile-list"]',
                '[data-test="JobSearchResults"]', 
                '.job-tile-list',
                'section[data-test="SearchResults"]',
                '.up-card-section',
            ]
            
            job_list_found = False
            for selector in job_list_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        logger.info(f"Found job list with selector: {selector}")
                        job_list_found = True
                        break
                except:
                    continue
            
            if not job_list_found:
                logger.warning("Could not find job list container, trying to find job tiles directly")
            
            # Try multiple selectors for job tiles
            tile_selectors = [
                '[data-test="job-tile-list"] article',
                '[data-test="JobTile"]',
                'article[data-test="JobTile"]',
                '.job-tile',
                'section[data-ev-label="search_results_impression"] article',
                '[data-test="JobSearchResults"] > div',
            ]
            
            job_tiles = []
            for selector in tile_selectors:
                try:
                    tiles = self.page.locator(selector).all()
                    if tiles:
                        logger.info(f"Found {len(tiles)} job tiles with selector: {selector}")
                        job_tiles = tiles
                        break
                except:
                    continue
            
            # If still no tiles found, try to find job links directly
            if not job_tiles:
                logger.info("Trying to find job links directly...")
                # Look for any link to a job posting
                job_links = self.page.locator('a[href*="/jobs/~"]').all()
                if job_links:
                    logger.info(f"Found {len(job_links)} job links")
                    # Get unique job containers by finding parent elements
                    seen_urls = set()
                    for link in job_links[:search_config.max_results * 2]:
                        try:
                            href = link.get_attribute("href")
                            if href and href not in seen_urls:
                                seen_urls.add(href)
                                title = link.inner_text().strip()
                                if title and len(title) > 10:  # Filter out icon-only links
                                    job_id_match = re.search(r'/jobs/~([^/?]+)', href)
                                    job_id = job_id_match.group(1) if job_id_match else str(hash(href))
                                    url = f"https://www.upwork.com{href}" if not href.startswith("http") else href
                                    
                                    job = JobPosting(
                                        id=job_id,
                                        title=title[:200],
                                        description="",
                                        url=url,
                                        job_type="unknown",
                                        required_skills=[],
                                        proposals_count=0,
                                        client=ClientInfo()
                                    )
                                    jobs.append(job)
                                    logger.info(f"  Found job: {title[:50]}...")
                        except Exception as e:
                            continue
                    
                    if jobs:
                        logger.info(f"Found {len(jobs)} jobs via direct link search")
                        return jobs[:search_config.max_results]
                
                # Save debug info if no jobs found
                debug_dir = get_project_root() / "debug"
                debug_dir.mkdir(exist_ok=True)
                self.page.screenshot(path=str(debug_dir / "search_page.png"))
                with open(debug_dir / "search_page.html", "w") as f:
                    f.write(self.page.content())
                logger.warning(f"No jobs found. Debug files saved to {debug_dir}")
            
            for i, tile in enumerate(job_tiles[:search_config.max_results]):
                try:
                    job = self._parse_job_tile(tile)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.warning(f"Error parsing job tile {i}: {e}")
                    continue
            
            logger.info(f"Found {len(jobs)} jobs for '{keyword}'")
            return jobs
            
        except Exception as e:
            logger.error(f"Error searching for jobs: {e}")
            return []
    
    def _parse_job_tile(self, tile) -> Optional[JobPosting]:
        """Parse a job tile element"""
        try:
            title_elem = tile.locator('h2 a, [data-test="job-title-link"]').first
            title = title_elem.inner_text()
            url = title_elem.get_attribute("href")
            if url and not url.startswith("http"):
                url = f"https://www.upwork.com{url}"
            
            job_id_match = re.search(r'/jobs/~([^/?]+)', url) if url else None
            job_id = job_id_match.group(1) if job_id_match else str(hash(title))
            
            description_elem = tile.locator('[data-test="job-description-text"], .job-description').first
            description = description_elem.inner_text() if description_elem.count() > 0 else ""
            
            # Get job type and budget
            job_type = "fixed"
            budget_min = None
            budget_max = None
            fixed_price = None
            
            budget_elem = tile.locator('[data-test="job-type-label"], .job-type').first
            if budget_elem.count() > 0:
                budget_text = budget_elem.inner_text()
                if "hourly" in budget_text.lower():
                    job_type = "hourly"
                    rate_match = re.search(r'\$(\d+(?:\.\d{2})?)\s*-\s*\$(\d+(?:\.\d{2})?)', budget_text)
                    if rate_match:
                        budget_min = float(rate_match.group(1))
                        budget_max = float(rate_match.group(2))
                else:
                    job_type = "fixed"
                    price_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', budget_text)
                    if price_match:
                        fixed_price = float(price_match.group(1).replace(",", ""))
            
            # Get skills
            skills = []
            skill_elems = tile.locator('[data-test="token"], .skill-badge').all()
            for skill_elem in skill_elems:
                skill = skill_elem.inner_text()
                if skill:
                    skills.append(skill.strip())
            
            # Get proposals count
            proposals_count = 0
            proposals_elem = tile.locator('[data-test="proposals-tier"], .proposals-count').first
            if proposals_elem.count() > 0:
                proposals_text = proposals_elem.inner_text()
                proposals_match = re.search(r'(\d+)', proposals_text)
                if proposals_match:
                    proposals_count = int(proposals_match.group(1))
            
            # Client info
            client = ClientInfo()
            
            verified_elem = tile.locator('[data-test="payment-verified"]').first
            client.payment_verified = verified_elem.count() > 0
            
            rating_elem = tile.locator('[data-test="client-rating"] .rating').first
            if rating_elem.count() > 0:
                rating_text = rating_elem.inner_text()
                rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                if rating_match:
                    client.rating = float(rating_match.group(1))
            
            spent_elem = tile.locator('[data-test="total-spent"]').first
            if spent_elem.count() > 0:
                spent_text = spent_elem.inner_text()
                spent_match = re.search(r'\$(\d+(?:K|M)?)', spent_text)
                if spent_match:
                    spent_str = spent_match.group(1)
                    if "K" in spent_str:
                        client.total_spent = float(spent_str.replace("K", "")) * 1000
                    elif "M" in spent_str:
                        client.total_spent = float(spent_str.replace("M", "")) * 1000000
                    else:
                        client.total_spent = float(spent_str)
            
            country_elem = tile.locator('[data-test="client-country"]').first
            if country_elem.count() > 0:
                client.country = country_elem.inner_text()
            
            # Posted time
            posted_at = None
            time_elem = tile.locator('[data-test="posted-on"], time').first
            if time_elem.count() > 0:
                time_text = time_elem.inner_text()
                posted_at = self._parse_posted_time(time_text)
            
            return JobPosting(
                id=job_id,
                title=title.strip(),
                description=description.strip(),
                url=url or "",
                posted_at=posted_at,
                job_type=job_type,
                budget_min=budget_min,
                budget_max=budget_max,
                fixed_price=fixed_price,
                required_skills=skills,
                proposals_count=proposals_count,
                client=client
            )
            
        except Exception as e:
            logger.warning(f"Error parsing job tile: {e}")
            return None
    
    def _parse_posted_time(self, time_text: str) -> Optional[datetime]:
        """Parse relative time strings"""
        now = datetime.now()
        time_text = time_text.lower().strip()
        
        patterns = [
            (r'(\d+)\s*minute', lambda m: now - timedelta(minutes=int(m.group(1)))),
            (r'(\d+)\s*hour', lambda m: now - timedelta(hours=int(m.group(1)))),
            (r'(\d+)\s*day', lambda m: now - timedelta(days=int(m.group(1)))),
            (r'(\d+)\s*week', lambda m: now - timedelta(weeks=int(m.group(1)))),
            (r'just\s*now', lambda m: now),
            (r'yesterday', lambda m: now - timedelta(days=1)),
        ]
        
        for pattern, parser in patterns:
            match = re.search(pattern, time_text)
            if match:
                return parser(match)
        
        return None

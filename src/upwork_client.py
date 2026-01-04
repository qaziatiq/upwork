"""Upwork browser automation client using Playwright"""
import asyncio
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .config import get_config, get_credentials, get_project_root
from .models import JobPosting, ClientInfo
from .logger import get_logger

logger = get_logger()


class UpworkClient:
    """Browser-based Upwork client for searching and scraping jobs"""
    
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
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def start(self):
        """Start the browser - connects to user's actual Chrome if available"""
        logger.info(f"Starting browser (headless={self.headless})...")
        self._playwright = await async_playwright().start()

        # Try to connect to user's actual Chrome first (best for avoiding detection)
        # User needs to start Chrome with: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
        try:
            self.browser = await self._playwright.chromium.connect_over_cdp("http://localhost:9222")
            self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
            logger.info("Connected to your Chrome browser via CDP")
        except Exception as e:
            logger.info(f"Could not connect to Chrome CDP ({e}), using Playwright browser")
            # Fallback to persistent context
            chrome_user_data = self.state_dir / "chrome_profile"
            chrome_user_data.mkdir(exist_ok=True)

            # Use channel="chrome" to use the installed Chrome instead of bundled Chromium
            try:
                self.context = await self._playwright.chromium.launch_persistent_context(
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
                self.context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(chrome_user_data),
                    headless=self.headless,
                    slow_mo=100 if not self.headless else 50,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1920, "height": 1080},
                )
            self.browser = None

        # Get first page or create new one
        # When using CDP, always create a new page for automation to avoid using closed tabs
        if self.browser:  # CDP connection
            try:
                # Try to find an open page first
                for page in self.context.pages:
                    if not page.is_closed():
                        self.page = page
                        logger.debug(f"Using existing open page: {page.url}")
                        break

                # If no open pages found, create a new one
                if not self.page or self.page.is_closed():
                    self.page = await self.context.new_page()
                    logger.debug("Created new page for automation")
            except Exception as e:
                logger.warning(f"Error selecting page: {e}, creating new page")
                self.page = await self.context.new_page()
        else:  # Persistent context
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = await self.context.new_page()

        logger.info("Browser started successfully")
    
    async def close(self):
        """Close the browser - state is saved automatically in persistent profile"""
        try:
            if self.context:
                await self.context.close()
        except Exception as e:
            logger.warning(f"Error closing context: {e}")

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error stopping playwright: {e}")

        logger.info("Browser closed")
    
    async def is_logged_in(self) -> bool:
        """Check if currently logged in to Upwork"""
        try:
            # Check current URL without navigating if possible
            current_url = self.page.url

            # If we're clearly on a logged-in page, skip checks
            if current_url and any(path in current_url for path in ['/nx/find-work', '/nx/search/jobs', '/nx/']):
                # Quick check: if we're on these pages and not being redirected, we're logged in
                if "login" not in current_url.lower() and "account-security" not in current_url.lower():
                    logger.debug(f"On authenticated page: {current_url}")
                    return True

            # Only navigate if we're not on Upwork at all
            if not current_url or "upwork.com" not in current_url:
                await self.page.goto("https://www.upwork.com/nx/find-work/", timeout=15000)
                await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(2)
                current_url = self.page.url

            # Check if redirected to login page
            if "login" in current_url.lower() or "account-security" in current_url.lower():
                logger.debug(f"On login page: {current_url}")
                return False

            # If we're on any authenticated Upwork page
            if any(path in current_url for path in ['/nx/find-work', '/nx/search/jobs', '/nx/']):
                logger.debug(f"On authenticated page: {current_url}")
                return True

            logger.debug(f"Unknown page state: {current_url}")
            return False

        except Exception as e:
            logger.warning(f"Error checking login status: {e}")
            return False
    
    async def login(self) -> bool:
        """Log in to Upwork"""
        logger.info("Attempting to log in to Upwork...")
        
        if not self.credentials.upwork_username or not self.credentials.upwork_password:
            logger.error("Upwork credentials not configured. Please set UPWORK_USERNAME and UPWORK_PASSWORD in .env")
            return False
        
        try:
            # Navigate to login page
            await self.page.goto(self.UPWORK_LOGIN_URL, timeout=30000)
            await self.page.wait_for_load_state("networkidle")
            
            # Enter username
            username_input = self.page.locator('#login_username')
            await username_input.fill(self.credentials.upwork_username)
            await self.page.click('#login_password_continue')
            
            # Wait for password field
            await self.page.wait_for_selector('#login_password', timeout=10000)
            
            # Enter password
            password_input = self.page.locator('#login_password')
            await password_input.fill(self.credentials.upwork_password)
            await self.page.click('#login_control_continue')
            
            # Wait for navigation after login
            await self.page.wait_for_load_state("networkidle", timeout=30000)
            
            # Check for security question
            security_question = await self.page.locator('[data-test="deviceAuth-answer"]').count()
            if security_question > 0 and self.credentials.upwork_security_answer:
                logger.info("Answering security question...")
                await self.page.fill('[data-test="deviceAuth-answer"]', self.credentials.upwork_security_answer)
                await self.page.click('[data-test="deviceAuth-submit"]')
                await self.page.wait_for_load_state("networkidle", timeout=30000)
            
            # Verify login success
            is_logged_in = await self.is_logged_in()
            if is_logged_in:
                logger.info("Successfully logged in to Upwork")
                return True
            else:
                logger.error("Login failed - could not verify logged in state")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    async def ensure_logged_in(self) -> bool:
        """Ensure we're logged in, logging in if necessary"""
        if await self.is_logged_in():
            logger.info("Already logged in to Upwork")
            return True
        return await self.login()
    
    async def search_jobs(self, keyword: str, search_profile=None) -> list[JobPosting]:
        """
        Search for jobs matching the keyword
        
        Args:
            keyword: The search keyword
            search_profile: Optional SearchProfileConfig to use instead of the default search config
        """
        logger.info(f"Searching for jobs: {keyword}")
        
        if not await self.ensure_logged_in():
            logger.error("Cannot search - not logged in")
            return []
        
        # Use the provided search profile if available, otherwise use the default search config
        search_config = search_profile if search_profile else self.config.search
        jobs = []
        
        try:
            # Build search URL with parameters
            params = {
                "q": keyword,
                "sort": "recency",
            }
            
            # Add experience level filters
            if search_config.experience_levels:
                level_map = {"entry": "1", "intermediate": "2", "expert": "3"}
                levels = [level_map.get(l, l) for l in search_config.experience_levels]
                params["contractor_tier"] = ",".join(levels)
            
            # Add job type filter
            if search_config.job_types:
                type_map = {"hourly": "hourly", "fixed": "fixed-price"}
                types = [type_map.get(t, t) for t in search_config.job_types]
                params["t"] = ",".join(types)
            
            # Add budget filters
            if search_config.budget.min_hourly > 0:
                params["hourly_rate"] = f"{int(search_config.budget.min_hourly)}-{int(search_config.budget.max_hourly)}"
            
            # Add posted within filter
            if search_config.posted_within_hours:
                params["duration_v3"] = f"hours_{search_config.posted_within_hours}"
            
            # Navigate to search results
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            search_url = f"{self.UPWORK_JOBS_URL}?{query_string}"

            await self.page.goto(search_url, timeout=30000)
            await self.page.wait_for_load_state("domcontentloaded")

            # Give the page time to render (SPA needs time)
            await asyncio.sleep(3)

            # Debug: Check what page we're actually on
            current_url = self.page.url
            logger.debug(f"After navigation, current URL: {current_url}")

            # Check if we got redirected away (e.g., to login or home page)
            if "search/jobs" not in current_url:
                logger.warning(f"Redirected away from search page to: {current_url}")
                # Take a screenshot for debugging
                try:
                    screenshot_path = self.state_dir / f"debug_redirect_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    await self.page.screenshot(path=str(screenshot_path))
                    logger.info(f"Screenshot saved to: {screenshot_path}")
                except Exception:
                    pass
                return []

            # Wait for job listings to load - try multiple selectors
            job_container_found = False
            job_tiles = []

            # Try different selectors for job containers (Upwork UI changes frequently)
            selectors_to_try = [
                'section[data-test*="job-tile"]',  # Full job tile sections
                'div.job-tile',  # Job tiles by class
                'section.air3-card-section',  # Card sections
                '[data-ev-job-uid]',  # Elements with job UID
                'article',  # Generic articles (last resort)
            ]

            for selector in selectors_to_try:
                try:
                    await self.page.wait_for_selector(selector, timeout=5000)
                    job_tiles = await self.page.locator(selector).all()
                    if len(job_tiles) > 0:
                        logger.debug(f"Found {len(job_tiles)} job tiles using selector: {selector}")
                        job_container_found = True
                        break
                except Exception:
                    continue

            if not job_container_found or len(job_tiles) == 0:
                logger.warning("Could not find any job tiles")
                # Take a screenshot for debugging
                try:
                    screenshot_path = self.state_dir / f"debug_no_tiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    await self.page.screenshot(path=str(screenshot_path))
                    logger.info(f"Screenshot saved to: {screenshot_path}")
                except Exception:
                    pass

                # Check page content for clues
                page_text = await self.page.content()
                if "cloudflare" in page_text.lower():
                    logger.error("Detected Cloudflare challenge - manual login required")
                elif "login" in page_text.lower():
                    logger.error("Appears to be on login page")
                else:
                    logger.error("Unknown page state - check screenshot")
                return []
            
            for i, tile in enumerate(job_tiles[:search_config.max_results]):
                try:
                    # Debug: Save first job tile HTML
                    if i == 0:
                        try:
                            tile_html = await tile.inner_html()
                            debug_path = self.state_dir / "debug_job_tile.html"
                            with open(debug_path, 'w', encoding='utf-8') as f:
                                f.write(tile_html)
                            logger.info(f"Saved first job tile HTML to: {debug_path}")
                        except Exception as e:
                            logger.warning(f"Could not save debug HTML: {e}")

                    job = await self._parse_job_tile(tile)
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
    
    async def _parse_job_tile(self, tile) -> Optional[JobPosting]:
        """Parse a job tile element into a JobPosting model"""
        try:
            # Get job title and URL - try multiple selectors
            title = None
            url = None

            title_selectors = [
                'h2 a',
                'h3 a',
                'h4 a',
                '[data-test="job-title-link"]',
                'a[href*="/jobs/"]',
            ]

            for selector in title_selectors:
                try:
                    title_elem = tile.locator(selector).first
                    if await title_elem.count() > 0:
                        title = await title_elem.inner_text()
                        url = await title_elem.get_attribute("href")
                        if title and url:
                            break
                except Exception:
                    continue

            if not title:
                # Debug: Log tile HTML to understand structure
                try:
                    tile_html = await tile.inner_html()
                    logger.debug(f"Failed tile HTML (first 500 chars): {tile_html[:500]}")
                except Exception:
                    pass
                logger.warning("Could not find job title, skipping tile")
                return None

            if url and not url.startswith("http"):
                url = f"https://www.upwork.com{url}"

            # Extract job ID from URL
            job_id_match = re.search(r'/jobs/~([^/?]+)', url) if url else None
            job_id = job_id_match.group(1) if job_id_match else str(hash(title))
            
            # Get description using the correct data-test attribute
            description = ""
            try:
                desc_elem = tile.locator('[data-test="UpCLineClamp JobDescription"] p, [data-test="JobDescription"] p').first
                if await desc_elem.count() > 0:
                    description = await desc_elem.inner_text()
            except Exception:
                pass

            # Fallback: try to get any paragraph with substantial text
            if not description or len(description) < 20:
                try:
                    desc_elem = tile.locator('p.mb-0, p.text-body-sm').first
                    if await desc_elem.count() > 0:
                        description = await desc_elem.inner_text()
                except Exception:
                    pass

            # Get job type and budget using data-test attribute
            job_type = "fixed"
            budget_min = None
            budget_max = None
            fixed_price = None

            try:
                job_type_elem = tile.locator('[data-test="job-type-label"]').first
                if await job_type_elem.count() > 0:
                    budget_text = await job_type_elem.inner_text()

                    if "hourly" in budget_text.lower():
                        job_type = "hourly"
                        # Extract hourly rate range: "Hourly: $30.00 - $80.00"
                        rate_match = re.search(r'\$(\d+(?:\.\d{2})?)\s*-\s*\$(\d+(?:\.\d{2})?)', budget_text)
                        if rate_match:
                            budget_min = float(rate_match.group(1))
                            budget_max = float(rate_match.group(2))
                    elif "fixed" in budget_text.lower():
                        job_type = "fixed"
                        # Extract fixed price
                        price_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', budget_text)
                        if price_match:
                            fixed_price = float(price_match.group(1).replace(",", ""))
            except Exception:
                pass

            # Get required skills
            skills = []
            try:
                skill_elems = await tile.locator('[data-test="Skill"] span, [data-test="token"]').all()
                for skill_elem in skill_elems:
                    skill = await skill_elem.inner_text()
                    if skill and skill not in skills:
                        skills.append(skill.strip())
            except Exception:
                pass

            # Get proposals count
            proposals_count = 0
            try:
                proposals_elem = tile.locator('[data-test="proposals"]').first
                if await proposals_elem.count() > 0:
                    proposals_text = await proposals_elem.inner_text()
                    proposals_match = re.search(r'(\d+)', proposals_text)
                    if proposals_match:
                        proposals_count = int(proposals_match.group(1))
            except Exception:
                pass
            
            # Get client info using data-test attributes
            client = ClientInfo()

            # Payment verified
            try:
                verified_elem = tile.locator('[data-test="payment-verified"]').first
                client.payment_verified = await verified_elem.count() > 0
            except Exception:
                pass

            # Client rating
            try:
                rating_elem = tile.locator('[data-test="rating"]').first
                if await rating_elem.count() > 0:
                    rating_text = await rating_elem.inner_text()
                    rating_match = re.search(r'(\d\.\d{1,2})', rating_text)
                    if rating_match:
                        client.rating = float(rating_match.group(1))
            except Exception:
                pass

            # Client spent
            try:
                spent_elem = tile.locator('[data-test="total-spent"]').first
                if await spent_elem.count() > 0:
                    spent_text = await spent_elem.inner_text()
                    # Parse "$7K+ spent" format
                    spent_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(K|M)\+?', spent_text, re.IGNORECASE)
                    if spent_match:
                        amount = float(spent_match.group(1))
                        unit = spent_match.group(2).upper()
                        if unit == "K":
                            client.total_spent = amount * 1000
                        elif unit == "M":
                            client.total_spent = amount * 1000000
            except Exception:
                pass

            # Client country
            try:
                country_elem = tile.locator('[data-test="location"]').first
                if await country_elem.count() > 0:
                    country_text = await country_elem.inner_text()
                    # Extract just the country name
                    country_match = re.search(r'Location\s+(.+)$', country_text, re.IGNORECASE)
                    if country_match:
                        client.country = country_match.group(1).strip()
                    else:
                        client.country = country_text.strip()
            except Exception:
                pass

            # Posted time
            posted_at = None
            try:
                time_elem = tile.locator('[data-test="job-pubilshed-date"]').first
                if await time_elem.count() > 0:
                    time_text = await time_elem.inner_text()
                    # Parse "Posted 5 hours ago" format
                    time_match = re.search(r'Posted\s+(.+)', time_text, re.IGNORECASE)
                    if time_match:
                        posted_at = self._parse_posted_time(time_match.group(1))
            except Exception:
                pass
            
            job_posting = JobPosting(
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

            # Debug: Log first job's details
            logger.debug(f"Parsed job: {title[:50]}... | Type: {job_type} | Budget: {budget_min}-{budget_max} / {fixed_price} | Skills: {len(skills)} | Proposals: {proposals_count}")

            return job_posting
            
        except Exception as e:
            logger.warning(f"Error parsing job tile: {e}")
            return None
    
    def _parse_posted_time(self, time_text: str) -> Optional[datetime]:
        """Parse relative time strings like '2 hours ago' into datetime"""
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
    
    async def get_job_details(self, job_url: str) -> Optional[JobPosting]:
        """Get full details for a specific job"""
        logger.info(f"Fetching job details: {job_url}")
        
        try:
            await self.page.goto(job_url, timeout=30000)
            await self.page.wait_for_load_state("networkidle")
            
            # Parse the full job page
            # This is a placeholder - you'd parse the full job page here
            # The tile parsing gives us most info we need
            
            return None  # Return None for now, tile info is sufficient
            
        except Exception as e:
            logger.error(f"Error fetching job details: {e}")
            return None


async def run_search_example():
    """Example usage of the UpworkClient"""
    async with UpworkClient() as client:
        jobs = await client.search_jobs("python automation")
        for job in jobs:
            print(f"\n{job.title}")
            print(f"  Type: {job.job_type}")
            print(f"  Proposals: {job.proposals_count}")
            print(f"  Skills: {', '.join(job.required_skills)}")


if __name__ == "__main__":
    asyncio.run(run_search_example())

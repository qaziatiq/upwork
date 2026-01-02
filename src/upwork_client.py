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
        """Start the browser"""
        logger.info(f"Starting browser (headless={self.headless})...")
        self._playwright = await async_playwright().start()
        
        # Launch args - different for headless vs visible
        launch_args = ["--disable-blink-features=AutomationControlled"]
        
        if self.headless:
            launch_args.extend([
                "--disable-dev-shm-usage",
                "--no-sandbox", 
                "--disable-gpu",
            ])
        
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=100 if not self.headless else 0,
            args=launch_args
        )
        
        # Try to load existing session state
        state_file = self.state_dir / "state.json"
        
        # Simple context options - avoid complex features that may cause crashes
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }
        
        # Only load state if file exists and is valid
        if state_file.exists():
            try:
                import json
                with open(state_file, 'r') as f:
                    json.load(f)  # Validate JSON
                logger.info("Loading existing browser state...")
                context_options["storage_state"] = str(state_file)
            except Exception as e:
                logger.warning(f"Invalid browser state file, starting fresh: {e}")
                state_file.unlink()  # Delete corrupted file
        
        self.context = await self.browser.new_context(**context_options)
        self.page = await self.context.new_page()
        
        # Simple stealth script
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
    
    async def close(self):
        """Close the browser and save state"""
        if self.context:
            # Save session state for reuse
            state_file = self.state_dir / "state.json"
            try:
                await self.context.storage_state(path=str(state_file))
                logger.info("Browser state saved")
            except Exception as e:
                logger.warning(f"Could not save browser state: {e}")
        
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        
        logger.info("Browser closed")
    
    async def is_logged_in(self) -> bool:
        """Check if currently logged in to Upwork"""
        try:
            await self.page.goto("https://www.upwork.com/nx/find-work/", timeout=15000)
            await self.page.wait_for_load_state("networkidle", timeout=10000)
            
            # Check if redirected to login page
            if "login" in self.page.url.lower():
                return False
            
            # Check for logged-in indicators
            logged_in = await self.page.locator('[data-test="nav-dropdown-button"]').count() > 0
            return logged_in
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
            await self.page.wait_for_load_state("networkidle")
            
            # Wait for job listings to load
            await self.page.wait_for_selector('[data-test="job-tile-list"]', timeout=15000)
            
            # Get all job tiles
            job_tiles = await self.page.locator('[data-test="job-tile-list"] article').all()
            
            for i, tile in enumerate(job_tiles[:search_config.max_results]):
                try:
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
            # Get job title and URL
            title_elem = tile.locator('h2 a, [data-test="job-title-link"]').first
            title = await title_elem.inner_text()
            url = await title_elem.get_attribute("href")
            if url and not url.startswith("http"):
                url = f"https://www.upwork.com{url}"
            
            # Extract job ID from URL
            job_id_match = re.search(r'/jobs/~([^/?]+)', url) if url else None
            job_id = job_id_match.group(1) if job_id_match else str(hash(title))
            
            # Get description
            description_elem = tile.locator('[data-test="job-description-text"], .job-description').first
            description = await description_elem.inner_text() if await description_elem.count() > 0 else ""
            
            # Get job type and budget
            job_type = "fixed"
            budget_min = None
            budget_max = None
            fixed_price = None
            
            budget_elem = tile.locator('[data-test="job-type-label"], .job-type').first
            if await budget_elem.count() > 0:
                budget_text = await budget_elem.inner_text()
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
            
            # Get required skills
            skills = []
            skill_elems = await tile.locator('[data-test="token"], .skill-badge').all()
            for skill_elem in skill_elems:
                skill = await skill_elem.inner_text()
                if skill:
                    skills.append(skill.strip())
            
            # Get proposals count
            proposals_count = 0
            proposals_elem = tile.locator('[data-test="proposals-tier"], .proposals-count').first
            if await proposals_elem.count() > 0:
                proposals_text = await proposals_elem.inner_text()
                proposals_match = re.search(r'(\d+)', proposals_text)
                if proposals_match:
                    proposals_count = int(proposals_match.group(1))
            
            # Get client info
            client = ClientInfo()
            
            # Payment verified
            verified_elem = tile.locator('[data-test="payment-verified"]').first
            client.payment_verified = await verified_elem.count() > 0
            
            # Client rating
            rating_elem = tile.locator('[data-test="client-rating"] .rating').first
            if await rating_elem.count() > 0:
                rating_text = await rating_elem.inner_text()
                rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                if rating_match:
                    client.rating = float(rating_match.group(1))
            
            # Client spent
            spent_elem = tile.locator('[data-test="total-spent"]').first
            if await spent_elem.count() > 0:
                spent_text = await spent_elem.inner_text()
                spent_match = re.search(r'\$(\d+(?:K|M)?)', spent_text)
                if spent_match:
                    spent_str = spent_match.group(1)
                    if "K" in spent_str:
                        client.total_spent = float(spent_str.replace("K", "")) * 1000
                    elif "M" in spent_str:
                        client.total_spent = float(spent_str.replace("M", "")) * 1000000
                    else:
                        client.total_spent = float(spent_str)
            
            # Client country
            country_elem = tile.locator('[data-test="client-country"]').first
            if await country_elem.count() > 0:
                client.country = await country_elem.inner_text()
            
            # Posted time
            posted_at = None
            time_elem = tile.locator('[data-test="posted-on"], time').first
            if await time_elem.count() > 0:
                time_text = await time_elem.inner_text()
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

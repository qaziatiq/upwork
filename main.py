#!/usr/bin/env python3
"""
Upwork Automation Service - Main Entry Point

Usage:
    python main.py              # Run as a scheduled service
    python main.py --once       # Run a single search cycle
    python main.py --test       # Test configuration and login
    python main.py --login      # Login with visible browser (for 2FA)
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config, get_credentials, get_project_root
from src.logger import setup_logging, get_logger
from src.service import UpworkAutomationService, run_service, run_once
from src.upwork_client_sync import UpworkClientSync


def test_connection():
    """Test the Upwork connection and configuration"""
    setup_logging()
    logger = get_logger()
    
    logger.info("Testing Upwork Automation Configuration")
    logger.info("=" * 50)
    
    # Test configuration
    try:
        config = get_config()
        logger.info("✓ Configuration loaded successfully")
        logger.info(f"  Search keywords: {config.search.keywords}")
        logger.info(f"  Interval: {config.scheduler.interval_minutes} minutes")
        logger.info(f"  Ranking threshold: {config.ranking.threshold}")
    except Exception as e:
        logger.error(f"✗ Configuration error: {e}")
        return False
    
    # Test credentials
    try:
        creds = get_credentials()
        if not creds.upwork_username or not creds.upwork_password:
            logger.warning("⚠ Upwork credentials not set in .env file")
            logger.info("  Copy .env.example to .env and add your credentials")
            return False
        logger.info("✓ Credentials configured")
    except Exception as e:
        logger.error(f"✗ Credentials error: {e}")
        return False
    
    # Test browser and login
    logger.info("\nTesting browser and Upwork connection...")
    try:
        with UpworkClientSync(headless=False) as client:
            logger.info("✓ Browser started successfully")
            
            # Try to login
            if client.ensure_logged_in():
                logger.info("✓ Successfully logged in to Upwork")
                
                # Try a test search
                logger.info("\nRunning test search...")
                test_keyword = config.search.keywords[0] if config.search.keywords else "python"
                jobs = client.search_jobs(test_keyword)
                
                if jobs:
                    logger.info(f"✓ Found {len(jobs)} jobs for '{test_keyword}'")
                    logger.info(f"  Example: {jobs[0].title[:60]}...")
                else:
                    logger.warning(f"⚠ No jobs found for '{test_keyword}'")
            else:
                logger.error("✗ Could not log in to Upwork")
                logger.info("  Check your credentials in .env")
                return False
                
    except Exception as e:
        logger.error(f"✗ Browser/connection error: {e}")
        return False
    
    logger.info("\n" + "=" * 50)
    logger.info("All tests passed! You can now run the service.")
    return True


def interactive_login():
    """Interactive login - user logs in manually to avoid bot detection"""
    setup_logging()
    logger = get_logger()
    
    logger.info("=" * 60)
    logger.info("MANUAL LOGIN MODE")
    logger.info("=" * 60)
    logger.info("")
    logger.info("To avoid Cloudflare detection, please:")
    logger.info("1. Close ALL Chrome windows")
    logger.info("2. Start Chrome with remote debugging:")
    logger.info("")
    logger.info('   /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222')
    logger.info("")
    logger.info("3. In that Chrome window, go to upwork.com and LOG IN MANUALLY")
    logger.info("4. Complete any 2FA/captcha as needed")
    logger.info("5. Once logged in, come back here and press ENTER")
    logger.info("")
    logger.info("=" * 60)
    
    input("Press ENTER after you've logged in to Upwork in Chrome: ")
    
    try:
        with UpworkClientSync(headless=False) as client:
            logger.info("Connecting to your Chrome browser...")
            
            # Check if we're logged in
            if client.is_logged_in():
                logger.info("✓ Successfully connected! You are logged in.")
                logger.info("Session will be reused for future runs.")
            else:
                logger.warning("Could not verify login. Make sure you're logged into Upwork.")
            
    except Exception as e:
        logger.error(f"Error connecting to Chrome: {e}")
        logger.info("")
        logger.info("Make sure Chrome is running with --remote-debugging-port=9222")
        raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Upwork Automation Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py              Run as a scheduled service
  python main.py --once       Run a single search cycle  
  python main.py --test       Test configuration and login
  python main.py --login      Login with visible browser (for 2FA)
        """
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single search cycle instead of scheduling"
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test configuration and Upwork connection"
    )
    
    parser.add_argument(
        "--no-immediate",
        action="store_true",
        help="Don't run immediately when starting the scheduler"
    )
    
    parser.add_argument(
        "--login",
        action="store_true",
        help="Login with visible browser for 2FA setup"
    )
    
    args = parser.parse_args()
    
    if args.login:
        # Run interactive login with visible browser
        interactive_login()
    
    elif args.test:
        # Run connection test
        success = test_connection()
        sys.exit(0 if success else 1)
    
    elif args.once:
        # Run single cycle
        asyncio.run(run_once())
    
    else:
        # Run as scheduled service
        service = UpworkAutomationService()
        asyncio.run(service.start(run_immediately=not args.no_immediate))


if __name__ == "__main__":
    main()

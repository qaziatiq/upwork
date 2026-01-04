# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an Upwork automation service that searches for jobs, ranks them using AI and rule-based algorithms, and generates personalized proposal drafts. It's designed to run as a scheduled service with Cloudflare bypass capabilities using Chrome DevTools Protocol (CDP).

## Architecture

### Core Components

**Browser Automation Layer** (`src/upwork_client.py`, `src/upwork_client_sync.py`)
- Dual implementation: async (Playwright) and sync versions
- CDP connection to user's Chrome browser (`localhost:9222`) to avoid Cloudflare detection
- Fallback to Playwright's persistent browser context if CDP unavailable
- Session persistence via `browser_state/` directory to avoid repeated logins

**Job Ranking System** (`src/ranking.py`, `src/ai_engine.py`)
- Hybrid ranking: AI-powered (70%) + rule-based (30%) blended scores
- Rule-based factors: skills match, budget, client quality, job clarity, competition, recency
- AI ranking modes: `parallel` (fastest), `batch` (cheapest), `sequential` (most reliable)
- Configurable weights in `config/config.yaml`

**Service Orchestration** (`src/service.py`)
- APScheduler-based periodic execution
- Support for active hours and timezone restrictions
- Handles both single search profiles and multiple search profiles
- Deduplication of jobs across searches by job ID
- Max proposals per run limit to avoid spam

**Configuration System** (`src/config.py`)
- Pydantic models for type safety
- Environment variables via `.env` (credentials only)
- YAML configuration in `config/config.yaml` (all other settings)
- Search profiles: named configurations with different keywords, filters, and criteria

### Key Architectural Patterns

**Search Profiles**
- The service supports both legacy single search config and modern multi-profile approach
- Each profile has its own keywords, filters, budget ranges, and enabled/disabled flag
- Profiles are processed sequentially, each keyword within a profile is searched
- Jobs are deduplicated by ID across all profile searches

**AI Integration**
- OpenAI-compatible API (works with OpenAI, Ollama, or other providers)
- Ranking uses structured JSON responses with score, reasoning, strengths, concerns
- Proposal generation uses customizable system/user prompts with template variables
- Graceful fallback to rule-based ranking if AI unavailable or fails

**Cloudflare Bypass Strategy**
- Primary: Connect to user's Chrome via CDP (requires manual Chrome launch with `--remote-debugging-port=9222`)
- Secondary: Use Playwright's persistent context with installed Chrome (`channel="chrome"`)
- Tertiary: Fall back to Chromium with persistent profile
- Session state saved automatically in persistent contexts

## Development Commands

### Environment Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Running the Service
```bash
# Test configuration and connection
python main.py --test

# Manual login with Chrome CDP (for Cloudflare bypass)
# 1. Start Chrome with debugging:
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
# 2. Login manually to Upwork in that Chrome window
# 3. Verify connection:
python main.py --login

# Single search cycle (one-time run)
python main.py --once

# Scheduled service (runs every N minutes)
python main.py

# Scheduled service without immediate run
python main.py --no-immediate
```

### Configuration Files

**.env** - Credentials only (never commit)
- `UPWORK_USERNAME`
- `UPWORK_PASSWORD`
- `UPWORK_SECURITY_ANSWER`
- `OPENAI_API_KEY`

**config/config.yaml** - All other configuration
- `scheduler`: interval, active hours, timezone
- `search`: legacy single search config (keywords, filters, budget)
- `search_profiles`: modern multi-profile approach
- `ranking`: threshold, weights, my_skills
- `proposal`: template, output directory, max per run
- `ai`: base_url, model, ranking_mode, prompts

### Output Directories

- `proposals/YYYY-MM-DD/` - Generated proposals organized by date
- `logs/upwork_automation.log` - Rotating log file (10MB max, 5 backups)
- `browser_state/` - Persistent browser session data (gitignored)

## Important Implementation Notes

### When Working with Browser Automation

- The sync client (`upwork_client_sync.py`) is used for CLI commands (`--test`, `--login`)
- The async client (`upwork_client.py`) is used for the main service
- Always check for CDP connection first, then fall back to persistent context
- Use `slow_mo` parameter to make automation more human-like and avoid detection
- Check `is_logged_in()` before attempting job searches

### When Working with Configuration

- Never add credentials to YAML files - use environment variables only
- Ensure ranking weights sum to 1.0
- Search profiles override the legacy `search` config when present
- AI ranking modes: `parallel` for speed, `batch` for cost savings, `sequential` for reliability

### When Working with Job Ranking

- Blended score = (AI score × 0.7) + (rule-based score × 0.3)
- If AI ranking fails for a job, fall back to rule-based score
- Threshold is applied to the blended score, not individual scores
- Score breakdown is stored for proposal generation and debugging

### When Working with Proposal Generation

- Max proposals per run enforced in `service.py:211-214`
- AI proposals wrapped with metadata (job details, scores, client info)
- Template variables available: `{job_title}`, `{job_type}`, `{budget_info}`, `{required_skills}`, `{job_description}`, `{my_skills}`, `{my_experience}`, `{ranking_score}`, etc.
- Proposals saved to date-stamped directories with sanitized filenames

### When Working with Scheduler

- Uses `AsyncIOScheduler` from APScheduler
- Active hours check happens in `_scheduled_run()` wrapper
- Service keeps running with 1-second sleep loop, waiting for KeyboardInterrupt
- Scheduler timezone must be a valid pytz timezone string

## Common Troubleshooting Scenarios

**"Could not connect to Chrome CDP"**
- Ensure Chrome started with `--remote-debugging-port=9222`
- Close ALL other Chrome windows first
- Check that no other process is using port 9222

**"Cloudflare blocking / bot detection"**
- Use the CDP method with manual login in real Chrome
- Ensure `slow_mo` is set appropriately (100ms+ for non-headless)
- Check that `--disable-blink-features=AutomationControlled` arg is present

**AI ranking fails**
- Check `OPENAI_API_KEY` is set and valid
- Verify `ai.base_url` points to correct endpoint
- Check `ai.enabled` is true in config
- Service will gracefully fall back to rule-based ranking

**No jobs found**
- Verify logged in by checking browser window
- Expand search filters (lower `min_hourly`, increase `posted_within_hours`)
- Try broader keywords
- Check logs for scraping errors

**No proposals generated**
- Lower `ranking.threshold` value
- Check that at least one job scored above threshold
- Verify `proposal.max_proposals_per_run` is not 0
- Check logs for proposal generation errors
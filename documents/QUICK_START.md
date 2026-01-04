# Quick Start Guide - Fixed Chrome CDP Connection

## What Was Fixed

I've updated the async client (`src/upwork_client.py`) to support Chrome CDP connection, just like the sync client. This allows the service to connect to your manually-opened Chrome browser and bypass Cloudflare detection.

## How to Run Now

### Step 1: Start Chrome with Remote Debugging

**IMPORTANT:** Close ALL Chrome windows first, then run:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

Leave this terminal window open and Chrome running.

### Step 2: Login to Upwork Manually

In the Chrome window that just opened:
1. Go to https://www.upwork.com
2. Login with your credentials
3. Complete any 2FA/captcha verification
4. Make sure you're fully logged in (you should see your profile)

### Step 3: Run the Service

In a **new terminal** (keep Chrome running in the other terminal):

```bash
# Activate virtual environment
source venv/bin/activate

# Run single search cycle
python main.py --once

# OR run as scheduled service
python main.py
```

## What Will Happen

The service will now:
1. Try to connect to Chrome CDP on port 9222 (your open Chrome)
2. If successful: Use your logged-in session (no Cloudflare issues!)
3. If failed: Fall back to persistent Chrome profile
4. Search for jobs based on your config
5. Rank jobs using rule-based scoring (AI disabled since no API key)
6. Generate proposals from templates for qualifying jobs

## Expected Log Output

**Success:**
```
2026-01-04 12:45:00 | INFO | Starting browser (headless=True)...
2026-01-04 12:45:01 | INFO | Connected to your Chrome browser via CDP
2026-01-04 12:45:01 | INFO | Browser started successfully
2026-01-04 12:45:01 | INFO | Using 2 search profiles
2026-01-04 12:45:01 | INFO | Processing search profile: Python Development
2026-01-04 12:45:01 | INFO | Searching for: python developer
2026-01-04 12:45:05 | INFO | Found 15 jobs for 'python developer'...
```

**If CDP connection fails:**
```
2026-01-04 12:45:00 | INFO | Starting browser (headless=True)...
2026-01-04 12:45:01 | INFO | Could not connect to Chrome CDP (...), using Playwright browser
2026-01-04 12:45:02 | INFO | Using installed Chrome with persistent profile
```

## Troubleshooting

### "Could not connect to Chrome CDP"

**Cause:** Chrome not started with debugging port or already closed

**Fix:**
1. Close ALL Chrome windows (including background processes)
2. Run the Chrome command again: `/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug`
3. Make sure port 9222 is not used by another process: `lsof -i :9222`

### Login still failing

**Cause:** Using fallback mode which may trigger Cloudflare

**Options:**
1. Make sure Chrome CDP is connected (see above)
2. If using fallback, try running with `headless=False` (requires code modification)
3. Manually login again in the Chrome window

### AI Warning Message

```
WARNING | OpenAI API key not configured. AI features will be disabled.
```

This is **normal** if you don't have an OpenAI API key. The system will use rule-based ranking instead, which works fine.

## Testing Your Setup

```bash
# Verify configuration and connection (uses sync client with visible browser)
python main.py --test

# Run single cycle (uses async client with CDP)
python main.py --once
```

## Configuration Files

You're currently using:
- `config/config.yaml` - Default configuration (Python Development, Web Scraping profiles)
- `config/config_url_based.yaml` - URL-based configuration (Developer jobs, low competition focus)

To switch configs, either:
1. Copy `config_url_based.yaml` to `config.yaml`
2. Or modify the code to load a different config file

## Next Steps

1. **Monitor first run:** Check `logs/upwork_automation.log` for details
2. **Review proposals:** Check `proposals/YYYY-MM-DD/` directory
3. **Adjust ranking:** If too few/many proposals, modify `ranking.threshold` in config
4. **Fine-tune search:** Adjust search profiles based on results

## Running as a Service

Once you confirm it's working with `--once`, you can run continuously:

```bash
# Terminal 1: Keep Chrome running
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug

# Terminal 2: Run service
source venv/bin/activate
python main.py
```

The service will:
- Run every 60 minutes (configurable in `config.yaml`)
- Only run during active hours (9 AM - 6 PM Sydney time)
- Generate up to 5 proposals per run (configurable)

Press `Ctrl+C` to stop.

## Optional: Enable AI Features

If you later get an OpenAI API key:

1. Edit `.env`:
   ```bash
   OPENAI_API_KEY=sk-your-actual-key-here
   ```

2. Configure AI in `config.yaml`:
   ```yaml
   ai:
     enabled: true
     base_url: "https://api.openai.com/v1"
     model: "gpt-4o-mini"
   ```

3. Restart the service

AI will provide:
- Smarter job ranking (blended with rule-based)
- Auto-generated personalized proposals
- Analysis of job quality and fit

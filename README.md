# Upwork Automation Service

An automated service that periodically searches Upwork for jobs, ranks them based on configurable criteria, and generates proposal drafts for qualifying opportunities.

## Features

- **Scheduled Execution**: Runs at configurable intervals (default: every 60 minutes)
- **Multi-Keyword Search**: Search for multiple keywords/skill combinations
- **Smart Ranking**: Score jobs based on:
  - Skills match
  - Budget attractiveness
  - Client quality (payment verified, rating, total spent)
  - Job clarity
  - Competition level
  - Recency
- **Proposal Generation**: Auto-generates proposal drafts from customizable templates
- **Persistent Sessions**: Saves browser state to avoid repeated logins
- **Configurable Filters**: Filter by experience level, job type, budget range, etc.

## Quick Start

### 1. Install Dependencies

```bash
cd upwork-automation
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Credentials

```bash
cp .env.example .env
```

Edit `.env` with your actual Upwork credentials:
```
UPWORK_USERNAME=your_actual_email@domain.com
UPWORK_PASSWORD=your_actual_password
```

### 3. Customize Configuration

Edit `config/config.yaml` to set:
- Search keywords and filters
- Ranking weights and threshold
- Your skills for matching
- Scheduler interval

### 4. First-Time Login Setup (Important!)

Upwork uses Cloudflare bot protection. To bypass it, you must log in using your real Chrome browser:

**Step 1: Close all Chrome windows**

**Step 2: Start Chrome with remote debugging**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

**Step 3: Log in to Upwork manually**
- In the Chrome window that opens, go to https://www.upwork.com
- Log in with your credentials
- Complete any 2FA/captcha verification

**Step 4: Verify the connection**
```bash
python main.py --login
```

This connects to your authenticated Chrome session.

### 5. Test the Setup

With Chrome still running (from step 4):
```bash
python main.py --test
```

This will:
- Verify configuration is loaded
- Connect to your Chrome browser
- Check you're logged in
- Run a test job search

### 6. Run the Service

**Option A: Keep Chrome running in background**
```bash
# Start Chrome with debugging (keep this terminal open)
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug

# In another terminal, run the service
python main.py          # Scheduled service
python main.py --once   # Single search cycle
```

**Option B: Use Playwright's browser (may trigger Cloudflare)**
```bash
python main.py --once
```

## Command Reference

| Command | Description |
|---------|-------------|
| `python main.py --login` | Connect to Chrome and verify login |
| `python main.py --test` | Test configuration and connection |
| `python main.py --once` | Run single search cycle |
| `python main.py` | Run as scheduled service |

## Configuration

### Search Parameters (`config/config.yaml`)

```yaml
search:
  keywords:
    - "python developer"
    - "web scraping"
  experience_levels:
    - "intermediate"
    - "expert"
  budget:
    min_hourly: 25
    max_hourly: 150
  posted_within_hours: 24
```

### Multiple Search Profiles

You can define multiple search profiles with different parameters to target specific niches:

```yaml
search_profiles:
  - name: "Python Development"
    enabled: true
    keywords:
      - "python developer"
      - "python programmer"
    experience_levels:
      - "intermediate"
      - "expert"
    budget:
      min_hourly: 30
      max_hourly: 150
    # other parameters...
    
  - name: "Web Scraping"
    enabled: true
    keywords:
      - "web scraping"
      - "data extraction"
    experience_levels:
      - "expert"
    job_types:
      - "fixed"
      - "hourly"
    budget:
      min_hourly: 25
      max_hourly: 100
    # other parameters...
```

Each profile can have its own set of parameters and filters. Profiles can be enabled/disabled with the `enabled` flag without removing them from the configuration.

### Ranking Weights

Adjust weights to prioritize what matters most to you (must sum to 1.0):

```yaml
ranking:
  threshold: 60  # Minimum score to generate proposal
  weights:
    skills_match: 0.25
    budget_score: 0.20
    client_quality: 0.20
    job_clarity: 0.15
    competition: 0.10
    recency: 0.10
  my_skills:
    - "python"
    - "automation"
    - "web scraping"
```

### Scheduler Settings

```yaml
scheduler:
  interval_minutes: 60
  active_hours:
    start: "09:00"
    end: "18:00"
  timezone: "Australia/Sydney"
```

## Running as a Background Service (macOS)

To run automatically on system startup:

```bash
# Copy the launch agent
cp com.upwork.automation.plist ~/Library/LaunchAgents/

# Load the service
launchctl load ~/Library/LaunchAgents/com.upwork.automation.plist

# Check status
launchctl list | grep upwork

# Unload if needed
launchctl unload ~/Library/LaunchAgents/com.upwork.automation.plist
```

## Output

Proposals are saved to `proposals/YYYY-MM-DD/` with the format:
```
proposals/
└── 2024-01-15/
    ├── 20240115_143022_Python-Developer-for-Web-Scraping.md
    └── 20240115_143025_Automation-Expert-Needed.md
```

Each proposal includes:
- Job details and URL
- Client information
- Score breakdown
- Matching skills analysis
- Proposal draft template

## Logs

Logs are written to `logs/upwork_automation.log` with rotation.

## Project Structure

```
upwork-automation/
├── main.py                 # Entry point
├── config/
│   └── config.yaml         # Main configuration
├── src/
│   ├── config.py           # Configuration management
│   ├── upwork_client.py    # Browser automation
│   ├── ranking.py          # Job ranking engine
│   ├── proposal.py         # Proposal generation
│   ├── service.py          # Scheduler service
│   └── logger.py           # Logging setup
├── templates/
│   └── default_proposal.j2 # Proposal template
├── proposals/              # Generated proposals (gitignored)
├── logs/                   # Log files (gitignored)
└── browser_state/          # Browser session (gitignored)
```

## Important Notes

1. **Rate Limiting**: The service includes delays to avoid detection. Don't set intervals too short.
2. **2FA**: If you have 2FA enabled, you'll need to authenticate manually the first time.
3. **Terms of Service**: Use responsibly and in accordance with Upwork's ToS.
4. **Browser State**: The service saves browser cookies to avoid repeated logins. Clear `browser_state/` if you have login issues.

## Troubleshooting

**Cloudflare blocking / Bot detection:**
- Use the Chrome CDP method (see Step 4 above)
- Make sure Chrome is started with `--remote-debugging-port=9222`
- Log in manually in Chrome before running the script

**"Could not connect to Chrome CDP" error:**
- Close ALL Chrome windows first
- Start Chrome with: `/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug`
- Make sure no other process is using port 9222

**Login fails:**
- Check credentials in `.env`
- Delete `browser_state/` and try again
- Use Chrome CDP method instead of Playwright browser

**No jobs found:**
- Expand search filters in `config.yaml`
- Check if keywords are too specific
- Verify you're logged in by checking the browser window

**Proposals not generated:**
- Lower the `ranking.threshold` value
- Check `logs/upwork_automation.log` for details

## License

MIT

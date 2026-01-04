# Upwork Automation Configuration Guide

This document provides a comprehensive breakdown of the `config.yaml` file structure, explaining how each section works and how they interact to control the Upwork automation system.

## Table of Contents

1. [Configuration Architecture](#configuration-architecture)
2. [Scheduler Settings](#scheduler-settings)
3. [Search Parameters](#search-parameters)
4. [Search Profiles](#search-profiles)
5. [Ranking System](#ranking-system)
6. [Proposal Settings](#proposal-settings)
7. [Logging Configuration](#logging-configuration)
8. [AI Configuration](#ai-configuration)
9. [Configuration Flow](#configuration-flow)
10. [Best Practices](#best-practices)

---

## Configuration Architecture

The configuration system uses **Pydantic models** for type safety and validation. The structure is:

```
config.yaml → Pydantic Models → Application Runtime
     ↓              ↓                    ↓
  YAML File    Type Validation    Service Execution
```

**Key Files:**
- `config/config.yaml` - Main configuration file
- `src/config.py` - Pydantic model definitions
- `.env` - Credentials (never in YAML!)

---

## Scheduler Settings

Controls when and how often the automation runs.

```yaml
scheduler:
  interval_minutes: 60        # How often to search for jobs
  active_hours:               # Optional time window
    start: "09:00"           # Start time (24-hour format)
    end: "18:00"             # End time (24-hour format)
  timezone: "Australia/Sydney"  # IANA timezone
```

### Parameters Explained

**`interval_minutes`** (integer, default: 60)
- How frequently the service runs job searches
- Minimum recommended: 30 minutes (avoid rate limiting)
- Maximum practical: 1440 (once per day)

**`active_hours`** (optional object)
- Restricts automation to specific hours
- If empty/null, runs 24/7
- Times are in 24-hour format (HH:MM)
- Checks happen at each scheduled run

**`timezone`** (string, default: "UTC")
- Must be a valid IANA timezone (e.g., "America/New_York")
- Used for active_hours calculations
- Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

### How It Works

1. APScheduler creates an `IntervalTrigger` with the specified minutes
2. Before each run, `_should_run_now()` checks if current time is within active_hours
3. If outside active hours, the run is skipped (logged but not executed)
4. Service continues running and will execute on next interval

---

## Search Parameters

Legacy single-search configuration. **Note:** If `search_profiles` are defined, those take priority.

```yaml
search:
  keywords:
    - "python developer"
    - "web scraping"
  category: "Web, Mobile & Software Dev"
  experience_levels:
    - "intermediate"
    - "expert"
  job_types:
    - "hourly"
    - "fixed"
  client_history:
    min_jobs_posted: 1
    min_hire_rate: 0
    min_total_spent: 0
  budget:
    min_hourly: 25
    max_hourly: 150
    min_fixed: 100
    max_fixed: 10000
  posted_within_hours: 24
  max_results: 20
```

### Parameters Explained

**`keywords`** (list of strings)
- Search terms to query on Upwork
- Each keyword triggers a separate search
- Examples: "python developer", "web scraping", "react developer"
- More specific = better matches, broader = more results

**`category`** (string, optional)
- Upwork job category filter
- Common categories:
  - "Web, Mobile & Software Dev"
  - "Data Science & Analytics"
  - "Design & Creative"
  - "Writing & Translation"
- Corresponds to Upwork's category system

**`experience_levels`** (list of strings)
- Filter by required experience level
- Valid values: `entry`, `intermediate`, `expert`
- Multiple selections allowed
- Maps to Upwork's experience level filter

**`job_types`** (list of strings)
- Filter by job payment structure
- Valid values: `hourly`, `fixed`
- `hourly` = hourly-rate contracts
- `fixed` = fixed-price projects

**`client_history`** (object)
- Filters based on client's Upwork history
- `min_jobs_posted`: Minimum number of jobs client has posted (0 = no filter)
- `min_hire_rate`: Minimum percentage of posted jobs where client hired (0-100)
- `min_total_spent`: Minimum USD client has spent on Upwork

**`budget`** (object)
- Hourly rate filters:
  - `min_hourly`: Minimum hourly rate in USD (e.g., 25)
  - `max_hourly`: Maximum hourly rate in USD (e.g., 150)
- Fixed price filters:
  - `min_fixed`: Minimum fixed budget in USD (e.g., 100)
  - `max_fixed`: Maximum fixed budget in USD (e.g., 10000)

**`posted_within_hours`** (integer)
- Only find jobs posted within the last X hours
- 24 = last day, 168 = last week, 720 = last month
- Smaller values = fresher jobs, less competition

**`max_results`** (integer)
- Maximum number of job listings to fetch per keyword search
- Higher = more jobs but slower search
- Recommended: 20-50

---

## Search Profiles

Modern multi-profile approach for different job search strategies. **Profiles override legacy `search` config when present.**

```yaml
search_profiles:
  - name: "Python Development"
    enabled: true
    keywords:
      - "python developer"
      - "python programmer"
    category: "Web, Mobile & Software Dev"
    experience_levels:
      - "intermediate"
      - "expert"
    job_types:
      - "hourly"
      - "fixed"
    client_history:
      min_jobs_posted: 2
      min_hire_rate: 50
      min_total_spent: 1000
    budget:
      min_hourly: 30
      max_hourly: 150
      min_fixed: 1000
      max_fixed: 10000
    posted_within_hours: 24
    max_results: 15
```

### How Search Profiles Work

1. **Profile Processing:**
   - Service checks if `search_profiles` exists and has items
   - If yes, uses profiles; if no, falls back to `search` config
   - Only `enabled: true` profiles are processed

2. **Search Execution Flow:**
   ```
   For each enabled profile:
     For each keyword in profile:
       Search Upwork with keyword + profile filters
       Collect job results

   Deduplicate jobs by job ID across all profiles
   Proceed to ranking
   ```

3. **Profile Benefits:**
   - Different strategies for different niches
   - Separate filters per job type
   - Easy to enable/disable without deletion
   - Better organization for complex searches

### Profile Strategy Examples

**High-Quality Clients Only:**
```yaml
- name: "Premium Clients"
  enabled: true
  keywords: ["python developer"]
  client_history:
    min_jobs_posted: 5
    min_hire_rate: 80
    min_total_spent: 10000
  budget:
    min_hourly: 50
```

**Entry-Level, High Volume:**
```yaml
- name: "Entry Level"
  enabled: true
  keywords: ["developer", "programmer"]
  experience_levels: ["entry"]
  client_history:
    min_jobs_posted: 0
    min_hire_rate: 0
  posted_within_hours: 168
  max_results: 100
```

**Niche Specialization:**
```yaml
- name: "Web Scraping Specialist"
  enabled: true
  keywords: ["web scraping", "data extraction", "crawler"]
  experience_levels: ["expert"]
  budget:
    min_hourly: 40
```

---

## Ranking System

Controls how jobs are scored and which qualify for proposal generation.

```yaml
ranking:
  threshold: 60
  weights:
    skills_match: 0.25
    budget_score: 0.20
    client_quality: 0.20
    job_clarity: 0.15
    competition: 0.10
    recency: 0.10
  my_skills:
    - "python"
    - "web scraping"
    - "automation"
```

### How Ranking Works

**Overall Formula:**
```
Final Score = (AI Score × 0.7) + (Rule-Based Score × 0.3)

Rule-Based Score =
  (skills_match_score × weight.skills_match) +
  (budget_score × weight.budget_score) +
  (client_quality_score × weight.client_quality) +
  (job_clarity_score × weight.job_clarity) +
  (competition_score × weight.competition) +
  (recency_score × weight.recency)
```

### Ranking Components (0-100 each)

**1. Skills Match (`skills_match`)**

Calculates how well job requirements match your skills:
```python
# Exact matches in required_skills
matches = count of (my_skills found in job.required_skills)

# Partial matches in description
matches += 0.5 × count of (my_skills mentioned in job.description)

# Match ratio
score = (matches / len(job.required_skills)) × 100
```

**Example:**
- Job requires: ["Python", "Django", "PostgreSQL"]
- Your skills: ["python", "django", "web scraping"]
- Matches: 2 exact (Python, Django)
- Score: (2/3) × 100 = 66.67

**2. Budget Score (`budget_score`)**

Evaluates budget attractiveness:

For hourly jobs:
```python
if job.budget_max >= config.max_hourly:
    score = 100
elif job.budget_max >= config.min_hourly:
    # Scale from 50-100 within your range
    position = (job.budget_max - min_hourly) / (max_hourly - min_hourly)
    score = 50 + (position × 50)
else:
    # Below minimum, score decreases
    score = max(0, 50 - penalty)
```

**Example:**
- Your range: $25-$150/hr
- Job offers: $100/hr
- Position in range: (100-25)/(150-25) = 0.6
- Score: 50 + (0.6 × 50) = 80

**3. Client Quality (`client_quality`)**

Base score: 50, then adjusted by:
- Payment verified: +15
- Rating ≥4.8: +20 | ≥4.5: +15 | ≥4.0: +10 | <3.5: -15
- Total spent ≥$100k: +15 | ≥$10k: +10 | ≥$1k: +5 | <$100: -5
- Hire rate ≥80%: +10 | ≥50%: +5 | <30%: -10

**Example:**
```
Base: 50
+ Payment verified: 15
+ Rating 4.9: 20
+ Spent $50k: 10
+ Hire rate 75%: 5
= 100
```

**4. Job Clarity (`job_clarity`)**

Base score: 50, adjusted by:

Description length:
- ≥200 words: +20
- ≥100 words: +10
- <30 words: -15

Positive keywords (+3 each): "requirements", "deliverables", "deadline", "milestone", "experience", "skills", "looking for", "project"

Negative keywords (-10 each): "asap", "urgent", "cheap", "lowest bid", "budget is tight", "test task", "unpaid"

**Example:**
```
Base: 50
+ 250 words: 20
+ Has "requirements", "deliverables", "skills": 9
- Has "urgent": -10
= 69
```

**5. Competition (`competition`)**

Scores based on number of proposals:
- 0 proposals: 100
- 1-5: 90
- 6-10: 75
- 11-20: 60
- 21-35: 40
- 36-50: 25
- 50+: 10

**6. Recency (`recency`)**

Scores based on hours since posted:
- ≤1 hour: 100
- ≤3 hours: 90
- ≤6 hours: 80
- ≤12 hours: 70
- ≤24 hours: 60
- ≤48 hours: 40
- ≤72 hours: 25
- 72+ hours: 10

### Weights Configuration

**`weights`** (object, must sum to 1.0)

Determines importance of each factor. Default:
```yaml
skills_match: 0.25     # 25% - Most important
budget_score: 0.20     # 20%
client_quality: 0.20   # 20%
job_clarity: 0.15      # 15%
competition: 0.10      # 10%
recency: 0.10          # 10%
```

**Strategy Examples:**

Focus on low competition:
```yaml
competition: 0.30
skills_match: 0.20
budget_score: 0.15
client_quality: 0.15
job_clarity: 0.10
recency: 0.10
```

Focus on high-quality clients:
```yaml
client_quality: 0.35
skills_match: 0.25
budget_score: 0.15
job_clarity: 0.10
competition: 0.10
recency: 0.05
```

**`threshold`** (integer, 0-100)
- Minimum score required to generate a proposal
- Jobs scoring below threshold are ignored
- Lower = more proposals, higher = more selective
- Recommended: 50-70

**`my_skills`** (list of strings)
- Your actual skills for matching
- Case-insensitive matching
- Used for skills_match scoring
- Also passed to AI for ranking/proposal generation

---

## Proposal Settings

Controls how proposals are generated and saved.

```yaml
proposal:
  template: "templates/default_proposal.j2"
  output_directory: "proposals"
  include_job_details: true
  max_proposals_per_run: 5
```

### Parameters Explained

**`template`** (string)
- Path to Jinja2 template file
- Relative to project root
- Used only if AI proposal generation is disabled
- Variables available: `{{ job.title }}`, `{{ job.description }}`, `{{ score }}`, etc.

**`output_directory`** (string)
- Where to save generated proposals
- Subdirectories created by date: `proposals/YYYY-MM-DD/`
- Gitignored by default

**`include_job_details`** (boolean)
- If true: saves job metadata with proposal
- If false: saves only proposal text
- Recommended: true (helps with tracking)

**`max_proposals_per_run`** (integer)
- Maximum number of proposals to generate per cycle
- Processes top-scored jobs first
- Prevents spam/overwhelm
- Recommended: 5-10

### Proposal Generation Flow

1. Jobs are ranked and filtered by threshold
2. Top N jobs (up to `max_proposals_per_run`) selected
3. For each job:
   - If AI enabled: Generate AI proposal
   - If AI disabled: Use Jinja2 template
4. Proposal wrapped with metadata (job details, scores, client info)
5. Saved to: `{output_directory}/{YYYY-MM-DD}/{timestamp}_{sanitized_title}.md`

### Proposal File Format

```markdown
# Proposal for: {job.title}

## Job Details
- URL: {job.url}
- Type: {job.job_type}
- Posted: {job.posted_at}
- Proposals: {job.proposals_count}
- Required Skills: {job.required_skills}

## AI Analysis
- Score: {score}/100
- AI Score: {ai_score}/100
- Rule Score: {rule_score}/100
- Reasoning: {ai_reasoning}
- Strengths: {strengths}
- Concerns: {concerns}

## Client Info
- Payment Verified: {client.payment_verified}
- Total Spent: ${client.total_spent}
- Rating: {client.rating}/5.0

---

## Job Description
{job.description}

---

## AI-GENERATED PROPOSAL
{ai_generated_proposal_text}

---

*Generated: {timestamp}*
*Job ID: {job.id}*
```

---

## Logging Configuration

Controls application logging behavior.

```yaml
logging:
  level: "INFO"
  file: "logs/upwork_automation.log"
  max_size_mb: 10
  backup_count: 5
```

### Parameters Explained

**`level`** (string)
- Logging verbosity level
- Valid values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `DEBUG`: Very verbose, all operations
- `INFO`: Normal operation logs (recommended)
- `WARNING`: Only warnings and errors
- `ERROR`: Only errors

**`file`** (string)
- Path to log file (relative to project root)
- Directory created automatically if not exists
- Gitignored by default

**`max_size_mb`** (integer)
- Maximum size of a single log file in megabytes
- When exceeded, file is rotated (renamed to `.log.1`, `.log.2`, etc.)
- Prevents unlimited disk usage

**`backup_count`** (integer)
- Number of rotated log files to keep
- Oldest files deleted when limit reached
- Total disk usage ≈ `max_size_mb × (backup_count + 1)`

### Log Rotation Example

```
logs/
  upwork_automation.log       (current, 9.8 MB)
  upwork_automation.log.1     (10 MB)
  upwork_automation.log.2     (10 MB)
  upwork_automation.log.3     (10 MB)
  upwork_automation.log.4     (10 MB)
  upwork_automation.log.5     (10 MB)
```

When current log reaches 10 MB:
- `.log.5` deleted
- `.log.4` → `.log.5`
- `.log.3` → `.log.4`
- `.log.2` → `.log.3`
- `.log.1` → `.log.2`
- `.log` → `.log.1`
- New `.log` created

---

## AI Configuration

Controls AI-powered ranking and proposal generation using OpenAI-compatible APIs.

```yaml
ai:
  enabled: true
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o-mini"
  max_tokens: 2000
  ranking_mode: "parallel"
  max_concurrent: 5
  batch_size: 5
  my_experience: |
    I am an experienced developer...
  ranking_system_prompt: |
    You are an expert freelancer consultant...
  ranking_user_prompt: |
    Analyze this job posting...
  proposal_system_prompt: |
    You are an expert freelance proposal writer...
  proposal_user_prompt: |
    Write a proposal for this job...
```

### Core AI Settings

**`enabled`** (boolean)
- Master switch for AI features
- If false: falls back to rule-based ranking and template proposals
- Requires `OPENAI_API_KEY` in `.env`

**`base_url`** (string)
- API endpoint URL
- OpenAI: `https://api.openai.com/v1`
- Ollama (local): `http://localhost:11434/v1`
- Other providers: their compatible endpoint

**`model`** (string)
- Model identifier
- OpenAI: `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`
- Ollama: `llama3`, `mistral`, `codellama`
- Must be available at the `base_url`

**`max_tokens`** (integer)
- Maximum tokens in AI response
- Higher = longer responses, more cost
- Recommended: 1000-2000 for proposals

### Ranking Modes

**`ranking_mode`** (string: "parallel" | "batch" | "sequential")

Controls how multiple jobs are ranked:

**1. Parallel Mode** (recommended)
```yaml
ranking_mode: "parallel"
max_concurrent: 5
```
- Makes concurrent API calls for different jobs
- `max_concurrent` limits simultaneous requests
- **Pros:** Fastest (5 jobs in ~same time as 1)
- **Cons:** More API calls, higher cost
- **Best for:** When speed matters, reasonable job counts (< 50)

**2. Batch Mode**
```yaml
ranking_mode: "batch"
batch_size: 5
```
- Sends multiple jobs in single API call
- Model ranks all jobs in one response
- **Pros:** Fewer API calls, lower cost
- **Cons:** Requires larger context, less reliable for many jobs
- **Best for:** Cost optimization, smaller job counts (< 20)

**3. Sequential Mode**
```yaml
ranking_mode: "sequential"
```
- One job at a time, one API call each
- **Pros:** Most reliable, predictable cost
- **Cons:** Slowest (N jobs = N × API call time)
- **Best for:** When reliability matters most, debugging

### AI Prompts

**`my_experience`** (multiline string)
- Your professional background summary
- Injected into ranking and proposal prompts
- Used by AI to assess fit and write personalized proposals
- Be specific about expertise, achievements, metrics

**`ranking_system_prompt`** (multiline string)
- Defines AI's role for job ranking
- Specifies output format (JSON structure)
- Sets scoring guidelines
- Example structure:
  ```json
  {
    "score": 75,
    "reasoning": "Good match because...",
    "strengths": ["Strong skill match", "Well-funded client"],
    "concerns": ["High competition", "Vague requirements"],
    "recommendation": "pursue"
  }
  ```

**`ranking_user_prompt`** (multiline string with variables)
- Template for ranking requests
- Variables substituted at runtime:
  - `{job_title}`: Job title
  - `{job_type}`: "hourly" or "fixed"
  - `{budget_info}`: Budget details
  - `{proposals_count}`: Number of proposals
  - `{client_rating}`: Client rating
  - `{client_spent}`: Client total spent
  - `{required_skills}`: Comma-separated skills
  - `{job_description}`: Full job description
  - `{my_skills}`: Your skills list
  - `{my_experience}`: Your experience summary

**`proposal_system_prompt`** (multiline string)
- Defines AI's role for proposal writing
- Sets tone, structure, style guidelines
- Specifies what to include/avoid
- Example guidelines:
  - Open with understanding of client's problem
  - Demonstrate relevant experience
  - Propose clear approach
  - Include clarifying questions
  - Keep concise (150-250 words)

**`proposal_user_prompt`** (multiline string with variables)
- Template for proposal generation requests
- Variables substituted at runtime:
  - All ranking variables, plus:
  - `{ranking_score}`: Final blended score
  - `{ranking_reasoning}`: AI's reasoning from ranking
  - `{matching_strengths}`: Identified strengths

### AI Integration Flow

```
Job Data → Ranking Phase → Proposal Phase → Saved Output
    ↓             ↓              ↓              ↓
Variables → User Prompt → AI Response → Markdown File
    ↓             ↓              ↓
My Skills → System Prompt → JSON Parse
    ↓                            ↓
Experience                   Score/Reasoning
```

---

## Configuration Flow

### Complete System Flow

```
1. START: python main.py
         ↓
2. Load config.yaml → Pydantic validation
         ↓
3. Load .env → Credentials
         ↓
4. Initialize Components:
   - UpworkClient (browser)
   - RankingEngine (rule-based)
   - AIEngine (if enabled)
   - ProposalGenerator
   - Scheduler
         ↓
5. SCHEDULER LOOP:
   ├─→ Check active_hours
   ├─→ Search Phase:
   │   ├─→ For each enabled search_profile:
   │   │   └─→ For each keyword:
   │   │       └─→ Search Upwork
   │   └─→ Deduplicate by job ID
   │
   ├─→ Ranking Phase:
   │   ├─→ Rule-based scoring (all jobs)
   │   ├─→ AI scoring (if enabled, all jobs)
   │   ├─→ Blend scores: AI×0.7 + Rule×0.3
   │   └─→ Filter by threshold
   │
   ├─→ Proposal Phase:
   │   ├─→ Sort by score (descending)
   │   ├─→ Take top N (max_proposals_per_run)
   │   ├─→ For each job:
   │   │   ├─→ AI generate proposal (if enabled)
   │   │   └─→ Template proposal (if AI disabled)
   │   └─→ Save to proposals/YYYY-MM-DD/
   │
   └─→ Wait interval_minutes → Repeat
```

### Configuration Priority

When multiple configs could apply:

1. **Search Strategy:**
   - `search_profiles` exist and have enabled profiles → Use profiles
   - `search_profiles` empty or all disabled → Use `search` config

2. **Ranking:**
   - AI enabled and available → Blended (AI×0.7 + Rule×0.3)
   - AI disabled or unavailable → Rule-based only

3. **Proposals:**
   - AI enabled and available → AI-generated proposals
   - AI disabled or unavailable → Template-based proposals

### Environment Variables (.env)

Configuration in `.env` (never in YAML):

```bash
# Upwork credentials
UPWORK_USERNAME=your_email@domain.com
UPWORK_PASSWORD=your_password
UPWORK_SECURITY_ANSWER=your_security_answer

# AI API key
OPENAI_API_KEY=sk-...
```

These are loaded by `pydantic-settings` and accessed via `Credentials` model.

---

## Best Practices

### 1. Start Simple, Then Optimize

**Phase 1: Basic Setup**
```yaml
search_profiles:
  - name: "Test Search"
    enabled: true
    keywords: ["your main skill"]
    experience_levels: ["intermediate", "expert"]
    posted_within_hours: 24
    max_results: 10

ranking:
  threshold: 70  # High threshold initially

proposal:
  max_proposals_per_run: 3  # Start small
```

**Phase 2: Analyze Results**
- Check logs for job count
- Review generated proposals
- Note which jobs scored well

**Phase 3: Expand**
- Add more keywords
- Lower threshold if too restrictive
- Increase max_results
- Add more search profiles

### 2. Manage API Costs

**For OpenAI:**
- Use `gpt-4o-mini` instead of `gpt-4o` (cheaper)
- Use `batch` mode for small job counts (< 20)
- Limit `max_results` and `max_proposals_per_run`

**For Local LLM (Ollama):**
```yaml
ai:
  enabled: true
  base_url: "http://localhost:11434/v1"
  model: "llama3"  # Free, runs locally
```

### 3. Optimize Ranking Weights

**Strategy: Low Competition Focus**
```yaml
ranking:
  threshold: 55
  weights:
    competition: 0.30    # Prioritize
    recency: 0.20        # Get there first
    skills_match: 0.20
    client_quality: 0.15
    budget_score: 0.10
    job_clarity: 0.05
```

**Strategy: High-Quality Clients Only**
```yaml
ranking:
  threshold: 75          # High bar
  weights:
    client_quality: 0.35  # Most important
    budget_score: 0.25    # Good pay
    skills_match: 0.20
    job_clarity: 0.10
    competition: 0.05
    recency: 0.05
```

**Strategy: Perfect Skill Match**
```yaml
ranking:
  threshold: 65
  weights:
    skills_match: 0.40    # Must match well
    client_quality: 0.20
    budget_score: 0.15
    job_clarity: 0.15
    competition: 0.05
    recency: 0.05
```

### 4. Use Search Profiles Strategically

**Multiple Niches:**
```yaml
search_profiles:
  - name: "Python Backend"
    enabled: true
    keywords: ["python developer", "django", "flask"]
    budget:
      min_hourly: 40

  - name: "JavaScript Frontend"
    enabled: true
    keywords: ["react developer", "vue developer"]
    budget:
      min_hourly: 35

  - name: "Full Stack"
    enabled: true
    keywords: ["full stack developer"]
    budget:
      min_hourly: 50
```

**Quality Tiers:**
```yaml
search_profiles:
  - name: "Premium Clients"
    enabled: true
    keywords: ["python developer"]
    client_history:
      min_total_spent: 10000
      min_hire_rate: 80
    budget:
      min_hourly: 60

  - name: "Regular Clients"
    enabled: true
    keywords: ["python developer"]
    client_history:
      min_total_spent: 1000
      min_hire_rate: 50
    budget:
      min_hourly: 35
```

### 5. Avoid Over-Automation

**Don't:**
- Set `interval_minutes` < 30 (risk of rate limiting/ban)
- Set `max_proposals_per_run` > 20 (quality over quantity)
- Use `posted_within_hours: 720` with `interval_minutes: 30` (duplicate searches)

**Do:**
- Review generated proposals before submitting
- Adjust ranking based on actual results
- Monitor logs for errors
- Periodically check if still logged in to Upwork

### 6. Credential Security

**Never:**
```yaml
# ❌ Don't put credentials in config.yaml
search:
  username: "my_email@domain.com"  # WRONG!
```

**Always:**
```bash
# ✅ Put credentials in .env
UPWORK_USERNAME=my_email@domain.com
```

And ensure `.env` is in `.gitignore`!

### 7. Testing Configuration

```bash
# Test config loads without errors
python main.py --test

# Run single cycle to test search/ranking/proposals
python main.py --once

# Run with immediate execution
python main.py

# Run without immediate execution (wait for interval)
python main.py --no-immediate
```

### 8. Monitoring and Maintenance

**Check logs regularly:**
```bash
tail -f logs/upwork_automation.log
```

**Watch for:**
- Login failures → Re-login with `python main.py --login`
- No jobs found → Broaden search criteria
- Low-scoring jobs → Adjust ranking weights or threshold
- AI failures → Check API key, model availability

**Weekly review:**
- Success rate of proposals
- Quality of matched jobs
- Adjust ranking weights accordingly

---

## Common Configuration Scenarios

### Scenario 1: New to Upwork, Building Profile

**Goal:** Get any reasonable jobs to build reputation

```yaml
search_profiles:
  - name: "Entry Level Opportunities"
    enabled: true
    keywords: ["developer", "programmer", "web development"]
    experience_levels: ["entry", "intermediate"]
    client_history:
      min_jobs_posted: 0
      min_hire_rate: 0
      min_total_spent: 0
    budget:
      min_hourly: 15
      max_hourly: 50
    posted_within_hours: 72
    max_results: 50

ranking:
  threshold: 45  # Lower threshold
  weights:
    competition: 0.30   # Focus on low competition
    recency: 0.25       # Get there early
    skills_match: 0.20
    job_clarity: 0.15
    budget_score: 0.05
    client_quality: 0.05

proposal:
  max_proposals_per_run: 10  # More proposals
```

### Scenario 2: Established Freelancer, High-Value Only

**Goal:** Only pursue premium, high-paying clients

```yaml
search_profiles:
  - name: "Premium Projects"
    enabled: true
    keywords: ["senior developer", "lead developer", "architect"]
    experience_levels: ["expert"]
    client_history:
      min_jobs_posted: 10
      min_hire_rate: 70
      min_total_spent: 50000
    budget:
      min_hourly: 75
      min_fixed: 5000
    posted_within_hours: 48
    max_results: 20

ranking:
  threshold: 80  # Very high threshold
  weights:
    client_quality: 0.30
    budget_score: 0.25
    skills_match: 0.25
    job_clarity: 0.15
    recency: 0.03
    competition: 0.02

proposal:
  max_proposals_per_run: 3  # Selective
```

### Scenario 3: Niche Specialist

**Goal:** Only perfect-match jobs in specific domain

```yaml
search_profiles:
  - name: "Web Scraping Specialist"
    enabled: true
    keywords:
      - "web scraping"
      - "data extraction"
      - "crawler"
      - "selenium"
      - "playwright"
    experience_levels: ["intermediate", "expert"]
    budget:
      min_hourly: 40
    posted_within_hours: 48
    max_results: 30

ranking:
  threshold: 70
  weights:
    skills_match: 0.40   # Must match skills!
    client_quality: 0.20
    budget_score: 0.15
    job_clarity: 0.15
    competition: 0.05
    recency: 0.05

my_skills:
  - "web scraping"
  - "data extraction"
  - "selenium"
  - "playwright"
  - "beautifulsoup"
  - "scrapy"
  - "puppeteer"
```

---

## Troubleshooting Configuration Issues

### Config Won't Load

**Error:** `Configuration file not found`
- Check file is at `config/config.yaml`
- Check filename spelling (case-sensitive on Linux/Mac)

**Error:** `YAML parsing error`
- Validate YAML syntax: https://www.yamllint.com/
- Check indentation (must be spaces, not tabs)
- Check for special characters in strings

**Error:** `Validation error for AppConfig`
- Check all required fields present
- Check weights sum to 1.0
- Check valid enum values (experience_levels, job_types, etc.)

### No Jobs Found

**Possible causes:**
- Keywords too specific → Broaden keywords
- Budget range too narrow → Expand min/max
- `posted_within_hours` too small → Increase to 48-72
- `client_history` too restrictive → Lower minimums
- Not logged in → Run `python main.py --login`

### No Proposals Generated

**Possible causes:**
- All jobs scored below threshold → Lower `ranking.threshold`
- `max_proposals_per_run: 0` → Increase to ≥ 1
- AI failure and no template → Check API key, check logs
- No jobs met minimum client criteria → Review search filters

### AI Not Working

**Check:**
1. `ai.enabled: true` in config
2. `OPENAI_API_KEY` set in `.env`
3. API key valid and has credits
4. `base_url` correct for your provider
5. `model` available at that base_url
6. Network connection working
7. Check logs for API error messages

---

## Configuration Validation Checklist

Before running in production:

- [ ] Ranking weights sum to 1.0
- [ ] At least one search profile enabled OR search.keywords not empty
- [ ] Threshold is reasonable (40-80)
- [ ] Budget ranges make sense (min < max)
- [ ] `interval_minutes` ≥ 30
- [ ] Active hours format correct (HH:MM)
- [ ] Timezone valid IANA string
- [ ] `my_skills` list populated
- [ ] API credentials in `.env`, not config.yaml
- [ ] Log file path valid and writable
- [ ] Proposal output directory exists or can be created
- [ ] Template file exists (if AI disabled)

---

## Summary

The `config.yaml` file is the central control system for Upwork automation:

1. **Scheduler** controls *when* searches run
2. **Search/Search Profiles** define *what* jobs to find
3. **Ranking** determines *which* jobs are worth pursuing
4. **Proposal** settings control *how* proposals are generated
5. **AI** configuration adds intelligent analysis and writing
6. **Logging** provides visibility into operations

By understanding how these sections interact, you can fine-tune the system for your specific needs—whether you're building a reputation, pursuing premium clients, or specializing in a niche.

**Key principle:** Start conservative (high threshold, few proposals, narrow search), monitor results, then expand based on what works.

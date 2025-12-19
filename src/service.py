"""Main service orchestrator for Upwork automation"""
import asyncio
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import pytz

from .config import get_config, get_project_root
from .upwork_client import UpworkClient
from .ranking import RankingEngine
from .proposal import ProposalGenerator
from .ai_engine import AIEngine
from .models import RankedJob, Proposal, JobPosting
from .logger import setup_logging, get_logger


class UpworkAutomationService:
    """Main service that orchestrates the job search and proposal generation"""
    
    def __init__(self):
        self.config = get_config()
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.ranking_engine = RankingEngine()
        self.proposal_generator = ProposalGenerator()
        self.ai_engine = AIEngine()
        self.is_running = False
        self.last_run: Optional[datetime] = None
        self.run_count = 0
        
        # Set up logging
        setup_logging()
        self.logger = get_logger()
    
    async def run_job_search(self):
        """Execute a single job search cycle"""
        self.logger.info("=" * 60)
        self.logger.info("Starting job search cycle")
        self.logger.info("=" * 60)
        
        self.run_count += 1
        self.last_run = datetime.now()
        
        all_jobs = []
        all_ranked_jobs = []
        all_proposals = []
        
        try:
            async with UpworkClient() as client:
                # Search for each keyword
                for keyword in self.config.search.keywords:
                    self.logger.info(f"Searching for: {keyword}")
                    
                    try:
                        jobs = await client.search_jobs(keyword)
                        self.logger.info(f"Found {len(jobs)} jobs for '{keyword}'")
                        all_jobs.extend(jobs)
                    except Exception as e:
                        self.logger.error(f"Error searching for '{keyword}': {e}")
                        continue
                
                if not all_jobs:
                    self.logger.warning("No jobs found in this cycle")
                    return
                
                # Remove duplicates based on job ID
                seen_ids = set()
                unique_jobs = []
                for job in all_jobs:
                    if job.id not in seen_ids:
                        seen_ids.add(job.id)
                        unique_jobs.append(job)
                
                self.logger.info(f"Total unique jobs found: {len(unique_jobs)}")
                
                # Rank all jobs (using AI if enabled)
                self.logger.info("Ranking jobs...")
                if self.ai_engine.is_available:
                    self.logger.info("Using AI-powered ranking")
                    ranked_jobs = await self._ai_rank_jobs(unique_jobs)
                else:
                    self.logger.info("Using rule-based ranking (AI not configured)")
                    ranked_jobs = self.ranking_engine.rank_jobs(unique_jobs)
                
                all_ranked_jobs = ranked_jobs
                
                # Log ranking summary
                qualifying = [rj for rj in ranked_jobs if rj.meets_threshold]
                self.logger.info(f"Jobs meeting threshold ({self.config.ranking.threshold}): {len(qualifying)}")
                
                # Log top jobs
                for i, rj in enumerate(ranked_jobs[:5]):
                    status = "✓" if rj.meets_threshold else "✗"
                    self.logger.info(f"  {status} #{i+1}: {rj.job.title[:50]}... (Score: {rj.score})")
                
                # Generate proposals for qualifying jobs (using AI if enabled)
                if qualifying:
                    self.logger.info("Generating proposals...")
                    if self.ai_engine.is_available:
                        proposals = await self._ai_generate_proposals(qualifying)
                    else:
                        proposals = self.proposal_generator.process_jobs(ranked_jobs)
                    all_proposals = proposals
                    self.logger.info(f"Generated {len(proposals)} proposals")
                else:
                    self.logger.info("No jobs met the threshold, skipping proposal generation")
        
        except Exception as e:
            self.logger.error(f"Error in job search cycle: {e}", exc_info=True)
        
        finally:
            # Summary
            self.logger.info("-" * 60)
            self.logger.info("Cycle Summary:")
            self.logger.info(f"  Total jobs found: {len(all_jobs)}")
            self.logger.info(f"  Unique jobs: {len(all_ranked_jobs)}")
            self.logger.info(f"  Jobs meeting threshold: {len([rj for rj in all_ranked_jobs if rj.meets_threshold])}")
            self.logger.info(f"  Proposals generated: {len(all_proposals)}")
            self.logger.info(f"  Next run in: {self.config.scheduler.interval_minutes} minutes")
            self.logger.info("=" * 60)
    
    async def _ai_rank_jobs(self, jobs: list[JobPosting]) -> list[RankedJob]:
        """Rank jobs using AI engine with configurable mode (parallel/batch/sequential)"""
        my_skills = self.config.ranking.my_skills
        my_experience = self.config.ai.my_experience
        ranking_mode = self.config.ai.ranking_mode
        
        self.logger.info(f"AI ranking mode: {ranking_mode}")
        
        # Get AI rankings based on mode
        if ranking_mode == "parallel":
            ai_results = await self.ai_engine.rank_jobs_parallel(
                jobs, my_skills, my_experience,
                max_concurrent=self.config.ai.max_concurrent
            )
        elif ranking_mode == "batch":
            ai_results = await self.ai_engine.rank_jobs_batch(
                jobs, my_skills, my_experience,
                batch_size=self.config.ai.batch_size
            )
        else:  # sequential
            ai_results = []
            for job in jobs:
                result = await self.ai_engine.rank_job(job, my_skills, my_experience)
                ai_results.append(result)
        
        # Get rule-based scores for blending
        rule_based_jobs = self.ranking_engine.rank_jobs(jobs)
        
        # Combine AI and rule-based scores
        ranked_jobs = []
        for i, (job, ai_result, rule_based) in enumerate(zip(jobs, ai_results, rule_based_jobs)):
            try:
                if ai_result.get("ai_ranked"):
                    score = ai_result["score"]
                    blended_score = score * 0.7 + rule_based.score * 0.3
                else:
                    blended_score = rule_based.score
                
                ranked_job = RankedJob(
                    job=job,
                    score=round(blended_score, 2),
                    score_breakdown={
                        "ai_score": ai_result.get("score", 0),
                        "rule_score": rule_based.score,
                        "ai_reasoning": ai_result.get("reasoning", ""),
                        "strengths": ai_result.get("strengths", []),
                        "concerns": ai_result.get("concerns", []),
                    },
                    meets_threshold=blended_score >= self.config.ranking.threshold
                )
                ranked_jobs.append(ranked_job)
                
            except Exception as e:
                self.logger.warning(f"Error processing job {job.title[:30]}: {e}")
                ranked_jobs.append(rule_based)
        
        # Sort by score descending
        ranked_jobs.sort(key=lambda x: x.score, reverse=True)
        return ranked_jobs
    
    async def _ai_generate_proposals(self, ranked_jobs: list[RankedJob]) -> list[Proposal]:
        """Generate proposals using AI engine"""
        proposals = []
        max_proposals = self.config.proposal.max_proposals_per_run
        my_skills = self.config.ranking.my_skills
        my_experience = self.config.ai.my_experience
        
        for ranked_job in ranked_jobs[:max_proposals]:
            try:
                job = ranked_job.job
                
                # Generate AI proposal
                ai_proposal_text = await self.ai_engine.generate_proposal(
                    job=job,
                    my_skills=my_skills,
                    my_experience=my_experience,
                    ranking_info=ranked_job.score_breakdown
                )
                
                # Create proposal with metadata wrapper
                full_content = self._format_ai_proposal(job, ranked_job, ai_proposal_text)
                
                proposal = Proposal(
                    job=job,
                    content=full_content,
                    generated_at=datetime.now()
                )
                
                # Save to disk
                self.proposal_generator.save_proposal(proposal)
                proposals.append(proposal)
                
                self.logger.info(f"Generated AI proposal for: {job.title[:40]}...")
                
            except Exception as e:
                self.logger.error(f"AI proposal generation failed for {ranked_job.job.title[:30]}: {e}")
                continue
        
        return proposals
    
    def _format_ai_proposal(self, job: JobPosting, ranked_job: RankedJob, ai_text: str) -> str:
        """Format AI-generated proposal with metadata"""
        breakdown = ranked_job.score_breakdown
        
        return f"""# Proposal for: {job.title}

## Job Details
- **URL**: {job.url}
- **Type**: {job.job_type.capitalize()}
- **Posted**: {job.posted_at.strftime('%Y-%m-%d %H:%M') if job.posted_at else 'Unknown'}
- **Proposals**: {job.proposals_count}
- **Required Skills**: {', '.join(job.required_skills) if job.required_skills else 'None specified'}

## AI Analysis
- **Score**: {ranked_job.score}/100
- **AI Score**: {breakdown.get('ai_score', 'N/A')}/100
- **Rule Score**: {breakdown.get('rule_score', 'N/A')}/100
- **Reasoning**: {breakdown.get('ai_reasoning', 'N/A')}
- **Strengths**: {', '.join(breakdown.get('strengths', [])) or 'N/A'}
- **Concerns**: {', '.join(breakdown.get('concerns', [])) or 'N/A'}

## Client Info
- **Payment Verified**: {'Yes' if job.client.payment_verified else 'No'}
- **Total Spent**: ${job.client.total_spent or 0:,.2f}
- **Rating**: {job.client.rating or 'N/A'}/5.0

---

## Job Description

{job.description}

---

## AI-GENERATED PROPOSAL

{ai_text}

---

*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
*Job ID: {job.id}*
"""
    
    def _should_run_now(self) -> bool:
        """Check if we should run based on active hours"""
        active_hours = self.config.scheduler.active_hours
        if not active_hours:
            return True  # No restrictions
        
        tz = pytz.timezone(self.config.scheduler.timezone)
        now = datetime.now(tz)
        current_time = now.strftime("%H:%M")
        
        start = active_hours.get("start", "00:00")
        end = active_hours.get("end", "23:59")
        
        return start <= current_time <= end
    
    async def _scheduled_run(self):
        """Wrapper for scheduled runs with active hours check"""
        if self._should_run_now():
            await self.run_job_search()
        else:
            self.logger.info("Outside active hours, skipping this run")
    
    async def start(self, run_immediately: bool = True):
        """Start the scheduler service"""
        self.logger.info("Starting Upwork Automation Service")
        self.logger.info(f"Search keywords: {self.config.search.keywords}")
        self.logger.info(f"Interval: every {self.config.scheduler.interval_minutes} minutes")
        self.logger.info(f"Ranking threshold: {self.config.ranking.threshold}")
        
        if self.config.scheduler.active_hours:
            self.logger.info(f"Active hours: {self.config.scheduler.active_hours}")
        
        # Create scheduler
        self.scheduler = AsyncIOScheduler(timezone=self.config.scheduler.timezone)
        
        # Add the job
        self.scheduler.add_job(
            self._scheduled_run,
            IntervalTrigger(minutes=self.config.scheduler.interval_minutes),
            id="job_search",
            name="Upwork Job Search",
            replace_existing=True
        )
        
        # Start scheduler
        self.scheduler.start()
        self.is_running = True
        
        # Optionally run immediately
        if run_immediately:
            self.logger.info("Running initial job search...")
            await self.run_job_search()
        
        self.logger.info("Scheduler started. Press Ctrl+C to stop.")
        
        # Keep the service running
        try:
            while self.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
            await self.stop()
    
    async def stop(self):
        """Stop the scheduler service"""
        self.logger.info("Stopping Upwork Automation Service...")
        self.is_running = False
        
        if self.scheduler:
            self.scheduler.shutdown(wait=True)
        
        self.logger.info("Service stopped")
    
    def get_status(self) -> dict:
        """Get current service status"""
        return {
            "is_running": self.is_running,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "run_count": self.run_count,
            "interval_minutes": self.config.scheduler.interval_minutes,
            "next_run": self.scheduler.get_job("job_search").next_run_time.isoformat() if self.scheduler and self.scheduler.get_job("job_search") else None
        }


async def run_service():
    """Run the automation service"""
    service = UpworkAutomationService()
    await service.start()


async def run_once():
    """Run a single search cycle without scheduling"""
    service = UpworkAutomationService()
    await service.run_job_search()


if __name__ == "__main__":
    asyncio.run(run_service())

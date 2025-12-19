"""Job ranking engine for Upwork automation"""
from datetime import datetime, timedelta
from typing import Optional

from .config import get_config
from .models import JobPosting, RankedJob
from .logger import get_logger

logger = get_logger()


class RankingEngine:
    """Ranks jobs based on configurable criteria"""
    
    def __init__(self):
        self.config = get_config()
        self.ranking_config = self.config.ranking
        self.weights = self.ranking_config.weights
        self.my_skills = [s.lower() for s in self.ranking_config.my_skills]
    
    def rank_jobs(self, jobs: list[JobPosting]) -> list[RankedJob]:
        """Rank a list of jobs and return sorted by score"""
        ranked_jobs = []
        
        for job in jobs:
            score, breakdown = self._calculate_score(job)
            meets_threshold = score >= self.ranking_config.threshold
            
            ranked_job = RankedJob(
                job=job,
                score=score,
                score_breakdown=breakdown,
                meets_threshold=meets_threshold
            )
            ranked_jobs.append(ranked_job)
        
        # Sort by score descending
        ranked_jobs.sort(key=lambda x: x.score, reverse=True)
        
        return ranked_jobs
    
    def _calculate_score(self, job: JobPosting) -> tuple[float, dict]:
        """Calculate the overall score for a job"""
        breakdown = {}
        
        # Skills match score (0-100)
        skills_score = self._score_skills_match(job)
        breakdown["skills_match"] = skills_score
        
        # Budget score (0-100)
        budget_score = self._score_budget(job)
        breakdown["budget_score"] = budget_score
        
        # Client quality score (0-100)
        client_score = self._score_client_quality(job)
        breakdown["client_quality"] = client_score
        
        # Job clarity score (0-100)
        clarity_score = self._score_job_clarity(job)
        breakdown["job_clarity"] = clarity_score
        
        # Competition score (0-100)
        competition_score = self._score_competition(job)
        breakdown["competition"] = competition_score
        
        # Recency score (0-100)
        recency_score = self._score_recency(job)
        breakdown["recency"] = recency_score
        
        # Calculate weighted total
        total_score = (
            skills_score * self.weights.skills_match +
            budget_score * self.weights.budget_score +
            client_score * self.weights.client_quality +
            clarity_score * self.weights.job_clarity +
            competition_score * self.weights.competition +
            recency_score * self.weights.recency
        )
        
        return round(total_score, 2), breakdown
    
    def _score_skills_match(self, job: JobPosting) -> float:
        """Score based on how well job skills match your skills"""
        if not job.required_skills or not self.my_skills:
            return 50  # Neutral score if no skills to compare
        
        job_skills = [s.lower() for s in job.required_skills]
        
        # Count matching skills
        matches = 0
        for job_skill in job_skills:
            for my_skill in self.my_skills:
                if my_skill in job_skill or job_skill in my_skill:
                    matches += 1
                    break
        
        # Also check description for skill mentions
        description_lower = job.description.lower()
        for my_skill in self.my_skills:
            if my_skill in description_lower:
                matches += 0.5
        
        # Calculate match percentage
        if len(job_skills) == 0:
            match_ratio = 0.5
        else:
            match_ratio = min(matches / len(job_skills), 1.0)
        
        return round(match_ratio * 100, 2)
    
    def _score_budget(self, job: JobPosting) -> float:
        """Score based on budget attractiveness"""
        search_config = self.config.search.budget
        
        if job.job_type == "hourly":
            if job.budget_max:
                # Score based on where the max rate falls in our preferred range
                if job.budget_max >= search_config.max_hourly:
                    return 100
                elif job.budget_max >= search_config.min_hourly:
                    range_size = search_config.max_hourly - search_config.min_hourly
                    position = job.budget_max - search_config.min_hourly
                    return round(50 + (position / range_size) * 50, 2)
                else:
                    # Below minimum
                    return max(0, 50 - ((search_config.min_hourly - job.budget_max) / search_config.min_hourly) * 50)
            return 50  # No budget info
        else:
            # Fixed price
            if job.fixed_price:
                if job.fixed_price >= search_config.max_fixed:
                    return 100
                elif job.fixed_price >= search_config.min_fixed:
                    range_size = search_config.max_fixed - search_config.min_fixed
                    position = job.fixed_price - search_config.min_fixed
                    return round(50 + (position / range_size) * 50, 2)
                else:
                    return max(0, 50 - ((search_config.min_fixed - job.fixed_price) / search_config.min_fixed) * 50)
            return 50  # No budget info
    
    def _score_client_quality(self, job: JobPosting) -> float:
        """Score based on client quality indicators"""
        client = job.client
        score = 50  # Base score
        
        # Payment verified is important
        if client.payment_verified:
            score += 15
        
        # Client rating
        if client.rating:
            if client.rating >= 4.8:
                score += 20
            elif client.rating >= 4.5:
                score += 15
            elif client.rating >= 4.0:
                score += 10
            elif client.rating < 3.5:
                score -= 15
        
        # Total spent indicates serious client
        if client.total_spent:
            if client.total_spent >= 100000:
                score += 15
            elif client.total_spent >= 10000:
                score += 10
            elif client.total_spent >= 1000:
                score += 5
            elif client.total_spent < 100:
                score -= 5
        
        # Hire rate
        if client.hire_rate:
            if client.hire_rate >= 80:
                score += 10
            elif client.hire_rate >= 50:
                score += 5
            elif client.hire_rate < 30:
                score -= 10
        
        return max(0, min(100, score))
    
    def _score_job_clarity(self, job: JobPosting) -> float:
        """Score based on how clear and well-defined the job is"""
        description = job.description
        score = 50  # Base score
        
        # Longer descriptions usually mean clearer requirements
        word_count = len(description.split())
        if word_count >= 200:
            score += 20
        elif word_count >= 100:
            score += 10
        elif word_count < 30:
            score -= 15
        
        # Look for positive indicators
        positive_keywords = [
            "requirements", "deliverables", "deadline", "milestone",
            "experience", "skills", "must have", "looking for",
            "project", "develop", "build", "create"
        ]
        description_lower = description.lower()
        for keyword in positive_keywords:
            if keyword in description_lower:
                score += 3
        
        # Look for negative indicators
        negative_keywords = [
            "asap", "urgent", "cheap", "lowest bid", "budget is tight",
            "test task", "unpaid", "free trial"
        ]
        for keyword in negative_keywords:
            if keyword in description_lower:
                score -= 10
        
        return max(0, min(100, score))
    
    def _score_competition(self, job: JobPosting) -> float:
        """Score based on competition level (fewer proposals = better)"""
        proposals = job.proposals_count
        
        if proposals == 0:
            return 100  # No competition yet
        elif proposals <= 5:
            return 90
        elif proposals <= 10:
            return 75
        elif proposals <= 20:
            return 60
        elif proposals <= 35:
            return 40
        elif proposals <= 50:
            return 25
        else:
            return 10  # Very high competition
    
    def _score_recency(self, job: JobPosting) -> float:
        """Score based on how recently the job was posted"""
        if not job.posted_at:
            return 50  # Unknown posting time
        
        hours_ago = (datetime.now() - job.posted_at).total_seconds() / 3600
        
        if hours_ago <= 1:
            return 100
        elif hours_ago <= 3:
            return 90
        elif hours_ago <= 6:
            return 80
        elif hours_ago <= 12:
            return 70
        elif hours_ago <= 24:
            return 60
        elif hours_ago <= 48:
            return 40
        elif hours_ago <= 72:
            return 25
        else:
            return 10
    
    def get_qualifying_jobs(self, jobs: list[JobPosting]) -> list[RankedJob]:
        """Get only jobs that meet the threshold"""
        ranked = self.rank_jobs(jobs)
        return [rj for rj in ranked if rj.meets_threshold]
    
    def explain_score(self, ranked_job: RankedJob) -> str:
        """Generate a human-readable explanation of the score"""
        breakdown = ranked_job.score_breakdown
        lines = [
            f"Overall Score: {ranked_job.score}/100",
            f"Threshold: {self.ranking_config.threshold}",
            f"Qualifies: {'Yes' if ranked_job.meets_threshold else 'No'}",
            "",
            "Score Breakdown:",
        ]
        
        component_names = {
            "skills_match": "Skills Match",
            "budget_score": "Budget",
            "client_quality": "Client Quality", 
            "job_clarity": "Job Clarity",
            "competition": "Competition",
            "recency": "Recency"
        }
        
        for key, score in breakdown.items():
            weight = getattr(self.weights, key)
            weighted = round(score * weight, 2)
            name = component_names.get(key, key)
            lines.append(f"  {name}: {score}/100 (weight: {weight}, contribution: {weighted})")
        
        return "\n".join(lines)

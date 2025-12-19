"""AI Engine for job ranking and proposal generation"""
import asyncio
import json
from typing import Optional

import httpx

from .config import get_config, get_credentials
from .models import JobPosting, RankedJob
from .logger import get_logger

logger = get_logger()


class AIEngine:
    """AI-powered ranking and proposal generation using OpenAI or compatible APIs"""
    
    def __init__(self):
        self.config = get_config()
        self.credentials = get_credentials()
        self.ai_config = self.config.ai
        
        # API configuration
        self.api_key = self.credentials.openai_api_key
        self.base_url = self.ai_config.base_url
        self.model = self.ai_config.model
        
        if not self.api_key:
            logger.warning("OpenAI API key not configured. AI features will be disabled.")
    
    @property
    def is_available(self) -> bool:
        """Check if AI engine is configured and available"""
        return bool(self.api_key) and self.ai_config.enabled
    
    async def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> Optional[str]:
        """Make a call to the LLM API"""
        if not self.is_available:
            return None
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": temperature,
                        "max_tokens": self.ai_config.max_tokens
                    }
                )
                
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
                
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            return None
    
    async def rank_jobs_parallel(self, jobs: list[JobPosting], my_skills: list[str], 
                                   my_experience: str, max_concurrent: int = 5) -> list[dict]:
        """
        Rank multiple jobs in parallel for efficiency.
        Uses semaphore to limit concurrent API calls.
        """
        if not self.is_available:
            return [{"score": 50, "reasoning": "AI not available", "ai_ranked": False} for _ in jobs]
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def rank_with_limit(job: JobPosting) -> dict:
            async with semaphore:
                return await self.rank_job(job, my_skills, my_experience)
        
        # Run all rankings concurrently (limited by semaphore)
        results = await asyncio.gather(
            *[rank_with_limit(job) for job in jobs],
            return_exceptions=True
        )
        
        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Parallel ranking failed for job {i}: {result}")
                processed_results.append({"score": 50, "reasoning": str(result), "ai_ranked": False})
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def rank_jobs_batch(self, jobs: list[JobPosting], my_skills: list[str], 
                              my_experience: str, batch_size: int = 5) -> list[dict]:
        """
        Rank multiple jobs in a single API call (batch mode).
        More token-efficient but requires larger context window.
        """
        if not self.is_available or not jobs:
            return [{"score": 50, "reasoning": "AI not available", "ai_ranked": False} for _ in jobs]
        
        results = []
        
        # Process in batches
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            batch_results = await self._rank_batch(batch, my_skills, my_experience)
            results.extend(batch_results)
        
        return results
    
    async def _rank_batch(self, jobs: list[JobPosting], my_skills: list[str], 
                          my_experience: str) -> list[dict]:
        """Rank a batch of jobs in a single API call"""
        system_prompt = """You are an expert freelancer consultant. Analyze multiple job postings and rank each one.

Respond with a JSON array containing one object per job in the same order as provided:
[
  {"job_index": 0, "score": 75, "reasoning": "...", "strengths": [...], "concerns": [...], "recommendation": "pursue"},
  {"job_index": 1, "score": 45, "reasoning": "...", "strengths": [...], "concerns": [...], "recommendation": "skip"},
  ...
]

Scoring: 80-100 excellent match, 60-79 good, 40-59 moderate, 0-39 poor."""
        
        # Build batch prompt
        jobs_text = "\n\n---\n\n".join([
            f"**JOB {i}:**\nTitle: {job.title}\nType: {job.job_type}\nBudget: {self._format_budget(job)}\nSkills: {', '.join(job.required_skills)}\nProposals: {job.proposals_count}\nClient Rating: {job.client.rating or 'N/A'}\nClient Spent: ${job.client.total_spent or 0}\n\nDescription:\n{job.description[:500]}..."
            for i, job in enumerate(jobs)
        ])
        
        user_prompt = f"""Analyze these {len(jobs)} jobs for a freelancer with:

**Skills:** {', '.join(my_skills)}
**Experience:** {my_experience}

{jobs_text}

Provide rankings for all {len(jobs)} jobs as a JSON array."""
        
        try:
            response = await self._call_llm(system_prompt, user_prompt, temperature=0.3)
            
            if not response:
                return [{"score": 50, "reasoning": "No response", "ai_ranked": False} for _ in jobs]
            
            # Parse batch response
            return self._parse_batch_response(response, len(jobs))
            
        except Exception as e:
            logger.error(f"Batch ranking failed: {e}")
            return [{"score": 50, "reasoning": str(e), "ai_ranked": False} for _ in jobs]
    
    def _parse_batch_response(self, response: str, expected_count: int) -> list[dict]:
        """Parse batch ranking response"""
        try:
            # Extract JSON array
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                # Try to find array in response
                start = response.find('[')
                end = response.rfind(']') + 1
                json_str = response[start:end] if start != -1 else response
            
            data = json.loads(json_str.strip())
            
            if not isinstance(data, list):
                raise ValueError("Expected JSON array")
            
            results = []
            for item in data:
                results.append({
                    "score": min(100, max(0, int(item.get("score", 50)))),
                    "reasoning": item.get("reasoning", ""),
                    "strengths": item.get("strengths", []),
                    "concerns": item.get("concerns", []),
                    "recommendation": item.get("recommendation", ""),
                    "ai_ranked": True
                })
            
            # Pad if we got fewer results
            while len(results) < expected_count:
                results.append({"score": 50, "reasoning": "Missing from batch", "ai_ranked": False})
            
            return results[:expected_count]
            
        except Exception as e:
            logger.error(f"Failed to parse batch response: {e}")
            return [{"score": 50, "reasoning": str(e), "ai_ranked": False} for _ in range(expected_count)]
    
    async def rank_job(self, job: JobPosting, my_skills: list[str], my_experience: str) -> dict:
        """
        Use AI to analyze and rank a single job posting.
        Returns a dict with score (0-100) and reasoning.
        """
        if not self.is_available:
            return {"score": 50, "reasoning": "AI not available", "ai_ranked": False}
        
        system_prompt = self.ai_config.ranking_system_prompt
        
        user_prompt = self.ai_config.ranking_user_prompt.format(
            job_title=job.title,
            job_description=job.description,
            required_skills=", ".join(job.required_skills),
            job_type=job.job_type,
            budget_info=self._format_budget(job),
            client_rating=job.client.rating or "Unknown",
            client_spent=job.client.total_spent or 0,
            proposals_count=job.proposals_count,
            my_skills=", ".join(my_skills),
            my_experience=my_experience
        )
        
        try:
            response = await self._call_llm(system_prompt, user_prompt, temperature=0.3)
            
            if not response:
                return {"score": 50, "reasoning": "No AI response", "ai_ranked": False}
            
            # Parse the response - expect JSON
            result = self._parse_ranking_response(response)
            result["ai_ranked"] = True
            return result
            
        except Exception as e:
            logger.error(f"AI ranking failed: {e}")
            return {"score": 50, "reasoning": str(e), "ai_ranked": False}
    
    def _parse_ranking_response(self, response: str) -> dict:
        """Parse the AI ranking response"""
        try:
            # Try to extract JSON from the response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response
            
            data = json.loads(json_str.strip())
            return {
                "score": min(100, max(0, int(data.get("score", 50)))),
                "reasoning": data.get("reasoning", ""),
                "strengths": data.get("strengths", []),
                "concerns": data.get("concerns", []),
                "recommendation": data.get("recommendation", "")
            }
        except json.JSONDecodeError:
            # If not JSON, try to extract score from text
            import re
            score_match = re.search(r'score[:\s]+(\d+)', response.lower())
            score = int(score_match.group(1)) if score_match else 50
            return {
                "score": min(100, max(0, score)),
                "reasoning": response[:500]
            }
    
    async def generate_proposal(self, job: JobPosting, my_skills: list[str], 
                                my_experience: str, ranking_info: dict) -> str:
        """
        Use AI to generate a personalized proposal for a job.
        """
        if not self.is_available:
            return self._generate_fallback_proposal(job, my_skills)
        
        system_prompt = self.ai_config.proposal_system_prompt
        
        user_prompt = self.ai_config.proposal_user_prompt.format(
            job_title=job.title,
            job_description=job.description,
            required_skills=", ".join(job.required_skills),
            job_type=job.job_type,
            budget_info=self._format_budget(job),
            my_skills=", ".join(my_skills),
            my_experience=my_experience,
            ranking_score=ranking_info.get("score", "N/A"),
            ranking_reasoning=ranking_info.get("reasoning", ""),
            matching_strengths=", ".join(ranking_info.get("strengths", []))
        )
        
        try:
            response = await self._call_llm(system_prompt, user_prompt, temperature=0.7)
            
            if not response:
                return self._generate_fallback_proposal(job, my_skills)
            
            return response
            
        except Exception as e:
            logger.error(f"AI proposal generation failed: {e}")
            return self._generate_fallback_proposal(job, my_skills)
    
    def _format_budget(self, job: JobPosting) -> str:
        """Format budget information for prompts"""
        if job.job_type == "hourly":
            if job.budget_min and job.budget_max:
                return f"${job.budget_min}-${job.budget_max}/hr"
            return "Hourly rate not specified"
        else:
            if job.fixed_price:
                return f"${job.fixed_price} fixed"
            return "Budget not specified"
    
    def _generate_fallback_proposal(self, job: JobPosting, my_skills: list[str]) -> str:
        """Generate a basic proposal when AI is not available"""
        matching = [s for s in my_skills if s.lower() in job.description.lower()]
        
        return f"""Hi,

I'm interested in your project "{job.title}".

{"I have experience with " + ", ".join(matching[:3]) + " which aligns with your requirements." if matching else ""}

I'd love to discuss this project in more detail and understand your specific needs.

Best regards"""


class AIRankedJob(RankedJob):
    """Extended RankedJob with AI analysis"""
    ai_score: Optional[float] = None
    ai_reasoning: Optional[str] = None
    ai_strengths: list[str] = []
    ai_concerns: list[str] = []
    ai_recommendation: Optional[str] = None

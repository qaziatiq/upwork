"""Data models for Upwork jobs and proposals"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ClientInfo(BaseModel):
    """Information about the job poster"""
    name: Optional[str] = None
    country: Optional[str] = None
    jobs_posted: int = 0
    hire_rate: float = 0.0
    total_spent: float = 0.0
    avg_hourly_rate: Optional[float] = None
    payment_verified: bool = False
    rating: Optional[float] = None
    reviews_count: int = 0


class JobPosting(BaseModel):
    """Represents an Upwork job posting"""
    id: str
    title: str
    description: str
    url: str
    posted_at: Optional[datetime] = None
    
    # Job details
    job_type: str = "fixed"  # "hourly" or "fixed"
    experience_level: str = "intermediate"
    duration: Optional[str] = None
    
    # Budget
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    fixed_price: Optional[float] = None
    
    # Skills
    required_skills: list[str] = Field(default_factory=list)
    
    # Competition
    proposals_count: int = 0
    interviewing_count: int = 0
    invites_sent: int = 0
    
    # Client info
    client: ClientInfo = Field(default_factory=ClientInfo)
    
    # Computed fields
    score: float = 0.0
    score_breakdown: dict = Field(default_factory=dict)


class RankedJob(BaseModel):
    """A job with its ranking score"""
    job: JobPosting
    score: float
    score_breakdown: dict
    meets_threshold: bool


class Proposal(BaseModel):
    """Generated proposal for a job"""
    job: JobPosting
    content: str
    generated_at: datetime = Field(default_factory=datetime.now)
    file_path: Optional[str] = None

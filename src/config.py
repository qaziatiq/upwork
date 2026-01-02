"""Configuration management for Upwork Automation"""
import os
from pathlib import Path
from typing import Optional, List

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv


class SchedulerConfig(BaseModel):
    interval_minutes: int = 60
    active_hours: Optional[dict] = None
    timezone: str = "UTC"


class BudgetConfig(BaseModel):
    min_hourly: float = 0
    max_hourly: float = 1000
    min_fixed: float = 0
    max_fixed: float = 100000


class ClientHistoryConfig(BaseModel):
    min_jobs_posted: int = 0
    min_hire_rate: float = 0
    min_total_spent: float = 0


class SearchConfig(BaseModel):
    keywords: list[str] = []
    category: Optional[str] = None
    experience_levels: list[str] = ["intermediate", "expert"]
    job_types: list[str] = ["hourly", "fixed"]
    client_history: ClientHistoryConfig = ClientHistoryConfig()
    budget: BudgetConfig = BudgetConfig()
    posted_within_hours: int = 24
    max_results: int = 20


# New class for search profiles
class SearchProfileConfig(SearchConfig):
    name: str = ""
    enabled: bool = True


class RankingWeights(BaseModel):
    skills_match: float = 0.25
    budget_score: float = 0.20
    client_quality: float = 0.20
    job_clarity: float = 0.15
    competition: float = 0.10
    recency: float = 0.10


class RankingConfig(BaseModel):
    threshold: int = 60
    weights: RankingWeights = RankingWeights()
    my_skills: list[str] = []


class ProposalConfig(BaseModel):
    template: str = "templates/default_proposal.j2"
    output_directory: str = "proposals"
    include_job_details: bool = True
    max_proposals_per_run: int = 5


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "logs/upwork_automation.log"
    max_size_mb: int = 10
    backup_count: int = 5


class AIConfig(BaseModel):
    enabled: bool = True
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    max_tokens: int = 2000
    ranking_mode: str = "parallel"  # parallel, batch, or sequential
    max_concurrent: int = 5
    batch_size: int = 5
    my_experience: str = ""
    ranking_system_prompt: str = ""
    ranking_user_prompt: str = ""
    proposal_system_prompt: str = ""
    proposal_user_prompt: str = ""


class AppConfig(BaseModel):
    scheduler: SchedulerConfig = SchedulerConfig()
    search: SearchConfig = SearchConfig()
    search_profiles: List[SearchProfileConfig] = []  # New field for search profiles
    ranking: RankingConfig = RankingConfig()
    proposal: ProposalConfig = ProposalConfig()
    logging: LoggingConfig = LoggingConfig()
    ai: AIConfig = AIConfig()


class Credentials(BaseSettings):
    """Environment-based credentials"""
    upwork_username: str = Field(default="", alias="UPWORK_USERNAME")
    upwork_password: str = Field(default="", alias="UPWORK_PASSWORD")
    upwork_security_answer: str = Field(default="", alias="UPWORK_SECURITY_ANSWER")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_project_root() -> Path:
    """Get the project root directory"""
    return Path(__file__).parent.parent


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from YAML file"""
    if config_path is None:
        config_path = get_project_root() / "config" / "config.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, "r") as f:
        config_dict = yaml.safe_load(f)
    
    return AppConfig(**config_dict)


def load_credentials() -> Credentials:
    """Load credentials from environment"""
    env_path = get_project_root() / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    return Credentials()


# Global instances
_config: Optional[AppConfig] = None
_credentials: Optional[Credentials] = None


def get_config() -> AppConfig:
    """Get the global configuration instance"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_credentials() -> Credentials:
    """Get the global credentials instance"""
    global _credentials
    if _credentials is None:
        _credentials = load_credentials()
    return _credentials

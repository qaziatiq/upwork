"""Proposal generation and storage for Upwork automation"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, Template

from .config import get_config, get_project_root
from .models import JobPosting, RankedJob, Proposal
from .logger import get_logger

logger = get_logger()


class ProposalGenerator:
    """Generates and saves proposals for qualifying jobs"""
    
    def __init__(self):
        self.config = get_config()
        self.proposal_config = self.config.proposal
        
        # Set up output directory
        self.output_dir = get_project_root() / self.proposal_config.output_directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up Jinja2 environment
        templates_dir = get_project_root() / "templates"
        templates_dir.mkdir(exist_ok=True)
        
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False
        )
    
    def generate_proposal(self, ranked_job: RankedJob) -> Proposal:
        """Generate a proposal for a job"""
        job = ranked_job.job
        logger.info(f"Generating proposal for: {job.title}")
        
        # Try to load template
        try:
            template_name = Path(self.proposal_config.template).name
            template = self.jinja_env.get_template(template_name)
        except Exception as e:
            logger.warning(f"Could not load template {template_name}, using default: {e}")
            template = self._get_default_template()
        
        # Prepare template context
        context = {
            "job": job,
            "ranked_job": ranked_job,
            "score": ranked_job.score,
            "score_breakdown": ranked_job.score_breakdown,
            "my_skills": self.config.ranking.my_skills,
            "matching_skills": self._get_matching_skills(job),
            "generated_at": datetime.now(),
        }
        
        # Render the proposal
        content = template.render(**context)
        
        proposal = Proposal(
            job=job,
            content=content,
            generated_at=datetime.now()
        )
        
        return proposal
    
    def _get_matching_skills(self, job: JobPosting) -> list[str]:
        """Get skills that match between job and your skills"""
        my_skills = [s.lower() for s in self.config.ranking.my_skills]
        job_skills = [s.lower() for s in job.required_skills]
        description_lower = job.description.lower()
        
        matching = []
        for skill in my_skills:
            if any(skill in js or js in skill for js in job_skills):
                matching.append(skill)
            elif skill in description_lower:
                matching.append(skill)
        
        return list(set(matching))
    
    def _get_default_template(self) -> Template:
        """Get the default proposal template"""
        default_template = """
# Proposal for: {{ job.title }}

## Job Details
- **URL**: {{ job.url }}
- **Type**: {{ job.job_type }}
{% if job.job_type == 'hourly' and job.budget_min %}
- **Rate**: ${{ job.budget_min }} - ${{ job.budget_max }}/hr
{% elif job.fixed_price %}
- **Budget**: ${{ job.fixed_price }}
{% endif %}
- **Posted**: {{ job.posted_at.strftime('%Y-%m-%d %H:%M') if job.posted_at else 'Unknown' }}
- **Proposals**: {{ job.proposals_count }}
- **Required Skills**: {{ job.required_skills | join(', ') }}

## Client Info
- **Payment Verified**: {{ 'Yes' if job.client.payment_verified else 'No' }}
- **Total Spent**: ${{ job.client.total_spent | default(0) | round(2) }}
- **Rating**: {{ job.client.rating | default('N/A') }}
- **Country**: {{ job.client.country | default('Unknown') }}

## Job Score: {{ score }}/100
{% for key, value in score_breakdown.items() %}
- {{ key }}: {{ value }}/100
{% endfor %}

## My Matching Skills
{{ matching_skills | join(', ') if matching_skills else 'No direct skill matches identified' }}

---

## Job Description
{{ job.description }}

---

## Proposal Draft

Hello,

I came across your project and I'm very interested in helping you with this.

{% if matching_skills %}
I have extensive experience with {{ matching_skills[:3] | join(', ') }}, which aligns well with your requirements.
{% endif %}

[Customize this section based on the specific job requirements]

**What I can offer:**
- [Specific solution approach]
- [Relevant experience or portfolio item]
- [Timeline/availability]

**Questions for you:**
- [Clarifying question about the project]

I'd love to discuss this project in more detail. Looking forward to hearing from you!

Best regards,
[Your Name]

---
Generated: {{ generated_at.strftime('%Y-%m-%d %H:%M:%S') }}
"""
        return Template(default_template)
    
    def save_proposal(self, proposal: Proposal) -> str:
        """Save a proposal to a file and return the file path"""
        job = proposal.job
        
        # Create a safe filename
        safe_title = re.sub(r'[^\w\s-]', '', job.title)[:50]
        safe_title = re.sub(r'[-\s]+', '-', safe_title).strip('-')
        
        timestamp = proposal.generated_at.strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{safe_title}.md"
        
        # Create date-based subdirectory
        date_dir = self.output_dir / proposal.generated_at.strftime('%Y-%m-%d')
        date_dir.mkdir(exist_ok=True)
        
        file_path = date_dir / filename
        
        # Write the proposal
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(proposal.content)
        
        proposal.file_path = str(file_path)
        logger.info(f"Saved proposal to: {file_path}")
        
        return str(file_path)
    
    def generate_and_save(self, ranked_job: RankedJob) -> Proposal:
        """Generate a proposal and save it to disk"""
        proposal = self.generate_proposal(ranked_job)
        self.save_proposal(proposal)
        return proposal
    
    def process_jobs(self, ranked_jobs: list[RankedJob]) -> list[Proposal]:
        """Process a list of ranked jobs, generating proposals for qualifying ones"""
        proposals = []
        max_proposals = self.proposal_config.max_proposals_per_run
        
        qualifying_jobs = [rj for rj in ranked_jobs if rj.meets_threshold]
        logger.info(f"Found {len(qualifying_jobs)} jobs meeting threshold out of {len(ranked_jobs)} total")
        
        for i, ranked_job in enumerate(qualifying_jobs[:max_proposals]):
            try:
                proposal = self.generate_and_save(ranked_job)
                proposals.append(proposal)
                logger.info(f"Generated proposal {i+1}/{min(len(qualifying_jobs), max_proposals)}: {ranked_job.job.title}")
            except Exception as e:
                logger.error(f"Error generating proposal for {ranked_job.job.title}: {e}")
                continue
        
        return proposals

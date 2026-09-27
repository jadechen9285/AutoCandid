import asyncio
import httpx
import re
import html
from typing import List, Dict, Any
from pydantic import BaseModel, HttpUrl, Field, ValidationError
from datetime import datetime, timezone

# ============================================================================
# 1. STRICT DATA CONTRACTS (Pydantic)
# ============================================================================
class JobPosting(BaseModel):
    source: str = "greenhouse_api"
    external_id: str
    title: str
    company: str
    description: str
    location: str
    url: HttpUrl
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============================================================================
# 2. API EXTRACTION ENGINE
# ============================================================================
class GreenhouseIngestor:
    def __init__(self, company_board_token: str):
        """
        company_board_token: The internal Greenhouse slug (e.g., 'discord', 'openai')
        """
        self.company_token = company_board_token
        # content=true tells Greenhouse to include the actual job description text
        self.api_url = f"https://boards-api.greenhouse.io/v1/boards/{self.company_token}/jobs?content=true"

    def _clean_html(self, raw_html: str) -> str:
        """Strips HTML tags and decodes entities (e.g., &nbsp;) for the LLM."""
        if not raw_html:
            return "No description provided."
        # Remove HTML tags using regex
        text = re.sub(r'<[^>]+>', ' ', raw_html)
        # Decode HTML entities
        text = html.unescape(text)
        # Collapse multiple spaces/newlines into single spaces
        return " ".join(text.split())

    async def fetch_active_jobs(self) -> List[JobPosting]:
        print(f"[*] Fetching live jobs for '{self.company_token}' from Greenhouse API...")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self.api_url)
            response.raise_for_status()
            
            payload = response.json()
            jobs_data = payload.get("jobs", [])
            
            validated_jobs = []
            for job in jobs_data:
                try:
                    # Map the raw Greenhouse JSON schema to our strict Pipeline schema
                    posting = JobPosting(
                        external_id=str(job.get("id")),
                        title=job.get("title", ""),
                        company=self.company_token.upper(),
                        description=self._clean_html(job.get("content", "")),
                        location=job.get("location", {}).get("name", "Remote / Unspecified"),
                        url=job.get("absolute_url")
                    )
                    validated_jobs.append(posting)
                except ValidationError as e:
                    print(f"[-] Dropped job {job.get('id')} due to missing fields.")
                    
            print(f"[+] Successfully validated and ingested {len(validated_jobs)}/{len(jobs_data)} jobs.")
            return validated_jobs


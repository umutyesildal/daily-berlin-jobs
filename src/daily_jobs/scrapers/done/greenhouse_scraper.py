"""
Greenhouse ATS Scraper - API-based
Scrapes job listings from Greenhouse API
"""

import requests
import logging
from typing import List, Dict
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _office_berlin_location(office: dict) -> str:
    office_name = str(office.get('name') or '')
    office_location = office.get('location') or ''
    if isinstance(office_location, dict):
        office_location = office_location.get('name') or office_location.get('location') or ''
    office_location = str(office_location)
    if 'berlin' in office_location.casefold():
        return office_location
    if 'berlin' in office_name.casefold():
        return office_name
    return ''


class GreenhouseScraper:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def scrape_jobs(self, url: str, company_name: str, company_description: str = '', label: str = '') -> List[Dict]:
        """
        Scrape jobs from Greenhouse API
        
        Args:
            url: Greenhouse career page URL (e.g., https://boards.greenhouse.io/cultureamp)
                 or direct API URL (e.g., https://boards-api.greenhouse.io/v1/boards/company/jobs?content=true)
            company_name: Name of the company
            company_description: Description of the company
            label: Company label/category
            
        Returns:
            List of job dictionaries
        """
        jobs = []
        
        try:
            # Check if URL is already an API URL
            if 'boards-api.greenhouse.io' in url:
                api_url = url
            else:
                # Extract company slug from URL (e.g., "cultureamp" from https://boards.greenhouse.io/cultureamp)
                company_slug = url.rstrip('/').split('/')[-1]
                # Construct API URL
                api_url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"
            
            response = self.session.get(api_url, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            for job_data in data.get('jobs', []):
                try:
                    # Get location name
                    location = job_data.get('location', {})
                    location_name = (
                        str(location.get('name') or '')
                        if isinstance(location, dict)
                        else str(location or '')
                    )
                    
                    # Get departments
                    departments = job_data.get('departments', [])
                    department = departments[0].get('name', '') if departments else ''
                    
                    # Get offices
                    offices = job_data.get('offices') or []
                    office_names = ', '.join(
                        str(office.get('name') or '') for office in offices if isinstance(office, dict)
                    ) if offices else location_name
                    base_location = location_name or office_names
                    location_value = base_location
                    if 'berlin' not in base_location.casefold():
                        berlin_location = ''
                        for office in offices:
                            if isinstance(office, dict):
                                berlin_location = _office_berlin_location(office)
                                if berlin_location:
                                    break
                        if berlin_location:
                            location_value = f'{base_location} / {berlin_location}' if base_location else berlin_location
                    
                    # Clean HTML content
                    content_html = job_data.get('content', '')
                    content_plain = BeautifulSoup(content_html, 'html.parser').get_text(separator=' ', strip=True) if content_html else ''
                    
                    job = {
                        'Company Name': company_name,
                        'Job Title': job_data.get('title', ''),
                        'Location': location_value,
                        'Job Link': job_data.get('absolute_url', ''),
                        'Job Description': content_plain,
                        'Employment Type': '',  # Greenhouse doesn't provide this in API
                        'Department': department,
                        'Posted Date': job_data.get('first_published', '').split('T')[0] if job_data.get('first_published') else '',
                        'Company Description': company_description,
                        'Remote': 'Yes' if 'remote' in location_name.lower() else 'No',
                        'Label': label,
                        'ATS': 'Greenhouse'
                    }
                    jobs.append(job)
                except Exception as e:
                    continue
            
        except Exception as e:
            pass
        
        return jobs

from __future__ import annotations

import logging
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
JOB_PATH = re.compile(r"/forto-jobs/[^/?#]+-[0-9a-f-]{36}/?$", re.IGNORECASE)


def parse_forto_listing(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    seen = set()
    for anchor in soup.find_all("a", href=JOB_PATH):
        card = anchor.find_parent("li", class_=re.compile(r"\blist-item\b"))
        if not card:
            continue
        title = card.select_one("p.title") or card.find(["h2", "h3", "h4"])
        columns = card.select(".list-item-column")
        department = columns[1].get_text(" ", strip=True) if len(columns) > 1 else ""
        employment_type = columns[2].get_text(" ", strip=True) if len(columns) > 2 else ""
        location_element = card.select_one(".list-item-location")
        location = location_element.get_text(" ", strip=True) if location_element else ""
        job_link = urljoin(base_url, anchor.get("href", ""))
        if not title or job_link in seen:
            continue
        seen.add(job_link)
        jobs.append({
            "title": title.get_text(" ", strip=True),
            "url": job_link,
            "location": location,
            "department": department,
            "employment_type": employment_type,
        })
    return jobs


def parse_forto_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    text = main.get_text(" ", strip=True)
    title = soup.find("h1")
    location_match = re.search(r"\bLocation\s+(.+?)\s+Department\b", text, re.IGNORECASE)
    department_match = re.search(r"\bDepartment\s+(.+?)\s+Employment Type\b", text, re.IGNORECASE)
    employment_match = re.search(r"\bEmployment Type\s+(.+?)\s+Overview\b", text, re.IGNORECASE)

    description_element = soup.select_one(
        '[class*="job-description"], [class*="jobDescription"], [class*="job-overview"], article'
    )
    description = (
        description_element.get_text(" ", strip=True)
        if description_element
        else text
    )
    return {
        "title": title.get_text(" ", strip=True) if title else "",
        "location": location_match.group(1).strip() if location_match else "",
        "department": department_match.group(1).strip() if department_match else "",
        "employment_type": employment_match.group(1).strip() if employment_match else "",
        "description": description,
    }


class FortoScraper:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

    def scrape_jobs(
        self,
        url: str,
        company_name: str = "Forto",
        company_description: str = "",
        label: str = "",
    ) -> list[dict]:
        try:
            response = self.session.get(url, timeout=25)
            if response.status_code == 403:
                logger.warning("Forto returned HTTP 403 for %s", url)
                return []
            response.raise_for_status()
            listings = parse_forto_listing(response.text, response.url)
        except requests.RequestException as error:
            logger.warning("Forto listing request failed (%s)", type(error).__name__)
            return []

        jobs = []
        if listings and self.delay:
            time.sleep(self.delay)
        for listing in listings:
            try:
                detail_response = self.session.get(listing["url"], timeout=25)
                if detail_response.status_code == 403:
                    logger.warning("Forto detail returned HTTP 403 for %s", url)
                    detail = {}
                else:
                    detail_response.raise_for_status()
                    detail = parse_forto_detail(detail_response.text)
            except requests.RequestException as error:
                logger.debug("Forto detail request failed (%s)", type(error).__name__)
                detail = {}
            finally:
                if self.delay:
                    time.sleep(self.delay)

            location = str(detail.get("location") or listing["location"])
            if "berlin" not in location.casefold():
                continue
            jobs.append({
                "Company Name": company_name,
                "Job Title": str(detail.get("title") or listing["title"]),
                "Location": location,
                "Job Link": listing["url"],
                "Job Description": str(detail.get("description") or ""),
                "Employment Type": str(detail.get("employment_type") or listing["employment_type"]),
                "Department": str(detail.get("department") or listing["department"]),
                "Posted Date": "",
                "Company Description": company_description,
                "Remote": "Hybrid" if "hybrid" in location.casefold() else "No",
                "Label": label,
                "ATS": "Forto",
            })
        return jobs

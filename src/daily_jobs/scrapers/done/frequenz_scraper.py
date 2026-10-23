from __future__ import annotations

import logging
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
JOB_PATH = re.compile(r"/careers/[^/?#]+/?$", re.IGNORECASE)


def parse_frequenz_listing(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    seen = set()
    for anchor in soup.find_all("a", href=JOB_PATH):
        job_link = urljoin(base_url, anchor.get("href", ""))
        if job_link in seen:
            continue
        seen.add(job_link)
        title = anchor.find(["h1", "h2", "h3", "h4", "h5"])
        title_text = title.get_text(" ", strip=True) if title else anchor.get_text(" ", strip=True)
        if title_text:
            jobs.append({"title": title_text, "url": job_link})
    return jobs


def parse_frequenz_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("div.main") or soup.find("main") or soup.body or soup
    text = main.get_text(" ", strip=True)
    title = soup.find("h1")
    location_match = re.search(
        r"Hiring location\s+(.+?)\s+About\s+Frequenz\b",
        text,
        re.IGNORECASE,
    )
    location = location_match.group(1).strip() if location_match else ""
    if not location:
        top_location = re.search(
            r"\b(Berlin(?:\s*/\s*Hybrid possible)?|Hybrid possible)\s+"
            r"(?:Full[- ]time|Part[- ]time|Contract)\b",
            text,
            re.IGNORECASE,
        )
        location = top_location.group(1).strip() if top_location else ""

    employment_match = re.search(
        r"\b(Full[- ]time|Part[- ]time|Contract)\b",
        text,
        re.IGNORECASE,
    )
    department_match = re.search(
        r"\b(?:Full[- ]time|Part[- ]time|Contract)\s+(.+?)\s+Job role insights\b",
        text,
        re.IGNORECASE,
    )
    posted_match = re.search(
        r"Date posted\s+(.+?)\s+Level\b",
        text,
        re.IGNORECASE,
    )
    description = " ".join(
        section.get_text(" ", strip=True)
        for section in main.find_all(["p", "li"])
        if section.get_text(" ", strip=True)
    )
    return {
        "title": title.get_text(" ", strip=True) if title else "",
        "location": location,
        "employment_type": employment_match.group(1) if employment_match else "",
        "department": department_match.group(1).strip() if department_match else "",
        "posted_date": posted_match.group(1).strip() if posted_match else "",
        "description": description or text,
    }


class FrequenzScraper:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

    def scrape_jobs(
        self,
        url: str,
        company_name: str = "Frequenz",
        company_description: str = "",
        label: str = "",
    ) -> list[dict]:
        try:
            response = self.session.get(url, timeout=25)
            if response.status_code == 403:
                logger.warning("Frequenz returned HTTP 403 for %s", url)
                return []
            response.raise_for_status()
            listings = parse_frequenz_listing(response.text, response.url)
        except requests.RequestException as error:
            logger.warning("Frequenz listing request failed (%s)", type(error).__name__)
            return []

        jobs = []
        if listings and self.delay:
            time.sleep(self.delay)
        seen = set()
        for listing in listings:
            if listing["url"] in seen:
                continue
            seen.add(listing["url"])
            try:
                detail_response = self.session.get(listing["url"], timeout=25)
                if detail_response.status_code == 403:
                    logger.warning("Frequenz detail returned HTTP 403 for %s", url)
                    detail = {}
                else:
                    detail_response.raise_for_status()
                    detail = parse_frequenz_detail(detail_response.text)
            except requests.RequestException as error:
                logger.debug("Frequenz detail request failed (%s)", type(error).__name__)
                detail = {}
            finally:
                if self.delay:
                    time.sleep(self.delay)

            location = str(detail.get("location") or "")
            if "berlin" not in location.casefold():
                continue
            jobs.append({
                "Company Name": company_name,
                "Job Title": str(detail.get("title") or listing["title"]),
                "Location": location,
                "Job Link": listing["url"],
                "Job Description": str(detail.get("description") or ""),
                "Employment Type": str(detail.get("employment_type") or ""),
                "Department": str(detail.get("department") or ""),
                "Posted Date": str(detail.get("posted_date") or ""),
                "Company Description": company_description,
                "Remote": "Hybrid" if "hybrid" in location.casefold() else "No",
                "Label": label,
                "ATS": "Frequenz",
            })
        return jobs

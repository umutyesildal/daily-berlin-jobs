from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _feed_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    if path.endswith(".rss"):
        path = path[:-4]
    if path.endswith(".json"):
        feed_path = path
    elif path.endswith("/jobs"):
        feed_path = f"{path}.json"
    else:
        feed_path = f"{path}/jobs.json" if path else "/jobs.json"
    return urlunsplit((parts.scheme or "https", parts.netloc, feed_path, "", ""))


def _location_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _location_values(child)]
    if isinstance(value, dict):
        address = value.get("address")
        if isinstance(address, dict):
            fields = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            formatted = ", ".join(str(part).strip() for part in fields if part)
            if formatted:
                return [formatted]
        for key in ("name", "location", "addressLocality", "city", "label"):
            nested = _location_values(value.get(key))
            if nested:
                return nested
    return []


def _plain_text(value: Any) -> str:
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(separator=" ", strip=True)


def _remote_value(location: str, description: str) -> str:
    text = f"{location} {description}".casefold()
    if "hybrid" in text:
        return "Hybrid"
    if "remote" in text or "work from home" in text:
        return "Yes"
    return "No"


def parse_teamtailor_job(
    item: dict,
    company_name: str,
    company_description: str,
    label: str,
) -> dict:
    jobposting = item.get("_jobposting") or {}
    locations = _location_values(
        jobposting.get("jobLocation")
        or item.get("locations")
        or item.get("location")
    )
    location = " / ".join(dict.fromkeys(locations))
    description = _plain_text(item.get("content_html") or jobposting.get("description"))
    return {
        "Company Name": company_name or (jobposting.get("hiringOrganization") or {}).get("name", ""),
        "Job Title": str(item.get("title") or jobposting.get("title") or ""),
        "Location": location,
        "Job Link": str(item.get("url") or ""),
        "Job Description": description,
        "Employment Type": str(jobposting.get("employmentType") or item.get("employment_type") or ""),
        "Department": str(
            jobposting.get("occupationalCategory")
            or item.get("department")
            or ""
        ),
        "Posted Date": str(item.get("date_published") or jobposting.get("datePosted") or "")[:10],
        "Company Description": company_description,
        "Remote": _remote_value(location, description),
        "Label": label,
        "ATS": "Teamtailor",
    }


class TeamtailorScraper:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/feed+json, application/json, text/html;q=0.9, */*;q=0.8",
        })

    def _scrape_feed(
        self,
        url: str,
        company_name: str,
        company_description: str,
        label: str,
    ) -> tuple[list[dict], bool]:
        feed_url = _feed_url(url)
        jobs = []
        seen_urls = set()
        seen_feeds = set()
        has_feed = False

        while feed_url and len(jobs) < 500:
            if feed_url in seen_feeds:
                break
            seen_feeds.add(feed_url)
            response = self.session.get(feed_url, timeout=25)
            if response.status_code == 403:
                logger.warning("Teamtailor returned HTTP 403 for %s", urlsplit(feed_url).hostname)
                return [], True
            if response.status_code == 404:
                return (jobs, True) if has_feed else ([], False)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError:
                if not has_feed:
                    return [], False
                break
            if not isinstance(payload, dict):
                if not has_feed:
                    return [], False
                break
            items = payload.get("items")
            if items is None:
                items = payload.get("jobs")
            if not isinstance(items, list):
                if not has_feed:
                    return [], False
                break
            has_feed = True
            for item in items:
                if not isinstance(item, dict):
                    continue
                job = parse_teamtailor_job(item, company_name, company_description, label)
                if not job["Job Title"] or not job["Job Link"] or job["Job Link"] in seen_urls:
                    continue
                seen_urls.add(job["Job Link"])
                jobs.append(job)
                if len(jobs) >= 500:
                    break

            next_url = payload.get("next_url")
            if not next_url or len(jobs) >= 500:
                break
            candidate = urljoin(feed_url, str(next_url))
            parsed = urlsplit(candidate)
            if parsed.scheme != "https" or parsed.hostname != urlsplit(feed_url).hostname:
                logger.warning("Teamtailor returned an off-site pagination URL")
                break
            feed_url = candidate
            if self.delay:
                time.sleep(self.delay)

        return jobs, has_feed

    def _scrape_html(
        self,
        url: str,
        company_name: str,
        company_description: str,
        label: str,
    ) -> list[dict]:
        page_url = url
        seen_pages = set()
        seen_jobs = set()
        jobs = []
        while page_url and page_url not in seen_pages and len(jobs) < 500:
            seen_pages.add(page_url)
            response = self.session.get(page_url, timeout=25)
            if response.status_code == 403:
                logger.warning("Teamtailor returned HTTP 403 for %s", urlsplit(page_url).hostname)
                break
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a", href=re.compile(r"/jobs/\d+")):
                title_element = anchor.find(["h2", "h3", "h4"])
                title = title_element.get_text(" ", strip=True) if title_element else anchor.get_text(" ", strip=True)
                paragraphs = [p.get_text(" ", strip=True) for p in anchor.find_all("p")]
                location = paragraphs[1] if len(paragraphs) > 1 else ""
                job_link = urljoin(response.url, anchor.get("href", ""))
                if not title or job_link in seen_jobs:
                    continue
                seen_jobs.add(job_link)
                jobs.append({
                    "Company Name": company_name,
                    "Job Title": title,
                    "Location": location,
                    "Job Link": job_link,
                    "Job Description": "",
                    "Employment Type": "",
                    "Department": paragraphs[0] if paragraphs else "",
                    "Posted Date": "",
                    "Company Description": company_description,
                    "Remote": _remote_value(location, anchor.get_text(" ", strip=True)),
                    "Label": label,
                    "ATS": "Teamtailor",
                })
                if len(jobs) >= 500:
                    break
            next_link = soup.find(
                "a",
                href=True,
                string=re.compile(r"show\s+more|next", re.IGNORECASE),
            )
            if not next_link:
                next_link = soup.find("a", href=re.compile(r"/jobs/show_more\?page="))
            page_url = urljoin(response.url, next_link["href"]) if next_link else ""
            if page_url and self.delay:
                time.sleep(self.delay)
        return jobs

    def scrape_jobs(
        self,
        url: str,
        company_name: str = "",
        company_description: str = "",
        label: str = "",
    ) -> list[dict]:
        try:
            jobs, has_feed = self._scrape_feed(url, company_name, company_description, label)
            if has_feed:
                return jobs
            return self._scrape_html(url, company_name, company_description, label)
        except requests.RequestException as error:
            logger.warning("Teamtailor listing request failed (%s)", type(error).__name__)
            return []

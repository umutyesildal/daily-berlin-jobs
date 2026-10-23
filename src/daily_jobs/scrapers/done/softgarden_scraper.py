from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
JOB_LINK = re.compile(r"/job/\d+/", re.IGNORECASE)


def _value(card: BeautifulSoup, class_name: str) -> str:
    element = card.select_one(f".matchValue.{class_name}")
    return element.get_text(" ", strip=True) if element else ""


def parse_softgarden_listing(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('div.matchElement[id^="job_id_"]')
    jobs = []
    if cards:
        for card in cards:
            anchor = card.find("a", href=JOB_LINK)
            title = _value(card, "title") or (
                anchor.get_text(" ", strip=True) if anchor else ""
            )
            if not title or not anchor:
                continue
            locations = [
                element.get_text(" ", strip=True)
                for element in card.select(".matchValue.ProjectGeoLocationCity")
                if element.get_text(" ", strip=True)
            ]
            jobs.append({
                "title": title,
                "url": urljoin(base_url, anchor["href"]),
                "location": " / ".join(dict.fromkeys(locations)),
                "department": _value(card, "jobcategory"),
                "audience": _value(card, "audience"),
                "employment_type": _value(card, "employmentType") or _value(card, "employmenttype"),
                "posted_date": _value(card, "date"),
            })
        return jobs

    for anchor in soup.find_all("a", href=JOB_LINK):
        title = anchor.get_text(" ", strip=True)
        if not title:
            continue
        card = anchor.find_parent("div", id=re.compile(r"^job_id_"))
        locations = []
        if card:
            locations = [
                element.get_text(" ", strip=True)
                for element in card.select(".matchValue.ProjectGeoLocationCity")
                if element.get_text(" ", strip=True)
            ]
        jobs.append({
            "title": title,
            "url": urljoin(base_url, anchor["href"]),
            "location": " / ".join(dict.fromkeys(locations)),
            "department": _value(card, "jobcategory") if card else "",
            "audience": _value(card, "audience") if card else "",
            "employment_type": (
                _value(card, "employmentType") or _value(card, "employmenttype")
                if card else ""
            ),
            "posted_date": _value(card, "date") if card else "",
        })
    return jobs


def _job_posting(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("@type") == "JobPosting":
                return candidate
    return {}


def _description(soup: BeautifulSoup, posting: dict) -> str:
    description = posting.get("description")
    if description:
        return BeautifulSoup(str(description), "html.parser").get_text(separator=" ", strip=True)
    for selector in (
        '[class*="job-description"]',
        '[class*="jobDescription"]',
        '[id*="job-description"]',
        "article",
        "main",
    ):
        element = soup.select_one(selector)
        if element:
            text = element.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text
    return ""


def _employment_type(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    if isinstance(value, dict):
        return str(value.get("name") or value.get("value") or "")
    return str(value or "")


def _next_page(soup: BeautifulSoup, current_url: str) -> str:
    for anchor in soup.find_all("a", href=True):
        rel = anchor.get("rel") or []
        classes = " ".join(anchor.get("class") or []).casefold()
        label = " ".join([
            anchor.get_text(" ", strip=True),
            str(anchor.get("aria-label") or ""),
            str(anchor.get("title") or ""),
            classes,
            " ".join(rel) if isinstance(rel, list) else str(rel),
        ]).casefold()
        if "next" in label or "weiter" in label or "nächste" in label:
            href = urljoin(current_url, anchor["href"])
            if (
                href != current_url
                and urlsplit(href).scheme == "https"
                and urlsplit(href).hostname == urlsplit(current_url).hostname
            ):
                return href
    return ""


class SoftgardenScraper:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def scrape_jobs(
        self,
        url: str,
        company_name: str = "",
        company_description: str = "",
        label: str = "",
    ) -> list[dict]:
        jobs = []
        seen_pages = set()
        seen_links = set()
        page_url = url

        try:
            while page_url and page_url not in seen_pages and len(seen_pages) < 100 and len(jobs) < 1000:
                seen_pages.add(page_url)
                response = self.session.get(page_url, timeout=25)
                if response.status_code == 403:
                    logger.warning("Softgarden returned HTTP 403 for %s", urlsplit(page_url).hostname)
                    return []
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                page_jobs = parse_softgarden_listing(response.text, response.url)
                if not page_jobs:
                    break
                if self.delay:
                    time.sleep(self.delay)

                for listing in page_jobs:
                    job_link = listing["url"]
                    if job_link in seen_links:
                        continue
                    seen_links.add(job_link)
                    detail = {}
                    detail_soup = None
                    if "berlin" in listing["location"].casefold():
                        try:
                            detail_response = self.session.get(job_link, timeout=25)
                            if detail_response.status_code == 403:
                                logger.warning("Softgarden returned HTTP 403 for %s", urlsplit(job_link).hostname)
                            elif detail_response.status_code < 400:
                                detail_soup = BeautifulSoup(detail_response.text, "html.parser")
                                detail = _job_posting(detail_soup)
                        except requests.RequestException as error:
                            logger.debug("Softgarden detail request failed (%s)", type(error).__name__)
                        finally:
                            if self.delay:
                                time.sleep(self.delay)

                    detail_locations = detail.get("jobLocation") or []
                    if isinstance(detail_locations, dict):
                        detail_locations = [detail_locations]
                    detail_location = []
                    for location in detail_locations if isinstance(detail_locations, list) else []:
                        address = location.get("address") if isinstance(location, dict) else None
                        if isinstance(address, dict):
                            parts = [
                                address.get("addressLocality"),
                                address.get("addressRegion"),
                                address.get("addressCountry"),
                            ]
                            value = ", ".join(str(part) for part in parts if part)
                            if value:
                                detail_location.append(value)
                    location = " / ".join(dict.fromkeys(detail_location)) or listing["location"]
                    description = _description(detail_soup, detail) if detail_soup else ""
                    employment = (
                        _employment_type(detail.get("employmentType"))
                        or listing["employment_type"]
                    )
                    remote_text = f"{location} {description}".casefold()
                    remote = (
                        "Hybrid" if "hybrid" in remote_text
                        else "Yes" if "remote" in remote_text
                        else "No"
                    )
                    jobs.append({
                        "Company Name": company_name,
                        "Job Title": str(detail.get("title") or listing["title"]),
                        "Location": location,
                        "Job Link": job_link,
                        "Job Description": description,
                        "Employment Type": employment,
                        "Department": listing["department"],
                        "Posted Date": str(detail.get("datePosted") or listing["posted_date"]),
                        "Company Description": company_description,
                        "Remote": remote,
                        "Label": label,
                        "ATS": "Softgarden",
                    })

                next_page = _next_page(soup, response.url)
                page_url = next_page if next_page not in seen_pages else ""
                if page_url and self.delay:
                    time.sleep(self.delay)
        except requests.RequestException as error:
            logger.warning("Softgarden listing request failed (%s)", type(error).__name__)
            return []
        return jobs

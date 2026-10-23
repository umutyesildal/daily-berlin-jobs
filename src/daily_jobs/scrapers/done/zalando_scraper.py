from __future__ import annotations

import logging
import re
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
JOB_PATH = re.compile(r"/en/jobs/\d+-", re.IGNORECASE)


def parse_zalando_listing(html: str, base_url: str) -> tuple[list[dict], int]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for anchor in soup.find_all("a", href=JOB_PATH):
        article = anchor.find("article")
        if not article:
            continue
        title_element = article.find("h2")
        title = title_element.get_text(" ", strip=True) if title_element else ""
        paragraphs = [p.get_text(" ", strip=True) for p in article.find_all("p")]
        if not title:
            continue
        jobs.append({
            "title": title,
            "department": paragraphs[0] if paragraphs else "",
            "location": paragraphs[1] if len(paragraphs) > 1 else "",
            "url": urljoin(base_url, anchor.get("href", "")),
        })

    page_numbers = []
    for button in soup.find_all("button", attrs={"aria-label": True}):
        match = re.fullmatch(r"Page\s+(\d+)\s+button", str(button.get("aria-label") or ""), re.I)
        if match:
            page_numbers.append(int(match.group(1)))
    return jobs, max(page_numbers, default=1)


def _page_url(url: str, page: int) -> str:
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params.setdefault("location", "Berlin")
    params["page"] = str(page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))


def _plain_text(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text(separator=" ", strip=True) if value else ""


def _detail_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    text = main.get_text(" ", strip=True) if main else soup.get_text(" ", strip=True)
    article = soup.find("article")
    description = _plain_text(str(article)) if article else ""
    employment = ""
    match = re.search(r"\bContract\s+(.*?)\s+Job Category\b", text, re.IGNORECASE)
    if match:
        employment = match.group(1).strip()
    date = ""
    time_element = soup.find("time", attrs={"datetime": True})
    if time_element:
        date = str(time_element.get("datetime") or "")[:10]
    return {"description": description, "employment_type": employment, "posted_date": date}


class ZalandoScraper:
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
        company_name: str = "Zalando",
        company_description: str = "",
        label: str = "",
    ) -> list[dict]:
        jobs = []
        seen_links = set()
        page_limit = 100
        page = 1

        try:
            while page <= page_limit and len(jobs) < 500:
                response = self.session.get(_page_url(url, page), timeout=25)
                if response.status_code == 403:
                    logger.warning("Zalando returned HTTP 403 for %s", urlsplit(url).hostname)
                    return [] if page == 1 else jobs
                response.raise_for_status()
                page_jobs, page_count = parse_zalando_listing(response.text, response.url)
                new_jobs = [job for job in page_jobs if job["url"] not in seen_links]
                if not new_jobs:
                    break
                if self.delay:
                    time.sleep(self.delay)

                for listing in new_jobs:
                    seen_links.add(listing["url"])
                    location = listing["location"]
                    detail = {}
                    if "berlin" in location.casefold():
                        try:
                            detail_response = self.session.get(listing["url"], timeout=25)
                            if detail_response.status_code == 403:
                                logger.warning("Zalando detail returned HTTP 403 for %s", urlsplit(listing["url"]).hostname)
                            elif detail_response.status_code < 400:
                                detail = _detail_fields(detail_response.text)
                        except requests.RequestException as error:
                            logger.debug("Zalando detail request failed (%s)", type(error).__name__)
                        finally:
                            if self.delay:
                                time.sleep(self.delay)
                    if "berlin" not in location.casefold():
                        continue
                    jobs.append({
                        "Company Name": company_name,
                        "Job Title": listing["title"],
                        "Location": location,
                        "Job Link": listing["url"],
                        "Job Description": detail.get("description", ""),
                        "Employment Type": detail.get("employment_type", ""),
                        "Department": listing["department"],
                        "Posted Date": detail.get("posted_date", ""),
                        "Company Description": company_description,
                        "Remote": "Yes" if "remote" in location.casefold() else "No",
                        "Label": label,
                        "ATS": "Zalando",
                    })
                    if len(jobs) >= 500:
                        break

                if page >= page_count or page >= page_limit:
                    break
                page += 1
                if self.delay:
                    time.sleep(self.delay)
        except requests.RequestException as error:
            logger.warning("Zalando listing request failed (%s)", type(error).__name__)
            return jobs
        return jobs

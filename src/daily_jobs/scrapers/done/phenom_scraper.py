from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _embedded_object(script: str, marker: str) -> dict | None:
    match = re.search(rf"{re.escape(marker)}\s*=\s*", script)
    if not match:
        return None
    start = match.end()
    while start < len(script) and script[start].isspace():
        start += 1
    if start >= len(script) or script[start] != "{":
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(script)):
        char = script[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    value = json.loads(script[start:index + 1])
                except ValueError:
                    return None
                return value if isinstance(value, dict) else None
    return None


def extract_phapp_ddo(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    fallback = None
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        ddo = _embedded_object(text, "phApp.ddo")
        if ddo and ("eagerLoadRefineSearch" in ddo or "jobDetail" in ddo):
            return ddo
        if ddo is not None and fallback is None:
            fallback = ddo
    return fallback


def _slug(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")


def _location_values(job: dict) -> list[str]:
    values: list[str] = []
    for field in ("cityStateCountry", "location", "address", "city", "country"):
        value = job.get(field)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    for field in ("multi_location", "multi_location_array"):
        value = job.get(field)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    values.append(item.strip())
                elif isinstance(item, dict):
                    location = item.get("location")
                    if isinstance(location, str) and location.strip():
                        values.append(location.strip())
    result = []
    seen = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _job_url(search_url: str, ddo: dict, job: dict) -> str:
    direct = job.get("jobUrl") or job.get("url")
    if isinstance(direct, str) and direct.startswith(("https://", "http://")):
        return direct

    seq = str(job.get("jobSeqNo") or "")
    if not seq:
        return str(job.get("applyUrl") or "")
    config = ddo.get("siteConfig") or {}
    config_data = config.get("data") or {}
    template = ((config_data.get("urlMap") or {}).get("job") or "job/:jobId/:title")
    title_slug = _slug(str(job.get("title") or ""))
    path = str(template).replace(":jobId", quote(seq, safe="._-"))
    path = path.replace(":title", quote(title_slug, safe="-"))
    parts = urlsplit(search_url)
    page_dir = parts.path.rsplit("/", 1)[0].rstrip("/") + "/"
    base = urlunsplit((parts.scheme, parts.netloc, page_dir, "", ""))
    return urljoin(base, path)


def _base_search_url(url: str, offset: int) -> str:
    parts = urlsplit(url)
    params = urlencode({"keywords": "Berlin", "from": offset})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, params, ""))


def _plain_text(value: Any) -> str:
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(separator=" ", strip=True)


class PhenomScraper:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _get_ddo(self, url: str) -> dict | None:
        response = self.session.get(url, timeout=25)
        if response.status_code == 403:
            logger.warning("Phenom returned HTTP 403 for %s", urlsplit(url).hostname)
            return None
        response.raise_for_status()
        return extract_phapp_ddo(response.text)

    def scrape_jobs(
        self,
        url: str,
        company_name: str,
        company_description: str = "",
        label: str = "phenom",
    ) -> list[dict]:
        postings = []
        offset = 0
        total_hits: int | None = None
        page_config: dict = {}

        try:
            while offset < 500 and (total_hits is None or offset < total_hits):
                page_url = _base_search_url(url, offset)
                ddo = self._get_ddo(page_url)
                if not ddo:
                    if offset == 0:
                        return []
                    break
                search = ddo.get("eagerLoadRefineSearch") or {}
                data = search.get("data") or {}
                page = data.get("jobs") or []
                page_config = ddo
                if total_hits is None:
                    total_hits = int(search.get("totalHits") or len(page))
                if not page:
                    break
                postings.extend(page[:500 - len(postings)])
                offset += len(page)
                if offset < total_hits and offset < 500 and self.delay:
                    time.sleep(self.delay)
        except requests.exceptions.RequestException as error:
            logger.warning("Phenom listing request failed (%s)", type(error).__name__)
            return []
        except (ValueError, TypeError):
            logger.warning("Phenom search response could not be parsed")
            return []

        jobs = []
        for posting in postings:
            locations = _location_values(posting)
            if not any("berlin" in location.casefold() for location in locations):
                continue

            job_link = _job_url(url, page_config, posting)
            detail = {}
            if job_link:
                try:
                    detail_ddo = self._get_ddo(job_link)
                    detail = ((detail_ddo or {}).get("jobDetail") or {}).get("data") or {}
                    detail = detail.get("job") or {}
                except requests.exceptions.RequestException as error:
                    logger.debug("Phenom detail request failed (%s)", type(error).__name__)
                if self.delay:
                    time.sleep(self.delay)

            detailed_locations = _location_values(detail)
            if detailed_locations:
                locations = detailed_locations
            location = " / ".join(locations)
            if "berlin" not in location.casefold():
                continue
            jobs.append({
                "Company Name": company_name,
                "Job Title": str(detail.get("title") or posting.get("title") or ""),
                "Location": location,
                "Job Link": _job_url(url, page_config, detail or posting),
                "Job Description": _plain_text(
                    detail.get("description")
                    or detail.get("descriptionTeaser")
                    or posting.get("descriptionTeaser")
                ),
                "Employment Type": str(detail.get("type") or posting.get("type") or ""),
                "Department": str(
                    detail.get("category")
                    or detail.get("subCategory")
                    or posting.get("category")
                    or posting.get("subCategory")
                    or ""
                ),
                "Posted Date": str(detail.get("postedDate") or posting.get("postedDate") or ""),
                "Company Description": company_description,
                "Remote": "Yes" if "remote" in location.casefold() else "No",
                "Label": label,
                "ATS": "Phenom",
            })
        return jobs

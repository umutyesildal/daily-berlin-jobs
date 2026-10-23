from __future__ import annotations

import logging
import math
import time
from typing import Any
from urllib.parse import quote, urlsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
APPLE_API = "https://jobs.apple.com/api/v1"
BERLIN_LOCATION_ID = "postLocation-BRL"
SEARCH_PAGE_SIZE = 20


def apple_search_payload(page: int, locale: str = "en-us") -> dict:
    return {
        "query": "",
        "filters": {"locations": [BERLIN_LOCATION_ID]},
        "page": page,
        "locale": locale,
        "sort": "",
        "format": {
            "longDate": "MMMM D, YYYY",
            "mediumDate": "MMM D, YYYY",
        },
    }


def apple_locations(value: Any) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def apple_location_text(locations: list[dict]) -> str:
    values = []
    for location in locations:
        city = location.get("city") or location.get("name") or location.get("metro") or ""
        country = location.get("countryName") or ""
        if city and country and str(city).casefold() != str(country).casefold():
            value = f"{city}, {country}"
        else:
            value = str(city or country).strip()
        if value:
            values.append(value)
    return " / ".join(dict.fromkeys(values))


def is_apple_berlin_location(locations: list[dict]) -> bool:
    return any(
        location.get("postLocationId") == BERLIN_LOCATION_ID
        or location.get("id") == BERLIN_LOCATION_ID
        or "berlin" in " ".join(
            str(location.get(key) or "")
            for key in ("city", "name", "metro", "region", "postLocationId", "id")
        ).casefold()
        for location in locations
    )


def parse_apple_search_job(result: dict) -> dict:
    locations = apple_locations(result.get("locations"))
    return {
        "id": str(result.get("positionId") or result.get("id") or ""),
        "title": str(result.get("postingTitle") or result.get("title") or ""),
        "locations": locations,
        "location": apple_location_text(locations),
        "berlin": is_apple_berlin_location(locations),
    }


def _plain_text(value: Any) -> str:
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(separator=" ", strip=True)


def _job_link(locale: str, detail: dict, job_id: str, title: str) -> str:
    slug = str(detail.get("transformedPostingTitle") or "")
    if not slug:
        slug = "-".join(part for part in title.casefold().split() if part)
    return (
        f"https://jobs.apple.com/{quote(locale, safe='-')}/details/"
        f"{quote(job_id, safe='')}/{quote(slug, safe='-')}"
    )


class AppleScraper:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Origin": "https://jobs.apple.com",
            "Referer": "https://jobs.apple.com/en-us/search",
        })

    def _csrf_token(self) -> str:
        response = self.session.get(f"{APPLE_API}/CSRFToken", timeout=25)
        response.raise_for_status()
        token = response.headers.get("x-apple-csrf-token")
        if not token:
            raise ValueError("Apple CSRF endpoint did not return its token header")
        self.session.headers.update({"x-apple-csrf-token": token})
        if self.delay:
            time.sleep(self.delay)
        return token

    def _detail(self, job_id: str) -> dict:
        response = self.session.get(f"{APPLE_API}/jobDetails/{quote(job_id, safe='')}", timeout=25)
        if response.status_code == 403:
            logger.warning("Apple job detail returned HTTP 403")
            return {}
        response.raise_for_status()
        payload = response.json()
        detail = payload.get("res") if isinstance(payload, dict) else None
        if not isinstance(detail, dict):
            return {}
        return detail

    def scrape_jobs(
        self,
        url: str = "https://jobs.apple.com/en-us/search?location=berlin-BER",
        company_name: str = "Apple",
        company_description: str = "",
        label: str = "",
    ) -> list[dict]:
        locale_parts = [part for part in urlsplit(url).path.split("/") if part]
        locale = locale_parts[0] if locale_parts and "-" in locale_parts[0] else "en-us"

        try:
            self._csrf_token()
            response = self.session.post(
                f"{APPLE_API}/search",
                json=apple_search_payload(1, locale),
                timeout=30,
            )
            if response.status_code == 403:
                logger.warning("Apple search returned HTTP 403")
                return []
            response.raise_for_status()
            payload = response.json()
            result = payload.get("res") if isinstance(payload, dict) else None
            if not isinstance(result, dict) or not isinstance(result.get("searchResults"), list):
                raise ValueError("Apple search response has an unexpected structure")
            total_records = int(result.get("totalRecords") or 0)
            total_pages = min(100, max(1, math.ceil(total_records / SEARCH_PAGE_SIZE)))
            search_rows = list(result["searchResults"])

            for page in range(2, total_pages + 1):
                if self.delay:
                    time.sleep(self.delay)
                response = self.session.post(
                    f"{APPLE_API}/search",
                    json=apple_search_payload(page, locale),
                    timeout=30,
                )
                if response.status_code == 403:
                    logger.warning("Apple search returned HTTP 403")
                    return []
                response.raise_for_status()
                page_payload = response.json()
                page_result = page_payload.get("res") if isinstance(page_payload, dict) else None
                if not isinstance(page_result, dict) or not isinstance(page_result.get("searchResults"), list):
                    raise ValueError("Apple search page has an unexpected structure")
                page_rows = page_result["searchResults"]
                if not page_rows:
                    break
                search_rows.extend(page_rows)
        except requests.RequestException as error:
            logger.warning("Apple API request failed (%s)", type(error).__name__)
            return []
        except (ValueError, TypeError, KeyError) as error:
            logger.warning("Apple API response could not be parsed (%s)", type(error).__name__)
            return []

        jobs = []
        seen_ids = set()
        for row in search_rows:
            if not isinstance(row, dict):
                logger.warning("Apple search response contains an unexpected job row")
                return []
            listing = parse_apple_search_job(row)
            job_id = listing["id"]
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            if not listing["berlin"]:
                continue

            detail = {}
            try:
                detail = self._detail(job_id)
            except (requests.RequestException, ValueError, TypeError) as error:
                logger.debug("Apple job detail failed (%s)", type(error).__name__)
            finally:
                if self.delay:
                    time.sleep(self.delay)

            detail_locations = apple_locations(detail.get("locations"))
            location = apple_location_text(detail_locations) if detail_locations else listing["location"]
            if "berlin" not in location.casefold():
                continue
            title = str(detail.get("postingTitle") or listing["title"])
            detail_description = detail.get("description") or detail.get("jobSummary") or ""
            employment_type = detail.get("employmentType") or detail.get("employmentTypeName") or ""
            team_names = detail.get("teamNames") or []
            department = ", ".join(str(team) for team in team_names) if isinstance(team_names, list) else str(team_names)
            post_date = (
                detail.get("postingDateMeta")
                or detail.get("postDateInGMT")
                or detail.get("longPostingDate")
                or ""
            )
            jobs.append({
                "Company Name": company_name,
                "Job Title": title,
                "Location": location,
                "Job Link": _job_link(locale, detail, job_id, title),
                "Job Description": _plain_text(detail_description),
                "Employment Type": str(employment_type),
                "Department": department,
                "Posted Date": str(post_date)[:10],
                "Company Description": company_description,
                "Remote": "Yes" if "remote" in location.casefold() else "No",
                "Label": label,
                "ATS": "Apple",
            })
        return jobs

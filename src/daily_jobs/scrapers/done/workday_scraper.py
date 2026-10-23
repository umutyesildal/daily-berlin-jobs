from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

LOCALE_SEGMENT = re.compile(r"^[a-z]{2}-[a-z]{2}$", re.IGNORECASE)
MULTI_LOCATION = re.compile(r"^\s*\d+\s+locations?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class WorkdayBoard:
    host: str
    tenant: str
    site: str
    public_prefix: str


def parse_workday_url(url: str) -> WorkdayBoard:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = [unquote(part) for part in parsed.path.split("/") if part]
    if path and LOCALE_SEGMENT.fullmatch(path[0]):
        path.pop(0)

    workday_jobs = re.fullmatch(r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com", host, re.IGNORECASE)
    if workday_jobs:
        tenant = workday_jobs.group(1).lower()
        site = path[0] if path else ""
        if not site:
            raise ValueError("Workday career page has no site segment")
        return WorkdayBoard(
            host=host,
            tenant=tenant,
            site=site,
            public_prefix=f"/{quote(site, safe='._-')}",
        )

    workday_site = re.fullmatch(r"(wd\d+)\.myworkdaysite\.com", host, re.IGNORECASE)
    if workday_site:
        try:
            recruiting_index = next(index for index, part in enumerate(path) if part.casefold() == "recruiting")
            tenant, site = path[recruiting_index + 1:recruiting_index + 3]
        except (StopIteration, ValueError):
            raise ValueError("Workday recruiting URL must include tenant and site") from None
        if not tenant or not site:
            raise ValueError("Workday recruiting URL must include tenant and site")
        tenant = tenant.lower()
        return WorkdayBoard(
            host=host,
            tenant=tenant,
            site=site,
            public_prefix=f"/recruiting/{quote(tenant, safe='._-')}/{quote(site, safe='._-')}",
        )

    raise ValueError("Unsupported Workday career page URL")


def workday_postings(
    session: requests.Session,
    board: WorkdayBoard,
    *,
    search_text: str = "Berlin",
    delay: float = 0.2,
    max_postings: int = 500,
) -> tuple[list[dict], int | None]:
    endpoint = (
        f"https://{board.host}/wday/cxs/{quote(board.tenant, safe='._-')}/"
        f"{quote(board.site, safe='._-')}/jobs"
    )
    postings: list[dict] = []
    offset = 0
    total: int | None = None

    while len(postings) < max_postings and (total is None or offset < total):
        limit = min(20, max_postings - len(postings))
        response = session.post(
            endpoint,
            json={
                "limit": limit,
                "offset": offset,
                "searchText": search_text,
                "appliedFacets": {},
            },
            timeout=25,
        )
        if response.status_code == 403:
            logger.warning("Workday returned HTTP 403 for %s", board.host)
            return [], 403
        response.raise_for_status()
        payload = response.json()
        page = payload.get("jobPostings") or []
        if total is None:
            total = int(payload.get("total") or 0)
        if not page:
            break
        postings.extend(page[:max_postings - len(postings)])
        offset += len(page)
        if delay:
            time.sleep(delay)

    return postings, None


def _detail_info(payload: dict) -> dict:
    info = payload.get("jobPostingInfo")
    return info if isinstance(info, dict) else payload


def _location_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _location_values(child)]
    if isinstance(value, dict):
        return _location_values(
            value.get("descriptor")
            or value.get("fullLocation")
            or value.get("location")
            or value.get("name")
        )
    return []


def _full_locations(info: dict, listing_location: str) -> str:
    values = (
        _location_values(info.get("location"))
        + _location_values(info.get("additionalLocations"))
    )
    if not values:
        requisition_location = info.get("jobRequisitionLocation")
        values.extend(_location_values(requisition_location))
    if not values and not MULTI_LOCATION.fullmatch(listing_location):
        values.extend(_location_values(listing_location))
    unique = []
    seen = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return " / ".join(unique)


def _plain_text(value: object) -> str:
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(separator=" ", strip=True)


def _field_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("descriptor") or value.get("name") or "")
    return str(value or "")


class WorkdayScraper:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def scrape_jobs(
        self,
        url: str,
        company_name: str,
        company_description: str = "",
        label: str = "workday",
    ) -> list[dict]:
        try:
            board = parse_workday_url(url)
            postings, status_code = workday_postings(
                self.session,
                board,
                delay=self.delay,
                max_postings=500,
            )
            if status_code == 403:
                return []
        except requests.RequestException as error:
            logger.warning(
                "Workday listing request failed for %s (%s)",
                urlsplit(url).hostname or "source",
                type(error).__name__,
            )
            return []
        except (ValueError, TypeError) as error:
            logger.warning("Workday listing could not be parsed (%s)", type(error).__name__)
            return []

        jobs = []
        for posting in postings:
            listing_location = str(posting.get("locationsText") or "")
            needs_detail = (
                "berlin" in listing_location.casefold()
                or bool(MULTI_LOCATION.fullmatch(listing_location))
            )
            if not needs_detail:
                continue

            external_path = str(posting.get("externalPath") or "")
            detail = {}
            if external_path:
                detail_url = f"https://{board.host}/wday/cxs/{quote(board.tenant, safe='._-')}/{quote(board.site, safe='._-')}{external_path}"
                try:
                    response = self.session.get(detail_url, timeout=25)
                    if response.status_code == 403:
                        logger.warning("Workday returned HTTP 403 for %s", board.host)
                        return []
                    if response.status_code < 400:
                        detail = _detail_info(response.json())
                    else:
                        logger.warning("Workday detail request returned HTTP %s", response.status_code)
                except requests.RequestException as error:
                    logger.warning("Workday detail request failed (%s)", type(error).__name__)
                except (ValueError, TypeError) as error:
                    logger.warning("Workday detail could not be parsed (%s)", type(error).__name__)
                if self.delay:
                    time.sleep(self.delay)

            location = _full_locations(detail, listing_location)
            if "berlin" not in location.casefold():
                continue

            if board.host.endswith("myworkdaysite.com"):
                job_link = str(detail.get("externalUrl") or "")
                if not job_link:
                    job_link = f"https://{board.host}{board.public_prefix}{external_path}"
            else:
                job_link = f"https://{board.host}{board.public_prefix}{external_path}"
            title = _field_text(detail.get("title") or posting.get("title"))
            posted_date = (
                detail.get("startDate")
                or detail.get("postedOn")
                or posting.get("postedOn")
                or ""
            )
            employment_type = _field_text(detail.get("timeType") or posting.get("timeType"))
            department = (
                detail.get("jobFamily")
                or detail.get("jobFamilyGroup")
                or posting.get("jobFamily")
                or ""
            )
            remote_value = _field_text(detail.get("remoteType") or detail.get("workplaceType"))
            remote_normalized = remote_value.casefold()
            remote = (
                "Hybrid" if "hybrid" in remote_normalized
                else "Yes" if "remote" in remote_normalized
                else "No"
            )
            jobs.append({
                "Company Name": company_name,
                "Job Title": title,
                "Location": location,
                "Job Link": job_link,
                "Job Description": _plain_text(detail.get("jobDescription")),
                "Employment Type": employment_type,
                "Department": _field_text(department),
                "Posted Date": _field_text(posted_date),
                "Company Description": company_description,
                "Remote": remote,
                "Label": label,
                "ATS": "Workday",
            })
        return jobs

from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
APPLICATIONS_ROOT = "https://www.google.com/about/careers/applications/"


def _embedded_array(script: str) -> list:
    marker = re.search(r"\bdata\s*:\s*", script)
    if not marker:
        raise ValueError("Google ds:1 payload has no data array")
    start = marker.end()
    while start < len(script) and script[start].isspace():
        start += 1
    if start >= len(script) or script[start] != "[":
        raise ValueError("Google ds:1 payload data is not an array")

    stack = []
    pairs = {"[": "]", "{": "}"}
    in_string = False
    escaped = False
    end = None
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
        elif char in pairs:
            stack.append(pairs[char])
        elif char in "]}":
            if not stack or stack.pop() != char:
                raise ValueError("Google ds:1 payload has unbalanced data")
            if not stack:
                end = index + 1
                break
    if end is None:
        raise ValueError("Google ds:1 payload data is incomplete")
    payload = json.loads(script[start:end])
    if isinstance(payload, list) and payload and payload[0] is None:
        return []
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError("Google ds:1 payload has an unexpected job structure")
    return payload[0]


def _plain_text(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text(separator=" ", strip=True) if value else ""


def _description(row: list) -> str:
    fragments = []
    for index in (3, 4, 10, 18, 19):
        if index >= len(row):
            continue
        value = row[index]
        if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
            value = value[1]
        if isinstance(value, str) and value.strip() and value not in fragments:
            fragments.append(value)
    return "\n".join(_plain_text(fragment) for fragment in fragments)


def _location_text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, list):
        raise ValueError("Google job row has no locations array")
    locations = []
    for item in value:
        if isinstance(item, list) and item and isinstance(item[0], str):
            locations.append(item[0])
        elif isinstance(item, str):
            locations.append(item)
    return " / ".join(dict.fromkeys(location.strip() for location in locations if location.strip()))


def _job_link(job_id: str, title: str, anchor_links: dict[str, str]) -> str:
    if job_id in anchor_links:
        return anchor_links[job_id]
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    return f"{APPLICATIONS_ROOT}jobs/results/{quote(job_id, safe='')}-{quote(slug, safe='-')}"


def parse_google_ds1(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    payload_script = soup.find("script", class_="ds:1")
    if not payload_script:
        raise ValueError("Google page did not contain a ds:1 payload")
    script_text = payload_script.string or payload_script.get_text()
    rows = _embedded_array(script_text)

    anchor_links = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        match = re.search(r"(?:^|/)jobs/results/(\d+)-[^/?#]+", href)
        if not match:
            continue
        job_id = match.group(1)
        path = urlsplit(href).path
        if path.startswith("/"):
            anchor_links[job_id] = urlunsplit(("https", "www.google.com", path, "", ""))
        else:
            anchor_links[job_id] = urlunsplit(
                ("https", "www.google.com", f"/about/careers/applications/{path}", "", "")
            )

    jobs = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 10:
            raise ValueError("Google ds:1 job row has an unexpected structure")
        job_id, title = row[0], row[1]
        if not isinstance(job_id, str) or not isinstance(title, str):
            raise ValueError("Google ds:1 job row is missing its id or title")
        locations = _location_text(row[9])
        jobs.append({
            "id": job_id,
            "title": title,
            "location": locations,
            "url": _job_link(job_id, title, anchor_links),
            "description": _description(row),
            "department": str(row[7] or "") if len(row) > 7 else "",
        })
    return jobs


def _page_url(url: str, page: int) -> str:
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["location"] = params.get("location") or "Berlin, Germany"
    params["page"] = str(page)
    return urlunsplit((parts.scheme or "https", parts.netloc or "www.google.com", parts.path, urlencode(params), ""))


class GoogleScraper:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def scrape_jobs(
        self,
        url: str,
        company_name: str = "Google",
        company_description: str = "",
        label: str = "",
    ) -> list[dict]:
        jobs = []
        seen_ids = set()
        try:
            for page in range(1, 31):
                response = self.session.get(_page_url(url, page), timeout=30)
                if response.status_code == 403:
                    logger.warning("Google Careers returned HTTP 403")
                    return []
                response.raise_for_status()
                page_jobs = parse_google_ds1(response.text)
                fresh_jobs = [job for job in page_jobs if job["id"] not in seen_ids]
                if not fresh_jobs:
                    break
                for job in fresh_jobs:
                    seen_ids.add(job["id"])
                    if "berlin" not in job["location"].casefold():
                        continue
                    jobs.append({
                        "Company Name": company_name,
                        "Job Title": job["title"],
                        "Location": job["location"],
                        "Job Link": job["url"],
                        "Job Description": job["description"],
                        "Employment Type": "",
                        "Department": job["department"],
                        "Posted Date": "",
                        "Company Description": company_description,
                        "Remote": "Yes" if "remote" in job["location"].casefold() else "No",
                        "Label": label,
                        "ATS": "Google",
                    })
                if self.delay and page < 30:
                    time.sleep(self.delay)
        except (requests.RequestException, ValueError, json.JSONDecodeError) as error:
            logger.warning("Google Careers response could not be parsed (%s)", type(error).__name__)
            return []
        return jobs

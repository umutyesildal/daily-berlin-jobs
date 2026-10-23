from __future__ import annotations

import argparse
import collections
import hashlib
import html
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ..company_catalog import normalize_url
from ..job_taxonomy import classify_role
from ..postgres_storage import PostgresJobStorage
from ..scrapers.done.softgarden_scraper import SoftgardenScraper
from ..scrapers.done.teamtailor_scraper import TeamtailorScraper
from ..scrapers.done.workday_scraper import WorkdayScraper
from .boards import career_page, extract_boards
from .constants import (
    AGGREGATOR_DOMAINS,
    ATS_DOMAINS,
    DISCOVERY_TERMS,
    LLM_INSTRUCTIONS,
    LLM_SYSTEM,
    NEBIUS_MODEL,
    PARKED_DOMAINS,
    PARKED_MARKERS,
    RECRUITER_BLOCKLIST,
    SOCIAL_OR_NOISE,
    URL_RE,
)
from .text import (
    is_berlin,
    is_demo_or_test_slug,
    is_engineering,
    name_similarity,
    norm_name,
    registrable_domain,
    title_overlap,
)

USER_AGENT = "daily-berlin-jobs-discovery/0.1 (+https://github.com/umutyesildal/daily-berlin-jobs)"
TAVILY_ENDPOINT = "https://api.tavily.com/search"
NEBIUS_ENDPOINT = "https://api.tokenfactory.nebius.com/v1/chat/completions"


class BudgetExhausted(Exception):
    pass


class DiscoveryStore:
    def __init__(self, connection):
        self.connection = connection
        self.lock = threading.RLock()

    def _query(self, query: str, params=(), *, fetchone=False, fetchall=False):
        with self.lock:
            try:
                with self.connection.cursor() as cursor:
                    cursor.execute(query, params)
                    result = cursor.fetchone() if fetchone else cursor.fetchall() if fetchall else None
                self.connection.commit()
                return result
            except Exception:
                self.connection.rollback()
                raise

    def search_cache_get(self, query_key: str):
        row = self._query(
            """
            SELECT results FROM discovery_search_cache
            WHERE query_key = %s AND fetched_at > now() - interval '30 days'
            """,
            (query_key,),
            fetchone=True,
        )
        return row[0] if row else None

    def search_cache_put(self, query_key: str, query: dict, results: dict) -> None:
        self._query(
            """
            INSERT INTO discovery_search_cache(query_key, query, results, fetched_at)
            VALUES (%s, %s::jsonb, %s::jsonb, now())
            ON CONFLICT (query_key) DO UPDATE SET
                query = EXCLUDED.query,
                results = EXCLUDED.results,
                fetched_at = now()
            """,
            (query_key, json.dumps(query), json.dumps(results)),
        )

    def board_states(self) -> dict[tuple[str, str], tuple[str, datetime]]:
        rows = self._query(
            "SELECT ats, slug_key, status, last_checked_at FROM discovered_boards",
            fetchall=True,
        )
        return {
            (ats, slug_key.lower()): (status, last_checked_at)
            for ats, slug_key, status, last_checked_at in rows
        }

    def save_board(self, record: dict) -> None:
        llm = json.dumps(record["llm"]) if record.get("llm") is not None else None
        self._query(
            """
            INSERT INTO discovered_boards(
                ats, slug_key, slug, region, career_page, status, reason,
                company_name, website, api_berlin_eng, scraper_berlin_eng, llm
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (ats, slug_key) DO UPDATE SET
                slug = EXCLUDED.slug,
                region = EXCLUDED.region,
                career_page = EXCLUDED.career_page,
                status = EXCLUDED.status,
                reason = EXCLUDED.reason,
                company_name = EXCLUDED.company_name,
                website = EXCLUDED.website,
                api_berlin_eng = EXCLUDED.api_berlin_eng,
                scraper_berlin_eng = EXCLUDED.scraper_berlin_eng,
                llm = EXCLUDED.llm,
                last_checked_at = now()
            """,
            (
                record["ats"],
                record["slug"].lower(),
                record["slug"],
                record["region"],
                record["career_page"],
                record["status"],
                record.get("reason"),
                record.get("company_name") or record.get("name"),
                record.get("website"),
                record.get("api_berlin_eng", 0),
                record.get("scraper_berlin_eng", 0),
                llm,
            ),
        )


def sha(value: object) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True).encode()).hexdigest()


def safe_error_message(error: Exception) -> str:
    message = str(error)
    for name in ("TAVILY_API_KEY_DISCOVERY", "TAVILY_API_KEY_RESOLVE", "NEBIUS_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            message = message.replace(secret, "[redacted]")
    return message[:200]


def http_get(url: str, timeout=15, max_bytes=3_000_000):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(max_bytes).decode("utf-8", "ignore"), response.geturl()
    except urllib.error.HTTPError as error:
        return error.code, "", url
    except Exception:
        return None, "", url


def _json(url: str):
    status, body, _ = http_get(url, timeout=20)
    if status != 200:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def website_candidates(text: str) -> list[str]:
    counts = collections.Counter()
    for host in URL_RE.findall(text or ""):
        domain = registrable_domain(host)
        if domain and domain not in SOCIAL_OR_NOISE and not any(domain.endswith(suffix) for suffix in SOCIAL_OR_NOISE):
            counts[domain] += 1
    return [domain for domain, _ in counts.most_common(5)]


def verify_website(
    domain_or_url: str,
    company_name: str,
    source: str = "llm",
    *,
    page_cache: dict[str, dict] | None = None,
    fetch_page=None,
):
    if not domain_or_url:
        return None
    url = domain_or_url if domain_or_url.startswith("http") else f"https://{domain_or_url}"
    domain = registrable_domain(urllib.parse.urlsplit(url).hostname or "")
    if not domain or domain in SOCIAL_OR_NOISE or domain in PARKED_DOMAINS:
        return None
    if source in ("slug_guess", "search") and name_similarity(domain.split(".")[0], company_name) < 0.8:
        return None
    if source == "tavily_site" and name_similarity(domain.split(".")[0], company_name) < 0.8:
        return None

    page_cache = page_cache if page_cache is not None else {}
    cached = page_cache.get(domain)
    if cached is None:
        fetch = fetch_page or http_get
        status, body, final = fetch(f"https://{domain}", timeout=15, max_bytes=400_000)
        if status != 200:
            status, body, final = fetch(f"https://www.{domain}", timeout=15, max_bytes=400_000)
        cached = {"status": status, "final": final, "head": body[:60000]}
        page_cache[domain] = cached
    if cached["status"] != 200:
        return None
    final_domain = registrable_domain(urllib.parse.urlsplit(cached["final"]).hostname or "")
    if final_domain != domain:
        return None
    head = cached["head"].casefold()
    if any(marker in head for marker in PARKED_MARKERS):
        return None
    tokens = [token for token in norm_name(company_name).split() if len(token) >= 3][:2]
    tokens = tokens or [norm_name(company_name).replace(" ", "")]
    page = norm_name(cached["head"])
    page_compact = page.replace(" ", "")
    if tokens and all(token in page or token in page_compact for token in tokens):
        return f"https://{domain}"
    return None


class DiscoveryRunner:
    def __init__(
        self,
        storage: PostgresJobStorage,
        store: DiscoveryStore,
        *,
        budget_discovery: int,
        budget_resolve: int,
        dry_run: bool,
    ):
        self.storage = storage
        self.store = store
        self.budgets = {"DISCOVERY": budget_discovery, "RESOLVE": budget_resolve}
        self.spent = {"DISCOVERY": 0, "RESOLVE": 0}
        self.stopped = {"DISCOVERY": False, "RESOLVE": False}
        self.dry_run = dry_run
        self.lock = threading.Lock()
        self.board_cache: dict[tuple[str, str, str], dict] = {}
        self.scraper_cache: dict[tuple[str, str, str], dict] = {}
        self.llm_cache: dict[tuple, dict | None] = {}
        self.page_cache: dict[str, dict] = {}
        self.priority_companies: list[str] = []

    def tavily(self, query: str, key_name: str, include_domains=None, max_results=20):
        cache_key = {"q": query, "d": include_domains, "n": max_results}
        query_key = sha(cache_key)
        cached = self.store.search_cache_get(query_key)
        if cached is not None:
            return cached

        with self.lock:
            if self.stopped[key_name] or self.spent[key_name] >= self.budgets[key_name]:
                self.stopped[key_name] = True
                raise BudgetExhausted(key_name)
        environment_key = f"TAVILY_API_KEY_{key_name}"
        api_key = os.environ.get(environment_key)
        if not api_key:
            raise RuntimeError(f"Missing environment variable {environment_key}")

        body = {"query": query, "max_results": max_results, "search_depth": "basic"}
        if include_domains:
            body["include_domains"] = include_domains
        for attempt in range(4):
            with self.lock:
                if self.stopped[key_name] or self.spent[key_name] >= self.budgets[key_name]:
                    self.stopped[key_name] = True
                    raise BudgetExhausted(key_name)
                self.spent[key_name] += 1
            request = urllib.request.Request(
                TAVILY_ENDPOINT,
                data=json.dumps(body).encode(),
                method="POST",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=40) as response:
                    payload = json.loads(response.read().decode())
                result = {"results": payload.get("results", [])}
                self.store.search_cache_put(query_key, cache_key, result)
                return result
            except urllib.error.HTTPError as error:
                if error.code in (432, 433):
                    with self.lock:
                        self.stopped[key_name] = True
                    raise BudgetExhausted(f"{key_name}: HTTP {error.code}") from None
                if error.code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                result = {"results": [], "error": error.code}
                self.store.search_cache_put(query_key, cache_key, result)
                return result
            except Exception:
                time.sleep(2 * (attempt + 1))
        return {"results": [], "error": "network"}

    def load_inputs(self):
        linkedin_titles = collections.defaultdict(list)
        existing_boards = set()
        with self.storage.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT company_name, title FROM jobs WHERE lower(coalesce(source,''))='linkedin'"
            )
            for company, title in cursor.fetchall():
                linkedin_titles[str(company).replace("\\u0026", "&")].append(str(title or ""))
            cursor.execute("SELECT career_page FROM career_sources")
            for (page,) in cursor.fetchall():
                for ats, slug, _region in extract_boards(str(page or "")):
                    existing_boards.add((ats, slug.lower()))
            cursor.execute(
                """
                SELECT DISTINCT c.name
                FROM companies c
                JOIN career_sources s ON s.company_id = c.id
                JOIN source_health h ON h.career_source_id = s.id
                WHERE h.disabled_at > now() - interval '30 days'
                  AND h.disabled_reason LIKE 'auto:%'
                  AND NOT EXISTS (
                      SELECT 1 FROM career_sources active_source
                      WHERE active_source.company_id = c.id AND active_source.active
                  )
                ORDER BY c.name
                """
            )
            self.priority_companies = [str(row[0]) for row in cursor.fetchall()]
        for company in self.priority_companies:
            linkedin_titles[company] = []
        return linkedin_titles, existing_boards

    def stage_discovery(self, max_rounds=2):
        queries = [(f"{term} Berlin", [domain]) for domain in ATS_DOMAINS for term in DISCOVERY_TERMS]
        if max_rounds >= 2:
            for domain in ["ashbyhq.com", "greenhouse.io", "lever.co", "personio.de"]:
                for term in DISCOVERY_TERMS:
                    queries.append((f"{term} Berlin Germany (m/w/d) startup", [domain]))

        def run(item):
            query, domains = item
            try:
                result = self.tavily(query, "DISCOVERY", include_domains=domains)
            except BudgetExhausted:
                return item, None
            text = " ".join(
                f"{result_row.get('url', '')} {result_row.get('content', '')[:500]}"
                for result_row in result.get("results", [])
            )
            return item, extract_boards(text)

        boards = set()
        log = []
        with ThreadPoolExecutor(4) as pool:
            for (query, domains), found in pool.map(run, queries):
                if found is None:
                    log.append({"query": query, "domain": domains[0], "skipped": "budget"})
                    continue
                new = found - boards
                boards |= found
                log.append({"query": query, "domain": domains[0], "boards": len(found), "new": len(new)})
        return boards, log

    def stage_resolve(self, linkedin_titles, already_found_names):
        prioritized = [company for company in self.priority_companies if company in linkedin_titles]
        priority_set = set(prioritized)
        companies = prioritized + sorted(
            (company for company in linkedin_titles if company not in priority_set),
            key=lambda company: -len(linkedin_titles[company]),
        )
        candidates = collections.defaultdict(set)
        site_hints = collections.defaultdict(list)
        todo = [
            company for company in companies
            if norm_name(company) not in RECRUITER_BLOCKLIST and company not in already_found_names
        ]

        def run(company):
            found, hints = set(), []
            try:
                first = self.tavily(f'"{company}" jobs Berlin', "RESOLVE", include_domains=ATS_DOMAINS)
                for result in first.get("results", []):
                    found |= extract_boards(result.get("url", ""))
                if not found:
                    try:
                        second = self.tavily(f"{company} careers Berlin", "RESOLVE")
                    except BudgetExhausted:
                        second = self.tavily(f"{company} careers Berlin", "DISCOVERY")
                    pages = 0
                    for result in second.get("results", []):
                        url = result.get("url", "")
                        found |= extract_boards(url + " " + result.get("content", ""))
                        host = registrable_domain(urllib.parse.urlsplit(url).hostname or "")
                        if not host or host in AGGREGATOR_DOMAINS:
                            continue
                        hints.append(host)
                        if pages < 3:
                            pages += 1
                            status, body, _ = http_get(url, timeout=15, max_bytes=800_000)
                            found |= extract_boards(body)
            except BudgetExhausted:
                return company, None, hints
            return company, found, hints

        with ThreadPoolExecutor(4) as pool:
            for company, found, hints in pool.map(run, todo):
                if found is None:
                    continue
                candidates[company] |= found
                site_hints[company] = hints
        return candidates, site_hints

    def fetch_board(self, board):
        if board in self.board_cache:
            return self.board_cache[board]
        ats, slug, region = board
        name, jobs = None, []
        try:
            if ats == "ashby":
                data = _json(f"https://api.ashbyhq.com/posting-api/job-board/{urllib.parse.quote(slug)}")
                for job in (data or {}).get("jobs", []):
                    locations = [job.get("location") or ""] + [
                        secondary.get("location", "") for secondary in job.get("secondaryLocations") or []
                    ]
                    address = ((job.get("address") or {}).get("postalAddress") or {}).get("addressLocality") or ""
                    jobs.append({
                        "title": job.get("title", ""),
                        "location": " | ".join(filter(None, locations + [address])),
                        "text": (job.get("descriptionPlain") or "")[:4000],
                    })
            elif ats == "greenhouse":
                meta = _json(f"https://boards-api.greenhouse.io/v1/boards/{slug}") or {}
                name = meta.get("name")
                data = _json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
                for job in (data or {}).get("jobs", []):
                    jobs.append({
                        "title": job.get("title", ""),
                        "location": (job.get("location") or {}).get("name", ""),
                        "text": html.unescape(job.get("content") or "")[:4000],
                    })
            elif ats == "lever":
                data = _json(f"https://api.{'eu.' if region == 'eu' else ''}lever.co/v0/postings/{slug}?mode=json")
                for job in data if isinstance(data, list) else []:
                    categories = job.get("categories") or {}
                    locations = [categories.get("location") or ""] + list(categories.get("allLocations") or [])
                    jobs.append({
                        "title": job.get("text", ""),
                        "location": " | ".join(filter(None, locations)),
                        "text": (job.get("descriptionPlain") or "")[:4000],
                    })
            elif ats == "personio":
                status, body, _ = http_get(f"https://{slug}.jobs.personio.{region or 'de'}/xml", timeout=20)
                if status == 200 and "<position" in body:
                    for block in re.findall(r"<position>(.*?)</position>", body, re.S):
                        title = re.search(r"<name>(.*?)</name>", block, re.S)
                        offices = re.findall(r"<office>(.*?)</office>", block, re.S)
                        jobs.append({
                            "title": html.unescape(title.group(1)) if title else "",
                            "location": " | ".join(html.unescape(office) for office in offices),
                            "text": html.unescape(re.sub(r"<[^>]+>", " ", block))[:4000],
                        })
                    company = re.search(r"<subcompany>(.*?)</subcompany>", body, re.S)
                    name = html.unescape(company.group(1)).strip() if company else None
            elif ats == "recruitee":
                data = _json(f"https://{slug}.recruitee.com/api/offers")
                for job in (data or {}).get("offers", []):
                    name = name or job.get("company_name")
                    jobs.append({
                        "title": job.get("title", ""),
                        "location": " | ".join(filter(None, [job.get("city") or "", job.get("location") or ""])),
                        "text": html.unescape(re.sub(r"<[^>]+>", " ", job.get("description") or ""))[:4000],
                    })
            elif ats == "workable":
                data = _json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}") or {}
                name = data.get("name")
                for job in data.get("jobs", []):
                    locations = [job.get("city") or ""] + [
                        location.get("city", "") for location in job.get("locations") or []
                    ]
                    jobs.append({
                        "title": job.get("title", ""),
                        "location": " | ".join(filter(None, locations)),
                        "text": (data.get("description") or "")[:2000],
                    })
            elif ats == "smartrecruiters":
                data = _json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100") or {}
                for job in data.get("content", []):
                    name = name or (job.get("company") or {}).get("name")
                    location = job.get("location") or {}
                    jobs.append({
                        "title": job.get("name", ""),
                        "location": " | ".join(filter(None, [location.get("city") or "", location.get("fullLocation") or ""])),
                        "text": "",
                    })
            elif ats == "workday":
                tenant = slug.split("/", 1)[0]
                name = tenant
                scraper = WorkdayScraper(delay=0)
                for job in scraper.scrape_jobs(
                    career_page("workday", slug, region),
                    tenant,
                    label="workday",
                ):
                    jobs.append({
                        "title": job.get("Job Title", ""),
                        "location": job.get("Location", ""),
                        "text": job.get("Job Description", "")[:4000],
                    })
            elif ats in {"teamtailor", "softgarden"}:
                name = slug
                scraper_class = TeamtailorScraper if ats == "teamtailor" else SoftgardenScraper
                scraper = scraper_class(delay=0)
                for job in scraper.scrape_jobs(
                    career_page(ats, slug, region),
                    slug,
                    label=ats,
                ):
                    name = job.get("Company Name") or name
                    jobs.append({
                        "title": job.get("Job Title", ""),
                        "location": job.get("Location", ""),
                        "text": job.get("Job Description", "")[:4000],
                    })
        except Exception as error:
            result = {"ok": False, "error": safe_error_message(error), "jobs": []}
            self.board_cache[board] = result
            return result

        berlin = [job for job in jobs if is_berlin(job["location"])]
        berlin_eng = [job for job in berlin if is_engineering(job["title"])]
        result = {
            "ok": True,
            "name": name,
            "total": len(jobs),
            "berlin": len(berlin),
            "berlin_eng": len(berlin_eng),
            "berlin_eng_titles": [job["title"] for job in berlin_eng][:15],
            "all_titles": [job["title"] for job in jobs][:200],
            "text_sample": " ".join(job["text"] for job in (berlin_eng or jobs)[:3])[:6000],
        }
        self.board_cache[board] = result
        return result

    def scraper_check(self, board, display_name):
        if board in self.scraper_cache:
            return self.scraper_cache[board]
        from ..client import JobCrawlerController

        ats, slug, region = board
        error = None
        rows = []
        try:
            with tempfile.TemporaryDirectory(prefix="daily-jobs-discovery-") as output_dir:
                controller = JobCrawlerController(delay=0.2, output_dir=output_dir)
                scraper = controller.get_scraper(ats)
                rows = scraper.scrape_jobs(career_page(ats, slug, region), display_name or slug) or []
        except Exception as exc:
            error = safe_error_message(exc)
        berlin_eng = [
            row for row in rows
            if is_berlin(str(row.get("Location", ""))) and is_engineering(str(row.get("Job Title", "")))
        ]
        result = {"rows": len(rows), "berlin_eng": len(berlin_eng), "error": error}
        self.scraper_cache[board] = result
        return result

    def llm_check(self, board, evidence):
        cache_key = (board, sha(evidence))
        if cache_key in self.llm_cache:
            return self.llm_cache[cache_key]
        api_key = os.environ.get("NEBIUS_API_KEY")
        if not api_key:
            self.llm_cache[cache_key] = None
            return None

        body = {
            "model": NEBIUS_MODEL,
            "temperature": 0,
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": LLM_SYSTEM},
                {
                    "role": "user",
                    "content": LLM_INSTRUCTIONS.format(evidence=json.dumps(evidence, ensure_ascii=False)),
                },
            ],
        }
        for attempt in range(4):
            request = urllib.request.Request(
                NEBIUS_ENDPOINT,
                data=json.dumps(body).encode(),
                method="POST",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = json.loads(response.read().decode())
                content = payload["choices"][0]["message"]["content"]
                result = json.loads(content[content.find("{"): content.rfind("}") + 1])
                self.llm_cache[cache_key] = result
                return result
            except Exception:
                time.sleep(3 * (attempt + 1))
        self.llm_cache[cache_key] = None
        return None

    def verify_website(self, domain_or_url: str, company_name: str, source: str = "llm"):
        return verify_website(
            domain_or_url,
            company_name,
            source,
            page_cache=self.page_cache,
        )

    def _state_allows_check(self, board, states, now):
        state = states.get((board[0], board[1].lower()))
        if not state:
            return True
        status, last_checked_at = state
        if status == "accepted":
            return False
        if status == "rejected" and last_checked_at >= now - timedelta(days=14):
            return False
        return True

    def _checked_record(self, board, api_result, linkedin_match, board_origin, site_hints):
        if not api_result.get("ok"):
            return {
                "ats": board[0],
                "slug": board[1],
                "region": board[2],
                "career_page": career_page(*board),
                "board_name": None,
                "linkedin_company": None,
                "api_berlin_eng": 0,
                "scraper_berlin_eng": 0,
                "scraper_error": api_result.get("error"),
                "llm": None,
                "name": board[1],
                "website": None,
                "reason": "api_unavailable",
            }
        if api_result.get("berlin_eng", 0) < 1:
            return {
                "ats": board[0],
                "slug": board[1],
                "region": board[2],
                "career_page": career_page(*board),
                "board_name": api_result.get("name"),
                "linkedin_company": None,
                "api_berlin_eng": api_result.get("berlin_eng", 0),
                "scraper_berlin_eng": 0,
                "scraper_error": None,
                "llm": None,
                "name": api_result.get("name") or board[1],
                "website": None,
                "reason": "api_no_berlin_engineering",
            }

        display = linkedin_match.get(board) or api_result.get("name") or board[1]
        scraped = self.scraper_check(board, display)
        evidence = {
            "board_ats": board[0],
            "board_slug": board[1],
            "board_name": api_result.get("name"),
            "linkedin_company_name": linkedin_match.get(board),
            "sample_job_titles": api_result["berlin_eng_titles"][:8],
            "total_jobs_on_board": api_result["total"],
            "description_excerpt": api_result["text_sample"][:1500],
            "website_candidates_from_descriptions": website_candidates(api_result["text_sample"])[:3],
        }
        verdict = self.llm_check(board, evidence) if scraped["berlin_eng"] >= 1 else None
        record = {
            "ats": board[0],
            "slug": board[1],
            "region": board[2],
            "career_page": career_page(*board),
            "board_name": api_result.get("name"),
            "linkedin_company": linkedin_match.get(board),
            "api_berlin_eng": api_result["berlin_eng"],
            "scraper_berlin_eng": scraped["berlin_eng"],
            "scraper_error": scraped.get("error"),
            "llm": verdict,
        }

        reason = None
        if is_demo_or_test_slug(board[1]):
            reason = "demo_or_test_board"
        elif scraped["berlin_eng"] < 1:
            reason = "scraper_no_berlin_engineering"
        elif not verdict:
            reason = "llm_unavailable"
        elif verdict.get("is_staffing_or_recruitment_agency") or verdict.get("is_job_board_or_marketplace"):
            reason = "agency_or_marketplace"
        name = linkedin_match.get(board) or (verdict or {}).get("company_name") or api_result.get("name") or board[1]
        if not reason and norm_name(name) in RECRUITER_BLOCKLIST:
            reason = "recruiter_blocklist"

        website = None
        if not reason:
            company_hints = []
            for company in board_origin.get(board, ()):
                company_hints += site_hints.get(company, [])
            slug_core = re.sub(r"[^a-z0-9.-]", "", board[1].lower())
            slug_guesses = [slug_core] if "." in slug_core else [
                f"{slug_core}.{tld}" for tld in ("com", "de", "io", "ai")
            ]
            ordered = (
                [("llm", verdict.get("official_website"))]
                + [("description", candidate) for candidate in website_candidates(api_result["text_sample"])]
                + [("search", candidate) for candidate in company_hints]
                + [("slug_guess", candidate) for candidate in slug_guesses]
            )
            for source, candidate in ordered:
                website = self.verify_website(candidate, name, source) if candidate else None
                if website:
                    record["website_source"] = source
                    break
            if not website:
                try:
                    try:
                        results = self.tavily(f"{name} official website", "RESOLVE", max_results=5)
                    except BudgetExhausted:
                        results = self.tavily(f"{name} official website", "DISCOVERY", max_results=5)
                except BudgetExhausted:
                    results = {"results": []}
                for result in results.get("results", []):
                    host = registrable_domain(urllib.parse.urlsplit(result.get("url", "")).hostname or "")
                    website = self.verify_website(host, name, "tavily_site") if host and host not in AGGREGATOR_DOMAINS else None
                    if website:
                        record["website_source"] = "tavily_site"
                        break
            if not website:
                reason = "website_unverified"

        record.update({"name": name, "website": website, "reason": reason})
        return record

    def _dedupe_accepted(self, accepted: list[dict], rejected: list[dict]):
        best_by_key = {}
        for record in sorted(accepted, key=lambda row: -row["scraper_berlin_eng"]):
            keys = {
                ("name", norm_name(record["name"]).replace(" ", "")),
                (
                    "domain",
                    registrable_domain(urllib.parse.urlsplit(record["website"]).hostname),
                ),
            }
            if any(key in best_by_key for key in keys):
                record["reason"] = "duplicate_company"
                rejected.append(record)
                continue
            for key in keys:
                best_by_key[key] = record
        return sorted(best_by_key.values(), key=lambda row: row["name"].casefold()), rejected

    def run(self, started: datetime | None = None):
        started = started or datetime.now(timezone.utc)
        linkedin_titles, catalog_boards = self.load_inputs()
        known_states = self.store.board_states()

        open_boards, discovery_log = self.stage_discovery()
        resolved, site_hints = self.stage_resolve(linkedin_titles, set())
        board_origin = collections.defaultdict(set)
        all_boards = set(open_boards)
        for company, boards in resolved.items():
            for board in boards:
                board_origin[board].add(company)
                all_boards.add(board)

        now = datetime.now(timezone.utc)
        candidate_boards = {}
        candidate_origins = collections.defaultdict(set)
        for board in sorted(all_boards):
            key = (board[0], board[1].lower())
            candidate_boards.setdefault(key, board)
            candidate_origins[key].update(board_origin.get(board, ()))

        candidates = {}
        for key, board in candidate_boards.items():
            if key in catalog_boards or not self._state_allows_check(board, known_states, now):
                continue
            board_origin[board].update(candidate_origins[key])
            candidates.setdefault(key, board)
        boards_to_check = sorted(candidates.values())

        with ThreadPoolExecutor(12) as pool:
            verified = dict(zip(boards_to_check, pool.map(self.fetch_board, boards_to_check)))
        api_pass = {
            board: result for board, result in verified.items()
            if result.get("ok") and result.get("berlin_eng", 0) >= 1
        }
        linkedin_match = {}
        for board, info in api_pass.items():
            best = None
            pool_names = board_origin.get(board) or set()
            board_name = board[1].split("/", 1)[0] if board[0] == "workday" else board[1]
            for company in pool_names | set(linkedin_titles):
                similarity = max(
                    name_similarity(company, info.get("name") or ""),
                    name_similarity(company, board_name),
                )
                overlap = company in pool_names and title_overlap(linkedin_titles[company], info["all_titles"])
                if similarity >= 0.8 or overlap:
                    score = (overlap, similarity)
                    if best is None or score > best[0]:
                        best = (score, company)
            if best:
                linkedin_match[board] = best[1]

        with ThreadPoolExecutor(8) as pool:
            api_records = list(pool.map(
                lambda board: self._checked_record(board, verified[board], linkedin_match, board_origin, site_hints),
                boards_to_check,
            ))

        accepted = [record for record in api_records if not record.get("reason")]
        rejected = [record for record in api_records if record.get("reason")]
        accepted, rejected = self._dedupe_accepted(accepted, rejected)
        for record in accepted:
            record["status"] = "accepted"
        for record in rejected:
            record["status"] = "rejected"

        company_stats = (0, 0)
        if accepted and not self.dry_run:
            today = datetime.now(timezone.utc).date().isoformat()
            rows = [{
                "Name": record["name"],
                "Website": record["website"],
                "Career Page": record["career_page"],
                "Label": record["ats"],
                "Description": (
                    f"Added by ATS discovery on {today}: {record['ats']} board with "
                    f"{record['scraper_berlin_eng']} Berlin engineering roles at verification."
                ),
                "Active": True,
            } for record in accepted]
            company_stats = self.storage.upsert_companies(pd.DataFrame(rows), skip_existing_boards=True)

        if not self.dry_run:
            for record in api_records:
                # Dedupe may have changed an accepted result into a rejected row.
                self.store.save_board(record)

        finished = datetime.now(timezone.utc)
        report = {
            "accepted": accepted,
            "rejected": rejected,
            "tavily_spent": {
                "discovery": self.spent["DISCOVERY"],
                "resolve": self.spent["RESOLVE"],
                "budget_discovery": self.budgets["DISCOVERY"],
                "budget_resolve": self.budgets["RESOLVE"],
            },
            "discovery_log": discovery_log,
            "companies_upserted": company_stats[0],
            "companies_skipped": company_stats[1],
            "started": started.isoformat(),
            "finished": finished.isoformat(),
        }
        return report


def _nonnegative_budget(value: str) -> int:
    budget = int(value)
    if budget < 0:
        raise argparse.ArgumentTypeError("budget must be non-negative")
    return budget


def _summary(report: dict) -> str:
    reasons = collections.Counter(row.get("reason") for row in report["rejected"])
    reason_text = ", ".join(f"{reason}: {count}" for reason, count in sorted(reasons.items())) or "none"
    return (
        f"ATS discovery: accepted {len(report['accepted'])}, rejected {len(report['rejected'])}; "
        f"catalog {report['companies_upserted']} inserted, {report['companies_skipped']} skipped; "
        f"Tavily spend discovery {report['tavily_spent']['discovery']}/"
        f"{report['tavily_spent']['budget_discovery']}, resolve {report['tavily_spent']['resolve']}/"
        f"{report['tavily_spent']['budget_resolve']}; rejected reasons: {reason_text}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Discover and verify Berlin engineering ATS boards")
    parser.add_argument("--budget-discovery", type=_nonnegative_budget, default=150)
    parser.add_argument("--budget-resolve", type=_nonnegative_budget, default=150)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    storage = PostgresJobStorage()
    started = datetime.now(timezone.utc)
    with storage.connect() as connection:
        runner = DiscoveryRunner(
            storage,
            DiscoveryStore(connection),
            budget_discovery=args.budget_discovery,
            budget_resolve=args.budget_resolve,
            dry_run=args.dry_run,
        )
        report = runner.run(started)
    summary = _summary(report)
    report["summary"] = summary
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(summary, flush=True)
    return 0

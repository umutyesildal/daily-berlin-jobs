from .crawler_logger import CrawlerLogger
from .scrapers.done.amazon_scraper import AmazonScraper
from .scrapers.done.ashby_scraper import AshbyScraper
from .scrapers.done.bamboohr_scraper import BambooHRScraper
from .scrapers.done.capgemini_scraper import CapgeminiScraper
from .scrapers.done.consider_scraper import ConsiderScraper
from .scrapers.done.gem_scraper import GemScraper
from .scrapers.done.getro_scraper import GetroScraper
from .scrapers.done.greenhouse_scraper import GreenhouseScraper
from .scrapers.done.hibob_scraper import HiBobScraper
from .scrapers.done.join_scraper import JoinScraper
from .scrapers.done.lever_scraper import LeverScraper
from .scrapers.done.lingoda_scraper import LingodaScraper
from .scrapers.done.microsoft_scraper import MicrosoftScraper
from .scrapers.done.paypal_scraper import PayPalScraper
from .scrapers.done.personio_scraper import PersonioScraper
from .scrapers.done.recruitee_scraper import RecruiteeScraper
from .scrapers.done.rippling_scraper import RipplingScraper
from .scrapers.done.smartrecruiters_scraper import SmartRecruitarsScraper
from .scrapers.done.stripe_scraper import StripeScraper
from .scrapers.done.traderepublic_scraper import TradeRepublicScraper
from .scrapers.done.wipro_scraper import WiproScraper
from .scrapers.done.workable_scraper import WorkableScraper
from .scrapers.done.workday_scraper import WorkdayScraper
from .scrapers.done.phenom_scraper import PhenomScraper
from .scrapers.done.forto_scraper import FortoScraper
from .scrapers.done.frequenz_scraper import FrequenzScraper
from .scrapers.done.softgarden_scraper import SoftgardenScraper
from .scrapers.done.teamtailor_scraper import TeamtailorScraper
from .scrapers.done.zalando_scraper import ZalandoScraper
from .scrapers.done.linkedin_guest_jobs import LinkedInGuestJobsClient
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import re
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urlparse
import pandas as pd
import os
from .report_generator import ReportGenerator
from .job_taxonomy import classify_role


def _safe_source_health_error(error: object) -> Optional[str]:
    if error is None:
        return None
    message = str(error)
    for name, value in os.environ.items():
        if value and any(token in name.upper() for token in (
            "KEY", "TOKEN", "SECRET", "PASSWORD", "DATABASE", "CREDENTIAL", "PAT",
        )):
            message = message.replace(value, "[redacted]")
    message = re.sub(r"https?://[^\s\"'<>]+", "[redacted URL]", message, flags=re.IGNORECASE)
    message = re.sub(
        r"(?i)\b(?:authorization|bearer)\s*[:=]?\s*\S+",
        "[redacted credential]",
        message,
    )
    message = re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*[^&\s]+",
        r"\1=[redacted]",
        message,
    )
    return message[:300] or None


def _source_id_from_row(row: pd.Series) -> Optional[int]:
    value = row.get("Source ID")
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class DomainRateLimiter:
    """Simple per-domain rate limiter to enforce minimum delay between requests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_request = {}

    def wait(self, domain: str, delay: float):
        """Block until the minimum delay has passed for the given domain."""
        domain_key = domain or 'global'

        if delay <= 0:
            with self._lock:
                self._last_request[domain_key] = time.monotonic()
            return

        while True:
            with self._lock:
                last_request = self._last_request.get(domain_key)
                now = time.monotonic()
                if last_request is None or (now - last_request) >= delay:
                    self._last_request[domain_key] = now
                    return
                wait_time = delay - (now - last_request)

            if wait_time > 0:
                time.sleep(wait_time)

class JobCrawlerController:
    """Main controller for orchestrating job scraping across ATS platforms"""
    
    # Map label names to scraper classes
    SCRAPER_MAP = {
        'amazon': AmazonScraper,
        'amazonjobs': AmazonScraper,
        'ashbyhq': AshbyScraper,
        'ashby': AshbyScraper,
        'bamboohr': BambooHRScraper,
        'capgemini': CapgeminiScraper,
        'consider': ConsiderScraper,
        'gem': GemScraper,
        'getro': GetroScraper,
        'greenhouse': GreenhouseScraper,
        'hibob': HiBobScraper,
        'bob': HiBobScraper,
        'join': JoinScraper,
        'lever': LeverScraper,
        'lingoda': LingodaScraper,
        'pinpointhq': LingodaScraper,
        'microsoft': MicrosoftScraper,
        'paypal': PayPalScraper,
        'eightfold': PayPalScraper,
        'personio': PersonioScraper,
        'recruitee': RecruiteeScraper,
        'rippling': RipplingScraper,
        'smartrecruiters': SmartRecruitarsScraper,
        'stripe': StripeScraper,
        'traderepublic': TradeRepublicScraper,
        'wipro': WiproScraper,
        'workable': WorkableScraper,
        'workday': WorkdayScraper,
        'myworkdayjobs': WorkdayScraper,
        'phenom': PhenomScraper,
        'teamtailor': TeamtailorScraper,
        'softgarden': SoftgardenScraper,
        'zalando': ZalandoScraper,
        'custom-zalando': ZalandoScraper,
        'frequenz': FrequenzScraper,
        'custom-frequenz': FrequenzScraper,
        'forto': FortoScraper,
        'custom-forto': FortoScraper,
        'linkedin': LinkedInGuestJobsClient,
    }
    
    def __init__(self, delay: float = 2.0, output_dir: str = 'data', max_workers: int = None):
        self.delay = delay
        self.output_dir = output_dir
        self.failed_companies = []  # Track failed companies
        self.no_jobs_companies = []  # Track companies with no jobs (separate from failures)
        self.source_health_results = []
        self.rate_limit_issues = []  # Track rate limiting issues
        self.timing_stats = []  # Track timing for each company
        self.request_stats = {
            'total_requests': 0,
            'rate_limited': 0,
            'timeouts': 0,
            'connection_errors': 0,
            'successful': 0
        }

        self.max_workers = max_workers if max_workers and max_workers > 0 else max(1, min(8, (os.cpu_count() or 4)))
        self._rate_limiter = DomainRateLimiter()
        self._request_lock = threading.Lock()
        self.run_start_time: Optional[float] = None
        self.run_end_time: Optional[float] = None

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
    
    def log_request_issue(self, company_name: str, issue_type: str, details: str, status_code: int = None):
        """Log rate limiting and request issues"""
        issue_data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'company': company_name,
            'issue_type': issue_type,
            'details': details,
            'status_code': status_code,
            'current_delay': self.delay
        }

        with self._request_lock:
            if issue_type != 'success':
                self.rate_limit_issues.append(issue_data)
            self.request_stats['total_requests'] += 1

            if issue_type == 'rate_limited':
                self.request_stats['rate_limited'] += 1
                CrawlerLogger.rate_limited_request(company_name, status_code, self.delay)
            elif issue_type == 'timeout':
                self.request_stats['timeouts'] += 1
                CrawlerLogger.timeout_request(company_name, details)
            elif issue_type == 'connection_error':
                self.request_stats['connection_errors'] += 1
                CrawlerLogger.connection_error_request(company_name, details)
            elif issue_type == 'success':
                self.request_stats['successful'] += 1
            else:
                # Treat unknown error types as generic warnings
                self.request_stats['connection_errors'] += 1
                CrawlerLogger.warning_message(f"  ⚠️  Request issue for {company_name}: {details}")
    
    def should_increase_delay(self) -> bool:
        """Check if delay should be increased based on error rate"""
        total = self.request_stats['total_requests']
        if total < 5:  # Need some data first
            return False
        
        error_rate = (self.request_stats['rate_limited'] + self.request_stats['timeouts']) / total
        return error_rate > 0.2  # If >20% errors, suggest increase
    
    def log_company_timing(self, company_name: str, elapsed_time: float, job_count: int, status: str):
        """Log timing data for each company"""
        timing_data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'company': company_name,
            'elapsed_time': elapsed_time,
            'job_count': job_count,
            'jobs_per_second': job_count / elapsed_time if elapsed_time > 0 else 0,
            'status': status  # 'success', 'failed', 'timeout', 'error'
        }
        
        self.timing_stats.append(timing_data)
        
        # Log timing warnings
        if elapsed_time > 30:  # More than 30 seconds
            CrawlerLogger.slow_company_warning(company_name, elapsed_time, job_count)
        elif elapsed_time > 60:  # More than 1 minute
            CrawlerLogger.very_slow_company_warning(company_name, elapsed_time)
    
    def get_slow_companies(self, threshold: float = 20.0) -> list:
        """Get companies that took longer than threshold seconds"""
        return [stat for stat in self.timing_stats if stat['elapsed_time'] > threshold]
    
    def get_timing_summary(self) -> dict:
        """Get timing summary statistics"""
        if not self.timing_stats:
            return {}
        
        times = [stat['elapsed_time'] for stat in self.timing_stats]
        job_counts = [stat['job_count'] for stat in self.timing_stats]
        total_companies = len(self.timing_stats)

        total_scrape_time = sum(times)
        if self.run_start_time is not None:
            end_time = self.run_end_time if self.run_end_time is not None else time.time()
            total_scrape_time = max(0.0, end_time - self.run_start_time)

        avg_time = total_scrape_time / total_companies if total_companies else 0.0

        return {
            'total_companies': total_companies,
            'avg_time': avg_time,
            'max_time': max(times),
            'min_time': min(times),
            'total_time': total_scrape_time,
            'avg_jobs': sum(job_counts) / len(job_counts) if job_counts else 0,
            'total_jobs': sum(job_counts)
        }
    
    def get_delay_recommendation(self) -> float:
        """Get recommended delay based on current error rates"""
        if self.should_increase_delay():
            if self.request_stats['rate_limited'] > self.request_stats['timeouts']:
                return min(self.delay * 2.0, 5.0)  # Double delay for rate limits, max 5s
            else:
                return min(self.delay * 1.5, 3.0)  # 1.5x for other errors, max 3s
        return self.delay
    
    def save_timing_history(self):
        """Save timing data for future comparison"""
        timing_file = os.path.join(self.output_dir, 'timing_history.json')
        
        if not self.timing_stats:
            return
            
        # Load existing history
        history = []
        if os.path.exists(timing_file):
            try:
                import json
                with open(timing_file, 'r') as f:
                    history = json.load(f)
            except:
                history = []
        
        # Add current run data
        summary = self.get_timing_summary()
        avg_time = summary.get('avg_time', 0.0) if summary else 0.0
        total_time = summary.get('total_time', 0.0) if summary else 0.0

        current_run = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_companies': len(self.timing_stats),
            'avg_time': avg_time,
            'total_time': total_time,
            'companies': self.timing_stats
        }
        
        history.append(current_run)
        
        # Keep only last 30 runs
        history = history[-30:]
        
        # Save back
        try:
            import json
            with open(timing_file, 'w') as f:
                json.dump(history, f, indent=2)
            CrawlerLogger.info_message(f"💾 Timing history saved to: timing_history.json")
        except Exception as e:
            CrawlerLogger.warning_message(f"⚠️  Could not save timing history: {e}")
    
    
    def get_timing_trends(self) -> dict:
        """Get timing trends from historical data"""
        timing_file = os.path.join(self.output_dir, 'timing_history.json')
        
        if not os.path.exists(timing_file):
            return {}
            
        try:
            import json
            with open(timing_file, 'r') as f:
                history = json.load(f)
            
            if len(history) < 2:
                return {}
            
            # Compare last two runs
            current = history[-1]
            previous = history[-2]
            
            return {
                'previous_avg': previous['avg_time'],
                'current_avg': current['avg_time'],
                'trend': 'slower' if current['avg_time'] > previous['avg_time'] * 1.2 else 
                        'faster' if current['avg_time'] < previous['avg_time'] * 0.8 else 'stable',
                'change_percent': ((current['avg_time'] - previous['avg_time']) / previous['avg_time']) * 100
            }
        except:
            return {}
    
    
    def _extract_domain_name(self, url: str) -> str:
        """Extract clean domain name from URL for display"""
        if pd.isna(url) or not url:
            return 'Unknown'
        
        try:
            # Remove protocol
            domain = url.replace('https://', '').replace('http://', '')
            # Remove www.
            domain = domain.replace('www.', '')
            # Take first part before /
            domain = domain.split('/')[0]
            # Capitalize first letter
            domain = domain.split('.')[0].capitalize()
            return domain
        except:
            return url
    
    def _resolve_scraper_class(self, label: str):
        """Return the scraper class for the provided label."""
        if pd.isna(label) or not label:
            return None

        raw_label = label.lower().strip().replace(' ', '')
        if raw_label in self.SCRAPER_MAP:
            return self.SCRAPER_MAP[raw_label]

        normalized_label = raw_label.replace('-', '')

        if normalized_label in self.SCRAPER_MAP:
            return self.SCRAPER_MAP[normalized_label]

        matches = []
        for key, scraper_class in self.SCRAPER_MAP.items():
            normalized_key = key.lower().strip().replace(' ', '').replace('-', '')
            if normalized_key in normalized_label or normalized_label in normalized_key:
                matches.append((len(key), scraper_class))

        if matches:
            matches.sort(key=lambda item: item[0])
            return matches[0][1]

        return None

    def get_scraper(self, label: str):
        """Get appropriate scraper instance based on label"""
        scraper_class = self._resolve_scraper_class(label)
        if not scraper_class:
            return None

        scraper = scraper_class()
        if hasattr(scraper, 'delay'):
            scraper.delay = self.delay
        return scraper

    def _get_rate_limit_key(self, url: str) -> str:
        """Generate a domain key for rate limiting purposes."""
        if pd.isna(url) or not url:
            return 'global'

        parsed = urlparse(url)
        if parsed.netloc:
            return parsed.netloc.lower()

        cleaned = url.split('/')[0].strip().lower()
        return cleaned or 'global'

    def _normalize_jobs_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Keep legacy Company and scraper Company Name columns in sync."""
        df = df.copy()

        if 'Company' not in df.columns and 'Company Name' in df.columns:
            df['Company'] = df['Company Name']
        elif 'Company Name' not in df.columns and 'Company' in df.columns:
            df['Company Name'] = df['Company']
        elif 'Company' in df.columns and 'Company Name' in df.columns:
            df['Company'] = df['Company'].fillna(df['Company Name'])
            df['Company Name'] = df['Company Name'].fillna(df['Company'])

        preferred_columns = [
            'Company',
            'Company Name',
            'Job Title',
            'Location',
            'Job Link',
            'Job Description',
            'Employment Type',
            'Department',
            'Posted Date',
            'Company Description',
            'Remote',
            'Label',
            'ATS'
        ]
        ordered_columns = [col for col in preferred_columns if col in df.columns]
        remaining_columns = [col for col in df.columns if col not in ordered_columns]
        return df[ordered_columns + remaining_columns]

    def _scrape_company_task(self, task: Dict) -> Dict:
        """Worker task for scraping a single company."""
        company_name = task['company_name']
        career_page = task['career_page']
        description = task['description']
        label = task['label']
        scraper_class = task['scraper_class']
        rate_limit_key = task['rate_limit_key']

        scraper = scraper_class()
        if hasattr(scraper, 'delay'):
            scraper.delay = self.delay

        self._rate_limiter.wait(rate_limit_key, self.delay)
        start_time = time.time()

        try:
            jobs = scraper.scrape_jobs(
                url=career_page,
                company_name=company_name,
                company_description=description,
                label=label
            ) or []

            elapsed = time.time() - start_time
            return {
                'status': 'success',
                'jobs': jobs,
                'elapsed': elapsed,
                'company_name': company_name
            }

        except KeyboardInterrupt:
            raise
        except requests.exceptions.HTTPError as e:
            elapsed = time.time() - start_time
            status_code = e.response.status_code if hasattr(e, 'response') and e.response is not None else None
            issue_type = 'rate_limited' if status_code in [429, 403, 503] else 'http_error'
            return {
                'status': 'error',
                'error': e,
                'issue_type': issue_type,
                'status_code': status_code,
                'elapsed': elapsed,
                'company_name': company_name
            }
        except requests.exceptions.Timeout as e:
            elapsed = time.time() - start_time
            return {
                'status': 'error',
                'error': e,
                'issue_type': 'timeout',
                'status_code': None,
                'elapsed': elapsed,
                'company_name': company_name
            }
        except requests.exceptions.ConnectionError as e:
            elapsed = time.time() - start_time
            return {
                'status': 'error',
                'error': e,
                'issue_type': 'connection_error',
                'status_code': None,
                'elapsed': elapsed,
                'company_name': company_name
            }
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                'status': 'error',
                'error': e,
                'issue_type': 'error',
                'status_code': None,
                'elapsed': elapsed,
                'company_name': company_name
            }
    
    def _load_existing_jobs_by_company(self) -> Dict[str, set]:
        """
        Load existing job links from the CSV file, grouped by company.
        
        Returns:
            Dict[str, set]: {company_name: set(job_links)}
            
        Performance: ~1000x faster job checking per company
        (50 vs 50,000 comparisons)
        
        TODO: Add closed jobs detection here in future
        """
        all_jobs_file = os.path.join(self.output_dir, 'all_jobs.csv')
        existing_jobs_by_company = {}
        total_existing_jobs = 0
        
        if os.path.exists(all_jobs_file):
            try:
                existing_df = pd.read_csv(all_jobs_file, encoding='utf-8', low_memory=False, dtype=str)
                existing_df = self._normalize_jobs_dataframe(existing_df)
                if 'Job Link' in existing_df.columns and 'Company' in existing_df.columns:
                    # Group jobs by company
                    for _, row in existing_df.iterrows():
                        company = row.get('Company', 'Unknown')
                        job_link = row.get('Job Link')
                        
                        if pd.notna(job_link) and pd.notna(company):
                            if company not in existing_jobs_by_company:
                                existing_jobs_by_company[company] = set()
                            existing_jobs_by_company[company].add(job_link)
                            total_existing_jobs += 1
                
                CrawlerLogger.debug_existing_jobs(total_existing_jobs)
                CrawlerLogger.info_message(f"📊 Jobs grouped by {len(existing_jobs_by_company)} companies for faster lookup")
            except Exception as e:
                CrawlerLogger.debug_load_error(e)
        
        return existing_jobs_by_company

    def _detect_closed_jobs(self, company_name: str, previous_jobs: set, current_jobs: List[Dict]) -> set:
        """
        Detect jobs that were closed/removed for a specific company.
        
        Args:
            company_name: Name of the company
            previous_jobs: Set of previous job links for this company
            current_jobs: List of current job dictionaries from scraper
            
        Returns:
            set: Job links that were present before but not now (closed jobs)
            
        TODO: Implement closed jobs tracking
        - Save closed jobs with date closed
        - Calculate how long jobs were open
        - Add to reporting
        """
        current_job_links = {job.get('Job Link') for job in current_jobs if job.get('Job Link')}
        closed_job_links = previous_jobs - current_job_links
        
        # TODO: Implement full closed jobs tracking here
        # Example structure:
        # if closed_job_links:
        #     closed_jobs_data = []
        #     for job_link in closed_job_links:
        #         closed_jobs_data.append({
        #             'Company': company_name,
        #             'Job Link': job_link,
        #             'Date Closed': datetime.now().strftime('%Y-%m-%d'),
        #             'Status': 'Closed'
        #         })
        #     self._save_closed_jobs(closed_jobs_data)
        
        return closed_job_links

    def _load_existing_jobs(self) -> set:
        """
        Legacy method - Load all existing job links as single set
        Kept for backward compatibility, but slower than company-specific lookup
        """
        company_jobs = self._load_existing_jobs_by_company()
        all_jobs = set()
        for company_links in company_jobs.values():
            all_jobs.update(company_links)
        return all_jobs
    
    def scrape_company(self, row: pd.Series) -> List[Dict]:
        """
        Scrape jobs for a single company
        
        Args:
            row: DataFrame row with company data
            
        Returns:
            List of job dictionaries
        """
        name = row.get('Name', '')
        website = row.get('Website', '')
        career_page = row.get('Career Page', '')
        description = row.get('Description', '')
        label = row.get('Label', '')
        
        CrawlerLogger.company_start(name, career_page, label)
        
        # Validate input
        if pd.isna(career_page) or not career_page:
            CrawlerLogger.no_career_page_warning(name)
            return []
        
        if pd.isna(label) or not label:
            CrawlerLogger.no_label_warning(name)
            return []
        
        # Get appropriate scraper
        scraper = self.get_scraper(label)
        if not scraper:
            CrawlerLogger.scraper_not_found_error(label)
            return []
        
        # Scrape jobs
        try:
            jobs = scraper.scrape_jobs(
                url=career_page,
                company_name=name,
                company_description=description,
                label=label
            )
            
            CrawlerLogger.jobs_found(len(jobs), name)
            return jobs
            
        except Exception as e:
            CrawlerLogger.scraping_error(name, _safe_source_health_error(e) or "Scraping error")
            return []
    
    def _record_source_health(
        self,
        source_id: Optional[int],
        status: str,
        job_count: int = 0,
        berlin_engineering_count: int = 0,
        error: object = None,
        status_code: Optional[int] = None,
    ) -> None:
        if source_id is None:
            return
        try:
            status_code = int(status_code) if status_code is not None else None
        except (TypeError, ValueError):
            status_code = None
        self.source_health_results.append({
            "source_id": int(source_id),
            "status": status,
            "job_count": max(0, int(job_count)),
            "berlin_engineering_count": max(0, int(berlin_engineering_count)),
            "error": _safe_source_health_error(error),
            "status_code": status_code,
        })

    def process_companies(self, df: pd.DataFrame, limit: int = None):

        # Compare old data and backup
        self.compare_and_backup()
        self.source_health_results = []

        self.run_start_time = time.time()
        self.run_end_time = None

        # Load existing jobs grouped by company for faster lookup
        existing_jobs_by_company = self._load_existing_jobs_by_company()

        # Keep legacy single set for global operations (reports, etc.)
        existing_jobs = self._load_existing_jobs()

        companies_to_process = df.head(limit) if limit else df

        all_jobs = []
        stats = {
            'total_companies': len(df) if limit is None else min(limit, len(df)),
            'successful': 0,
            'failed': 0,
            'total_jobs': 0,
            'new_jobs': 0
        }

        CrawlerLogger.startup_header(stats['total_companies'], len(existing_jobs))

        tasks = []

        for idx, row in companies_to_process.iterrows():
            company_name = row.get('Name', 'Unknown')
            career_page = row.get('Career Page', '')
            description = row.get('Description', 'N/A')
            label = row.get('Label', 'unknown')
            source_id = _source_id_from_row(row)

            CrawlerLogger.company_start(idx, stats['total_companies'], company_name, label)

            if pd.isna(career_page) or not career_page:
                self._record_source_health(source_id, 'error', error='Missing career page')
                CrawlerLogger.warning_no_career_page(company_name)
                stats['failed'] += 1
                self.failed_companies.append({'Company': company_name, 'Reason': 'No career page'})
                CrawlerLogger.progress_update(stats['successful'], stats['failed'], stats['total_jobs'], stats['new_jobs'])
                continue

            if pd.isna(label) or not label:
                self._record_source_health(source_id, 'error', error='Missing ATS platform')
                CrawlerLogger.warning_no_ats_platform()
                stats['failed'] += 1
                self.failed_companies.append({'Company': company_name, 'Reason': 'No ATS platform'})
                CrawlerLogger.progress_update(stats['successful'], stats['failed'], stats['total_jobs'], stats['new_jobs'])
                continue

            scraper_class = self._resolve_scraper_class(label)
            if not scraper_class:
                self._record_source_health(source_id, 'error', error=f'No scraper for {label}')
                CrawlerLogger.warning_no_scraper(label)
                stats['failed'] += 1
                self.failed_companies.append({'Company': company_name, 'Reason': f'No scraper for {label}'})
                CrawlerLogger.progress_update(stats['successful'], stats['failed'], stats['total_jobs'], stats['new_jobs'])
                continue

            tasks.append({
                'index': idx,
                'company_name': company_name,
                'career_page': career_page,
                'description': description,
                'label': label,
                'source_id': source_id,
                'scraper_class': scraper_class,
                'rate_limit_key': self._get_rate_limit_key(career_page)
            })

        if tasks:
            max_workers = min(len(tasks), self.max_workers)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {
                    executor.submit(self._scrape_company_task, task): task for task in tasks
                }

                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    company_name = task['company_name']

                    try:
                        result = future.result()
                    except Exception as exc:
                        elapsed_time = 0.0
                        safe_error = _safe_source_health_error(exc) or "Unexpected scraping error"
                        self._record_source_health(task.get('source_id'), 'error', error=safe_error)
                        self.log_company_timing(company_name, elapsed_time, 0, 'error')
                        CrawlerLogger.company_error(safe_error, elapsed_time)
                        stats['failed'] += 1
                        self.failed_companies.append({'Company': company_name, 'Reason': f'Unexpected error: {safe_error[:80]}'})
                        CrawlerLogger.progress_update(stats['successful'], stats['failed'], stats['total_jobs'], stats['new_jobs'])
                        continue

                    status = result.get('status')
                    elapsed_time = result.get('elapsed', 0.0)
                    jobs = result.get('jobs') or []
                    issue_type = result.get('issue_type')
                    status_code = result.get('status_code')
                    error = result.get('error')

                    if status == 'success':
                        self.log_request_issue(company_name, 'success', 'Job scraping successful')

                        job_count = len(jobs)
                        berlin_engineering_count = sum(
                            1
                            for job in jobs
                            if 'berlin' in str(job.get('Location') or '').casefold()
                            and classify_role({'Job Title': job.get('Job Title', '')})
                        )
                        self._record_source_health(
                            task.get('source_id'),
                            'ok' if job_count else 'empty',
                            job_count=job_count,
                            berlin_engineering_count=berlin_engineering_count,
                        )
                        if job_count:
                            self.log_company_timing(company_name, elapsed_time, job_count, 'success')
                            CrawlerLogger.jobs_found(job_count, company_name)

                            company_existing_jobs = existing_jobs_by_company.get(company_name)
                            if company_existing_jobs is None:
                                company_existing_jobs = set()
                                existing_jobs_by_company[company_name] = company_existing_jobs

                            new_jobs = [j for j in jobs if j.get('Job Link') not in company_existing_jobs]

                            for job in new_jobs:
                                job_link = job.get('Job Link')
                                if job_link:
                                    existing_jobs.add(job_link)
                                    company_existing_jobs.add(job_link)

                            stats['new_jobs'] += len(new_jobs)
                            all_jobs.extend(jobs)
                            stats['total_jobs'] += job_count
                            stats['successful'] += 1

                            new_job_titles = [job.get('Job Title', 'Untitled') for job in new_jobs]
                            CrawlerLogger.company_success(job_count, len(new_jobs), elapsed_time,
                                                          company_name, new_job_titles)
                            CrawlerLogger.warning_slow_company(company_name, elapsed_time, job_count)
                            if elapsed_time > 60:
                                self.failed_companies.append({
                                    'Company': company_name,
                                    'Reason': f'Slow performance: {elapsed_time:.1f}s for {job_count} jobs'
                                })
                        else:
                            self.log_company_timing(company_name, elapsed_time, 0, 'no_jobs')
                            CrawlerLogger.company_no_jobs(elapsed_time)

                            if elapsed_time > 60:
                                CrawlerLogger.warning_slow_company(company_name, elapsed_time, 0)
                                self.failed_companies.append({
                                    'Company': company_name,
                                    'Reason': f'Possible scraping issue: {elapsed_time:.1f}s with no jobs'
                                })
                                stats['failed'] += 1
                            else:
                                self.no_jobs_companies.append({'Company': company_name, 'Time': f'{elapsed_time:.1f}s'})
                                stats['successful'] += 1

                    else:
                        issue_type = issue_type or 'connection_error'
                        if issue_type in ('http_error', 'error'):
                            issue_type = 'connection_error'
                        message = _safe_source_health_error(error) or 'Unknown error'
                        self._record_source_health(
                            task.get('source_id'),
                            'error',
                            error=message,
                            status_code=status_code,
                        )
                        self.log_request_issue(company_name, issue_type, message, status_code)
                        self.log_company_timing(company_name, elapsed_time, 0, 'error')

                        if error is not None:
                            CrawlerLogger.scraping_error(company_name, message)
                        CrawlerLogger.company_error(message, elapsed_time)

                        if elapsed_time > 60:
                            reason = f'Error + slow performance: {elapsed_time:.1f}s - {message[:50]}'
                        else:
                            reason = f'Error: {message[:80]}'

                        stats['failed'] += 1
                        self.failed_companies.append({'Company': company_name, 'Reason': reason})

                    CrawlerLogger.progress_update(stats['successful'], stats['failed'], stats['total_jobs'], stats['new_jobs'])

                    if self.should_increase_delay():
                        recommended_delay = self.get_delay_recommendation()
                        if recommended_delay > self.delay:
                            CrawlerLogger.warning_rate_limiting(recommended_delay, self.delay)

        self.save_jobs(all_jobs)

        # Final summary
        self.run_end_time = time.time()
        timing_summary = self.get_timing_summary()
        timing_trends = self.get_timing_trends()

        CrawlerLogger.completion_summary(stats['successful'], stats['failed'],
                                         stats['total_jobs'], stats['new_jobs'],
                                         len(self.no_jobs_companies), self.output_dir)

        CrawlerLogger.timing_summary(timing_summary, timing_trends)

        # Save timing history for future comparisons
        self.save_timing_history()

        # Print companies with no jobs (normal, not failures)
        CrawlerLogger.no_jobs_companies_section(self.no_jobs_companies)

        # Print failed companies if any (actual problems)
        CrawlerLogger.failed_companies_section(self.failed_companies)

        # Print timing statistics if any
        slow_companies = self.get_slow_companies(20.0)  # Companies taking >20s
        CrawlerLogger.timing_statistics_section(timing_summary, timing_trends, slow_companies)

        # Print rate limiting issues if any
        if self.rate_limit_issues and self.should_increase_delay():
            recommended_delay = self.get_delay_recommendation()
        else:
            recommended_delay = None

        CrawlerLogger.rate_limiting_section(self.request_stats, self.rate_limit_issues,
                                            self.delay, recommended_delay)

        self.generate_comparison_report()

        return all_jobs
    
    def compare_and_backup(self):
        """Compare old and new job data, create backup, and generate report"""
        output_path = os.path.join(self.output_dir, 'all_jobs.csv')
        backup_path = os.path.join(self.output_dir, 'all_jobs_backup.csv')
        
        if not os.path.exists(output_path):
            CrawlerLogger.no_previous_data()
            return
        
        try:
            old_df = pd.read_csv(output_path, encoding='utf-8', low_memory=False, dtype=str)
            old_df = self._normalize_jobs_dataframe(old_df)
            
            if len(old_df) == 0:
                CrawlerLogger.empty_previous_file()
                return
            
            pd.DataFrame(old_df).to_csv(backup_path, index=False, encoding='utf-8')
            CrawlerLogger.backup_success(len(old_df))
            
        except Exception as e:
            CrawlerLogger.backup_error(e)
    
    def generate_comparison_report(self):
        """Generate comparison report between old and new job data"""
        output_path = os.path.join(self.output_dir, 'all_jobs.csv')
        backup_path = os.path.join(self.output_dir, 'all_jobs_backup.csv')
        
        if not os.path.exists(backup_path):
            return
        
        try:
            old_df = pd.read_csv(backup_path, encoding='utf-8', low_memory=False, dtype=str)
            new_df = pd.read_csv(output_path, encoding='utf-8', low_memory=False, dtype=str)
            old_df = self._normalize_jobs_dataframe(old_df)
            new_df = self._normalize_jobs_dataframe(new_df)
            
            old_links = set(old_df['Job Link'].tolist())
            new_links = set(new_df['Job Link'].tolist())
            
            added_links = new_links - old_links
            removed_links = old_links - new_links
            unchanged_links = old_links & new_links
            
            added_jobs = new_df[new_df['Job Link'].isin(added_links)]
            removed_jobs = old_df[old_df['Job Link'].isin(removed_links)]
            
            student_new_jobs = added_jobs[
                (added_jobs['Job Title'].str.lower().str.contains('student|intern|praktikum', na=False)) &
                (added_jobs['Location'].str.lower().str.contains('berlin|germany|deutschland', na=False))
            ]
            
            student_removed_jobs = removed_jobs[
                (removed_jobs['Job Title'].str.lower().str.contains('student|intern|praktikum', na=False)) &
                (removed_jobs['Location'].str.lower().str.contains('berlin|germany|deutschland', na=False))
            ]
            
            # Import and use ReportGenerator
            
            # Get timing data
            timing_summary = self.get_timing_summary()
            timing_trends = self.get_timing_trends()
            slow_companies = self.get_slow_companies(20.0)
            
            # Generate and display report
            report_lines = ReportGenerator.get_report_lines(
                old_df=old_df,
                new_df=new_df,
                added_links=added_links,
                removed_links=removed_links,
                unchanged_links=unchanged_links,
                added_jobs=added_jobs,
                removed_jobs=removed_jobs,
                no_jobs_companies=self.no_jobs_companies,
                failed_companies=self.failed_companies,
                rate_limit_issues=self.rate_limit_issues,
                request_stats=self.request_stats,
                current_delay=self.delay,
                timing_summary=timing_summary,
                timing_trends=timing_trends,
                slow_companies=slow_companies,
                should_increase_delay=self.should_increase_delay(),
                delay_recommendation=self.get_delay_recommendation()
            )
            
            # Display report in console
            CrawlerLogger.display_report_lines(report_lines)
            
            # Save report to file
            report_filename = ReportGenerator.generate_job_changes_report(
                old_df=old_df,
                new_df=new_df,
                added_links=added_links,
                removed_links=removed_links,
                unchanged_links=unchanged_links,
                added_jobs=added_jobs,
                removed_jobs=removed_jobs,
                no_jobs_companies=self.no_jobs_companies,
                failed_companies=self.failed_companies,
                rate_limit_issues=self.rate_limit_issues,
                request_stats=self.request_stats,
                current_delay=self.delay,
                timing_summary=timing_summary,
                timing_trends=timing_trends,
                slow_companies=slow_companies,
                should_increase_delay=self.should_increase_delay(),
                delay_recommendation=self.get_delay_recommendation(),
                output_dir=self.output_dir
            )
            
            CrawlerLogger.report_saved(report_filename)
            
        except Exception as e:
            CrawlerLogger.comparison_report_error(e)
    
    def save_jobs(self, jobs: List[Dict]):
        """
        Save only this crawl's raw snapshot.

        PostgreSQL owns history and retention. Keeping cumulative raw crawler
        payloads made the local CSV grow without bound and is unnecessary.
        """
        output_path = os.path.join(self.output_dir, 'all_jobs.csv')
        empty_columns = [
            'Company', 'Company Name', 'Job Title', 'Location', 'Job Link',
            'Job Description', 'Employment Type', 'Department', 'Posted Date',
            'Company Description', 'Remote', 'Label', 'ATS'
        ]
        new_jobs_df = pd.DataFrame(jobs) if jobs else pd.DataFrame(columns=empty_columns)
        new_jobs_df = self._normalize_jobs_dataframe(new_jobs_df)
        
        links = new_jobs_df['Job Link'].fillna('').astype(str).str.strip()
        with_links = new_jobs_df[links.ne('')].drop_duplicates(subset=['Job Link'], keep='last')
        without_links = new_jobs_df[links.eq('')].drop_duplicates(
            subset=['Company Name', 'Job Title', 'Location'], keep='last'
        )
        snapshot_df = pd.concat([with_links, without_links], ignore_index=True, sort=False)
        snapshot_df.to_csv(output_path, index=False, encoding='utf-8')
        CrawlerLogger.debug_new_database(len(snapshot_df))

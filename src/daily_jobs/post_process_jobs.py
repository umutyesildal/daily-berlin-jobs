"""
Post-process collected jobs for canonical PostgreSQL or legacy Sheets outputs.

Creates the canonical Daily Berlin Jobs datasets. Every incoming row is
classified before the engineering-only public collections are written.
"""

import argparse
import os
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from .data_controller import DataController
from .discovery.text import norm_name
from .job_taxonomy import classify_job
from .linkedin_daily import collect_daily_linkedin_jobs, save_linkedin_daily_jobs


DEFAULT_SPREADSHEET = (
    "https://docs.google.com/spreadsheets/d/"
    "1sYI0IqzXp_W19eAYDCdC46ZjzrWqW5fwHfY0sAzUxKw/"
    "edit?gid=2095282077#gid=2095282077"
)

FIT_COLUMNS = ["Fit Score", "Fit Category", "Fit Reasons"]

EARLY_CAREER_PATTERN = re.compile(
    r"\b(working student|werkstudent|intern|internship|praktik|praktikum|"
    r"junior|entry[- ]?level|graduate|trainee|associate)\b",
    re.IGNORECASE,
)

ROLE_RULES = [
    ("early-career", re.compile(EARLY_CAREER_PATTERN.pattern, re.IGNORECASE), 5, "early-career title"),
    (
        "software",
        re.compile(
            r"\b(software|backend|back[- ]?end|frontend|front[- ]?end|full[- ]?stack|"
            r"web|developer|devops|platform engineer|cloud engineer|data engineer)\b",
            re.IGNORECASE,
        ),
        4,
        "software engineering match",
    ),
    (
        "automation-ai-data",
        re.compile(
            r"\b(automation|ai engineer|ai operations|machine learning|ml engineer|"
            r"data scientist|data engineering)\b",
            re.IGNORECASE,
        ),
        4,
        "automation/AI/data match",
    ),
    (
        "mobile",
        re.compile(r"\b(mobile|react native|flutter|ios engineer|android engineer)\b", re.IGNORECASE),
        3,
        "mobile app match",
    ),
]

ENGINEERING_TITLE_PATTERN = re.compile(
    r"\b(engineer|engineering|developer|devops|data scientist|machine learning|ml engineer|ai engineer)\b",
    re.IGNORECASE,
)

STACK_RULES = [
    (re.compile(r"\b(python|selenium|scrap(?:e|er|ing)|crawler)\b", re.IGNORECASE), 2, "Python/data collection"),
    (re.compile(r"\b(node\.?js|node|javascript|typescript|js|ts)\b", re.IGNORECASE), 2, "Node/JS"),
    (re.compile(r"\b(react|next\.?js|react native|flutter|dart)\b", re.IGNORECASE), 2, "React/mobile"),
    (re.compile(r"\b(n8n|make\.com|make|notion api|workflow|automation)\b", re.IGNORECASE), 2, "automation tools"),
    (re.compile(r"\b(ai|llm|prompt|machine learning|ml|nlp)\b", re.IGNORECASE), 2, "AI/ML"),
    (re.compile(r"\b(postgres|postgresql|sql|api|backend)\b", re.IGNORECASE), 1, "backend/API"),
    (re.compile(r"\b(blockchain|crypto|ethereum|web3)\b", re.IGNORECASE), 1, "crypto/Web3"),
]

SENIORITY_EXCLUDE_PATTERN = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|manager|head|director|vp|cto|chief|architect|expert|consultant|remote)\b",
    re.IGNORECASE,
)

NON_TARGET_PATTERN = re.compile(
    r"\b(sales engineer|solutions? engineer|customer success|support engineer|field engineer|"
    r"mechanical engineer|electrical engineer|civil engineer|process engineer|manufacturing engineer|"
    r"quality engineer|test engineer|engineer in test|qa engineer|security engineer|account executive|recruiter|"
    r"talent acquisition|marketing manager|product marketing|designer|product operations|product ops|"
    r"fund team|finance|sales|marketing|operations specialist|talent pool)\b",
    re.IGNORECASE,
)

NON_BERLIN_LOCATION_PATTERN = re.compile(
    r"\b(london|paris|munich|münchen|hamburg|sofia|tallinn|stockholm|poland|"
    r"kuala lumpur|remote|vilnius|cologne|köln|düsseldorf|frankfurt|amsterdam|"
    r"braunschweig|helsinki|lisbon|warsaw|prague|vienna|madrid|barcelona)\b",
    re.IGNORECASE,
)

EMPTY_JOB_VALUES = {"", "unknown", "n/a", "na", "none", "null", "-"}


def load_jobs(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False, dtype=str).fillna("")
    return DataController().normalize_jobs_dataframe(df)


def classify_jobs(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze every incoming job and attach the canonical public fields."""
    classified = DataController().normalize_jobs_dataframe(df.fillna(""))
    classification_rows = [classify_job(row) for row in classified.to_dict(orient="records")]
    for column in ["Role", "Level", "Work Mode", "Tech Stack", "Keywords", "Classification Version"]:
        classified[column] = [row[column] for row in classification_rows]
    return DataController().normalize_jobs_dataframe(classified)


def _row_text(row: pd.Series, columns) -> str:
    return " ".join(str(row.get(column, "")) for column in columns)


def _is_berlin_only_location(location: str) -> bool:
    location = str(location)
    if not re.search(r"\bberlin\b", location, re.IGNORECASE):
        return False

    if NON_BERLIN_LOCATION_PATTERN.search(location):
        return False

    if re.search(r"\bor\b|/|;", location, re.IGNORECASE):
        return False

    return True


def _score_related_job(row: pd.Series):
    title = str(row.get("Job Title", ""))
    title_department = _row_text(row, ["Job Title", "Department"])
    full_text = _row_text(row, ["Job Title", "Department", "Job Description", "Company Description"])

    if SENIORITY_EXCLUDE_PATTERN.search(title) or NON_TARGET_PATTERN.search(title_department):
        return None

    if not ENGINEERING_TITLE_PATTERN.search(title_department):
        return None

    score = 0
    categories = []
    reasons = []

    for category, pattern, points, reason in ROLE_RULES:
        if pattern.search(title_department):
            score += points
            categories.append(category)
            reasons.append(reason)

    for pattern, points, reason in STACK_RULES:
        if pattern.search(full_text):
            score += points
            reasons.append(reason)

    if _is_berlin_only_location(str(row.get("Location", ""))):
        score += 1
        reasons.append("Berlin")

    tech_categories = [category for category in categories if category != "early-career"]
    if score < 6 or not tech_categories:
        return None

    category = ", ".join(dict.fromkeys(categories))
    reason_text = "; ".join(dict.fromkeys(reasons[:5]))
    return score, category, reason_text


def filter_related_jobs(df: pd.DataFrame) -> pd.DataFrame:
    berlin_mask = df.get("Location", "").astype(str).map(_is_berlin_only_location)
    candidates = df[berlin_mask].copy()

    scored_rows = []
    for index, row in candidates.iterrows():
        fit = _score_related_job(row)
        if fit:
            score, category, reasons = fit
            scored_rows.append((index, score, category, reasons))

    if not scored_rows:
        empty = candidates.iloc[0:0].copy()
        for column in reversed(FIT_COLUMNS):
            empty.insert(0, column, "")
        return empty

    related_df = candidates.loc[[index for index, _, _, _ in scored_rows]].copy()
    score_by_index = {index: score for index, score, _, _ in scored_rows}
    category_by_index = {index: category for index, _, category, _ in scored_rows}
    reasons_by_index = {index: reasons for index, _, _, reasons in scored_rows}

    related_df["Fit Score"] = related_df.index.map(score_by_index)
    related_df["Fit Category"] = related_df.index.map(category_by_index)
    related_df["Fit Reasons"] = related_df.index.map(reasons_by_index)

    ordered_columns = FIT_COLUMNS + [column for column in related_df.columns if column not in FIT_COLUMNS]
    return related_df[ordered_columns].sort_values(
        by=["Fit Score", "Company", "Job Title"],
        ascending=[False, True, True],
    )


def filter_published_jobs(df: pd.DataFrame) -> pd.DataFrame:
    """Build the cumulative, consumer-facing Berlin engineering collection."""
    normalized = classify_jobs(df)
    title = normalized["Job Title"].astype(str).str.strip()
    company = normalized["Company Name"].astype(str).str.strip()
    location = normalized["Location"].astype(str).str.strip()
    role = normalized["Role"].astype(str).str.strip()

    valid = (
        location.str.contains(r"\bberlin\b", case=False, regex=True, na=False)
        & role.ne("")
        & ~title.str.casefold().isin(EMPTY_JOB_VALUES)
        & ~company.str.casefold().isin(EMPTY_JOB_VALUES)
        & ~location.str.casefold().isin(EMPTY_JOB_VALUES)
    )
    published = normalized[valid].copy()

    links = published["Job Link"].astype(str).str.strip()
    with_links = published[links.ne("")].drop_duplicates(subset=["Job Link"], keep="last")
    without_links = published[links.eq("")].drop_duplicates(
        subset=["Company Name", "Job Title", "Location"], keep="last"
    )
    return pd.concat([with_links, without_links], ignore_index=True, sort=False).fillna("")


def _published_date(value: str, today: date) -> Optional[date]:
    raw = str(value or "").strip()
    if raw.casefold() in EMPTY_JOB_VALUES:
        return None

    relative = re.fullmatch(r"(\d+)\s+(hour|hours|day|days)\s+ago", raw, re.IGNORECASE)
    if relative:
        amount = int(relative.group(1))
        return today - timedelta(days=amount if "day" in relative.group(2).casefold() else 0)

    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def filter_recent_published_jobs(df: pd.DataFrame, today: Optional[date] = None) -> pd.DataFrame:
    """Return only jobs whose posted date is today or yesterday in Berlin time."""
    today = today or datetime.now(ZoneInfo("Europe/Berlin")).date()
    allowed_dates = {today, today - timedelta(days=1)}
    posted_dates = df["Posted Date"].map(lambda value: _published_date(value, today))
    return df[posted_dates.isin(allowed_dates)].copy()


def merge_published_jobs(current_df: pd.DataFrame, previous_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Preserve the prior canonical collection and add this run's valid jobs."""
    frames = [previous_df, current_df] if previous_df is not None else [current_df]
    combined = pd.concat([frame for frame in frames if frame is not None], ignore_index=True, sort=False).fillna("")
    return filter_published_jobs(combined)


def _normalize_identity_value(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value).casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _job_identity(row: pd.Series):
    company = _normalize_identity_value(row.get("Company Name") or row.get("Company", ""))
    title = _normalize_identity_value(row.get("Job Title", ""))
    location = _normalize_identity_value(row.get("Location", ""))
    if not company or not title:
        return None
    return company, title, location


def find_daily_new_jobs(current_df: pd.DataFrame, previous_path: Optional[Path]) -> pd.DataFrame:
    if not previous_path or not previous_path.exists():
        return current_df.iloc[0:0].copy()

    previous_df = load_jobs(previous_path)
    previous_links = set(previous_df["Job Link"].dropna().astype(str))
    previous_identities = {
        identity
        for _, row in previous_df.iterrows()
        if (identity := _job_identity(row)) is not None
    }

    new_indexes = []
    seen_identities = set()
    for index, row in current_df.iterrows():
        job_link = str(row.get("Job Link", ""))
        identity = _job_identity(row)
        if job_link in previous_links or identity in previous_identities:
            continue
        if identity is not None and identity in seen_identities:
            continue

        new_indexes.append(index)
        if identity is not None:
            seen_identities.add(identity)

    return current_df.loc[new_indexes].copy()


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def _is_linkedin_row(row) -> bool:
    return any(
        pd.notna(row.get(column))
        and str(row.get(column)).strip().casefold() == "linkedin"
        for column in ("ATS", "Label")
    )


def _company_name(row) -> str:
    for column in ("Company Name", "Company", "company_name"):
        value = row.get(column)
        if pd.notna(value) and str(value).strip():
            return str(value)
    return ""


def prefer_ats_over_linkedin(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    linkedin_rows = dataframe.apply(_is_linkedin_row, axis=1)
    ats_companies = {
        norm_name(_company_name(row))
        for _, row in dataframe.loc[~linkedin_rows].iterrows()
        if _company_name(row)
    }
    keep = [
        not (_is_linkedin_row(row) and norm_name(_company_name(row)) in ats_companies)
        for _, row in dataframe.iterrows()
    ]
    return dataframe.loc[keep].copy()


def append_linkedin_daily_jobs(
    current_df: pd.DataFrame,
    output_path: Path,
    keywords,
    location: str,
    limit_per_query: int,
    delay: float,
    posted_within_seconds: int,
    related_only: bool,
) -> pd.DataFrame:
    linkedin_df = collect_daily_linkedin_jobs(
        keywords=keywords,
        location=location,
        limit_per_query=limit_per_query,
        delay=delay,
        posted_within_seconds=posted_within_seconds,
    )
    raw_count = len(linkedin_df)
    if related_only and not linkedin_df.empty:
        linkedin_df = filter_related_jobs(linkedin_df)

    save_linkedin_daily_jobs(linkedin_df, output_path)
    if related_only:
        print(f"LinkedIn daily jobs: {len(linkedin_df)} profile-fit rows from {raw_count} raw rows -> {output_path}")
    else:
        print(f"LinkedIn daily jobs: {len(linkedin_df)} raw rows -> {output_path}")

    if linkedin_df.empty:
        return current_df

    combined_df = pd.concat([current_df, linkedin_df], ignore_index=True, sort=False).fillna("")
    normalized_df = DataController().normalize_jobs_dataframe(combined_df)
    return prefer_ats_over_linkedin(normalized_df)


def upload_to_sheet(df: pd.DataFrame, spreadsheet: str, worksheet: str, max_upload_lines: int) -> bool:
    if max_upload_lines and max_upload_lines > 0:
        data_rows = max(max_upload_lines - 1, 0)
        upload_df = df.head(data_rows).copy()
    else:
        upload_df = df.copy()

    print(f"{worksheet} upload rows: {len(upload_df)} data rows + 1 header row")
    return DataController().export_dataframe_to_google_sheet(upload_df, spreadsheet, worksheet)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    data_dir = repo_root / "data"

    parser = argparse.ArgumentParser(description="Create related and daily-new job outputs")
    parser.add_argument("--current", default=str(data_dir / "all_jobs.csv"), help="Current all_jobs.csv path")
    parser.add_argument("--previous", default=str(data_dir / "last_pulled_jobs.csv"),
                        help="Previous pulled jobs baseline path")
    parser.add_argument("--related-output", default=str(data_dir / "related_jobs.csv"), help="Related jobs CSV output")
    parser.add_argument("--all-output", default=str(data_dir / "published_all_jobs.csv"),
                        help="Cumulative consumer-facing Berlin engineering jobs CSV output")
    parser.add_argument("--daily-output", default=str(data_dir / "daily_new_jobs.csv"), help="Daily new jobs CSV output")
    parser.add_argument("--linkedin-output", default=str(data_dir / "linkedin_daily_jobs.csv"),
                        help="LinkedIn daily query CSV output")
    parser.add_argument("--spreadsheet", default=DEFAULT_SPREADSHEET, help="Google spreadsheet URL or ID")
    parser.add_argument("--related-worksheet", default="Related Jobs", help="Related jobs worksheet name")
    parser.add_argument("--all-worksheet", default="All Jobs", help="All published jobs worksheet name")
    parser.add_argument("--daily-worksheet", default="Daily New Jobs", help="Daily new jobs worksheet name")
    parser.add_argument("--max-upload-lines", type=int,
                        help="Legacy cap for both worksheets, including the header row")
    parser.add_argument("--related-max-upload-lines", type=int, default=0,
                        help="Maximum Related Jobs worksheet rows, including the header row; 0 uploads all")
    parser.add_argument("--daily-max-upload-lines", type=int, default=0,
                        help="Maximum Daily New Jobs worksheet rows, including the header row; 0 uploads all")
    parser.add_argument("--no-update-baseline", action="store_true",
                        help="Do not replace the previous pulled jobs baseline after a successful run")
    parser.add_argument("--skip-upload", action="store_true", help="Only write local CSV files")
    parser.add_argument(
        "--storage-backend",
        choices=["sheets", "postgres", "dual"],
        default=os.getenv("STORAGE_BACKEND", "sheets"),
        help="Canonical publisher; dual temporarily writes PostgreSQL and Sheets",
    )
    parser.add_argument("--retention-days", type=int, default=30,
                        help="Delete canonical job rows older than this many days")
    parser.add_argument("--skip-daily-upload", action="store_true", help="Do not update the daily-new worksheet")
    parser.add_argument("--include-linkedin-daily", action="store_true",
                        help="Append recent LinkedIn engineering searches before filtering/uploading")
    parser.add_argument("--linkedin-keywords", nargs="*",
                        help="LinkedIn query keywords; defaults to the supported tech-engineering areas")
    parser.add_argument("--linkedin-location", default="Berlin, Germany", help="LinkedIn query location")
    parser.add_argument("--linkedin-limit-per-query", type=int, default=25,
                        help="Maximum LinkedIn jobs to fetch per keyword")
    parser.add_argument("--linkedin-delay", type=float, default=1.0,
                        help="Delay between LinkedIn guest requests")
    parser.add_argument("--linkedin-posted-within-seconds", type=int, default=86400,
                        help="LinkedIn posted-time filter in seconds; 86400 means last 24 hours")
    parser.add_argument("--linkedin-raw-daily", action="store_true",
                        help="Append raw LinkedIn daily results instead of profile-fit rows only")
    parser.add_argument("--linkedin-pre-scraped", default="",
                        help="Path to pre-scraped LinkedIn daily jobs CSV file to append instead of scraping live")

    args = parser.parse_args()

    related_max_upload_lines = args.related_max_upload_lines
    daily_max_upload_lines = args.daily_max_upload_lines
    if args.max_upload_lines is not None:
        related_max_upload_lines = args.max_upload_lines
        daily_max_upload_lines = args.max_upload_lines

    current_path = Path(args.current)
    previous_path = Path(args.previous) if args.previous else None

    current_df = load_jobs(current_path)
    if args.include_linkedin_daily:
        pre_scraped_path = Path(args.linkedin_pre_scraped) if args.linkedin_pre_scraped else None
        if pre_scraped_path and pre_scraped_path.exists():
            print(f"Loading pre-scraped LinkedIn daily jobs: {pre_scraped_path}")
            linkedin_df = load_jobs(pre_scraped_path)
            if not linkedin_df.empty:
                # Filter for profile fit if not raw
                if not args.linkedin_raw_daily:
                    linkedin_df = filter_related_jobs(linkedin_df)
                combined_df = pd.concat([current_df, linkedin_df], ignore_index=True, sort=False).fillna("")
                current_df = DataController().normalize_jobs_dataframe(combined_df)
                current_df = prefer_ats_over_linkedin(current_df)
        else:
            current_df = append_linkedin_daily_jobs(
                current_df=current_df,
                output_path=Path(args.linkedin_output),
                keywords=args.linkedin_keywords,
                location=args.linkedin_location,
                limit_per_query=args.linkedin_limit_per_query,
                delay=args.linkedin_delay,
                posted_within_seconds=args.linkedin_posted_within_seconds,
                related_only=not args.linkedin_raw_daily,
            )

    current_df = classify_jobs(current_df)

    all_output = Path(args.all_output)
    current_published_df = filter_published_jobs(current_df)
    previous_published_path = all_output if all_output.exists() else Path(args.related_output)
    previous_published_df = load_jobs(previous_published_path) if previous_published_path.exists() else None
    if args.storage_backend == "sheets":
        published_df = merge_published_jobs(current_published_df, previous_published_df)
    else:
        # PostgreSQL owns the rolling history. The crawl artifact stays a single-run snapshot.
        published_df = current_published_df
    related_df = filter_related_jobs(current_df)
    daily_new_df = filter_recent_published_jobs(published_df)

    related_output = Path(args.related_output)
    daily_output = Path(args.daily_output)

    save_csv(published_df, all_output)
    save_csv(related_df, related_output)
    save_csv(daily_new_df, daily_output)

    print(f"Current jobs: {len(current_df)}")
    print(f"All published Berlin engineering jobs: {len(published_df)} -> {all_output}")
    print(f"Related jobs: {len(related_df)} -> {related_output}")
    if previous_path and previous_path.exists():
        print(f"Previous baseline: {previous_path}")
    else:
        print("Previous baseline: none found")
    print(f"New today (today + yesterday): {len(daily_new_df)} -> {daily_output}")

    postgres_ok = True
    if args.storage_backend in {"postgres", "dual"} and not args.skip_upload:
        try:
            from .postgres_storage import PostgresJobStorage

            storage = PostgresJobStorage(retention_days=args.retention_days)
            storage.migrate()
            ats_company_names = [
                _company_name(row)
                for row in published_df.to_dict(orient="records")
                if not _is_linkedin_row(row) and _company_name(row)
            ]
            deleted_linkedin = storage.delete_linkedin_jobs_for_companies(ats_company_names)
            print(f"PostgreSQL LinkedIn jobs replaced by ATS: {deleted_linkedin} deleted")
            stats = storage.upsert_jobs(published_df)
            print(
                "PostgreSQL publish: "
                f"{stats.inserted} inserted, {stats.updated} updated, "
                f"{stats.skipped} expired skipped, {stats.deleted} old rows deleted"
            )
        except Exception as exc:
            postgres_ok = False
            print(f"PostgreSQL publish failed: {exc}")

    if args.skip_upload:
        if not args.no_update_baseline and previous_path:
            save_csv(current_df, previous_path)
            print(f"Updated baseline: {previous_path}")
        return 0

    if args.storage_backend == "postgres":
        return 0 if postgres_ok else 1

    all_uploaded = upload_to_sheet(published_df, args.spreadsheet, args.all_worksheet, 0)
    related_uploaded = upload_to_sheet(
        related_df,
        args.spreadsheet,
        args.related_worksheet,
        related_max_upload_lines
    )
    daily_uploaded = True
    if not args.skip_daily_upload:
        daily_uploaded = upload_to_sheet(
            daily_new_df,
            args.spreadsheet,
            args.daily_worksheet,
            daily_max_upload_lines
        )

    if postgres_ok and all_uploaded and related_uploaded and daily_uploaded:
        if not args.no_update_baseline and previous_path:
            save_csv(current_df, previous_path)
            print(f"Updated baseline: {previous_path}")
        print("Google Sheets upload: success")
        return 0

    print("Google Sheets upload: failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

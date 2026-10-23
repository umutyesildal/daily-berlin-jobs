import re

ATS_DOMAINS = [
    "ashbyhq.com", "greenhouse.io", "lever.co", "personio.de", "personio.com",
    "recruitee.com", "workable.com", "smartrecruiters.com", "myworkdayjobs.com",
    "teamtailor.com", "softgarden.io",
]

NEBIUS_MODEL = "Qwen/Qwen3-235B-A22B-Instruct-2507"

RECRUITER_BLOCKLIST = {
    "instaffo", "european tech recruit", "michael page", "randstad", "randstad deutschland", "hays",
    "xcede", "zero to one search", "techbiz global", "jobster", "engradar", "mamgo", "whybrilliant",
    "vesterling", "darwin recruitment", "computer futures", "harnham", "understanding recruitment",
    "trust in soda", "nigel frank", "jefferson frank", "frank recruitment group", "alignerr",
}

AGGREGATOR_DOMAINS = {
    "linkedin.com", "indeed.com", "indeed.de", "glassdoor.com", "glassdoor.de", "stepstone.de", "xing.com",
    "kununu.com", "levels.fyi", "startup.jobs", "welcometothejungle.com", "arbeitnow.com",
    "berlinstartupjobs.com", "jobteaser.com", "crunchbase.com", "wellfound.com", "join.com",
    "ycombinator.com", "builtin.com", "simplyhired.com", "monster.de", "jooble.org", "talent.com",
    "jobs.lsvp.com", "otta.com", "honeypot.io", "germantechjobs.de", "jobdropberlin.com", "ampli.xyz",
    "wikipedia.org", "facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com", "github.com",
    "medium.com", "google.com", "apple.com", "bloomberg.com", "techcrunch.com", "theorg.com",
}

SOCIAL_OR_NOISE = AGGREGATOR_DOMAINS | {
    "ashbyhq.com", "greenhouse.io", "lever.co", "personio.de", "personio.com", "recruitee.com",
    "workable.com", "smartrecruiters.com", "teamtailor.com", "softgarden.io",
    "w3.org", "schema.org", "gstatic.com", "googleapis.com",
    "cloudfront.net", "amazonaws.com", "gdpr-info.eu", "eur-lex.europa.eu", "bit.ly", "goo.gl",
    "calendly.com", "notion.site", "typeform.com", "vimeo.com", "spotify.com", "tiktok.com",
    "glassdoor.co.uk", "kununu.de", "bundesagentur.de", "arbeitsagentur.de",
}

BOARD_PATTERNS = [
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9._%~-]+)", re.I)),
    ("ashby", re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([A-Za-z0-9._%~-]+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"(?:jobs|api)\.(eu\.)?lever\.co/(?:v0/postings/)?([A-Za-z0-9._-]+)", re.I)),
    ("personio", re.compile(r"([a-z0-9][a-z0-9-]*)\.jobs\.personio\.(de|com)", re.I)),
    ("recruitee", re.compile(r"([a-z0-9][a-z0-9-]*)\.recruitee\.com", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/(?:api/v\d/(?:widget/)?accounts/)?([A-Za-z0-9_-]+)", re.I)),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    (
        "workday",
        re.compile(
            r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[a-z]{2}/)?([A-Za-z0-9_-]+)",
            re.I,
        ),
    ),
    ("teamtailor", re.compile(r"([a-z0-9-]+)\.teamtailor\.com", re.I)),
    ("softgarden", re.compile(r"([a-z0-9-]+)\.softgarden\.io", re.I)),
]

BAD_SLUGS = {"", "api", "embed", "v0", "v1", "jobs", "job", "careers", "www", "app", "j", "js", "static",
             "assets", "support", "blog", "status", "help", "login", "signup", "posting-api", "oneclick-ui",
             "privacy", "terms", "cdn", "images", "favicon.ico", "robots.txt", "sitemap.xml", "apply"}

LLM_SYSTEM = (
    "You review employers for a Berlin tech job board. You only use the evidence given. "
    "Answer with a single JSON object and nothing else."
)

LLM_INSTRUCTIONS = """Evidence about one job board (JSON):
{evidence}

Return exactly this JSON object:
{{"company_name": string, "is_staffing_or_recruitment_agency": boolean, "is_job_board_or_marketplace": boolean, "official_website": string or null, "confidence": number between 0 and 1, "notes": string}}

Rules:
- company_name: the employer's name as it is commonly written, without legal suffixes such as GmbH, SE, AG or Inc unless they are part of the brand. Prefer board_name or linkedin_company_name when present.
- is_staffing_or_recruitment_agency: true only if the listed jobs are filled at client companies (recruiters, headhunters, staffing, contracting or talent-placement firms). IT consultancies and agencies that employ the engineers themselves are false.
- is_job_board_or_marketplace: true if the board aggregates jobs of many different employers or is a freelance/gig marketplace (for example AI-training gig work).
- official_website: the employer's own homepage (https://...) only if it appears in the evidence or you are certain of it; otherwise null. Never return an ATS, LinkedIn or job-board URL.
- confidence: your confidence in the two booleans.
- notes: at most 20 words."""

PARKED_DOMAINS = {"sedo.com", "domainmarkt.de", "dan.com", "afternic.com", "hugedomains.com", "godaddy.com",
                  "relocate.me", "careerwebsite.com", "parkingcrew.net", "bodis.com", "uniregistry.com"}
PARKED_MARKERS = ("domain is for sale", "domain for sale", "buy this domain", "domain kaufen", "diese domain",
                  "this domain may be for sale", "domain steht zum verkauf", "parked free")

DISCOVERY_TERMS = [
    "software engineer", "backend engineer", "frontend engineer", "full stack engineer", "data engineer",
    "machine learning engineer", "AI engineer", "devops engineer", "platform engineer", "site reliability engineer",
    "security engineer", "mobile engineer iOS Android", "embedded software engineer", "QA test automation engineer",
    "engineering manager", "data scientist", "cloud engineer", "Softwareentwickler", "Werkstudent software", "junior developer",
]

URL_RE = re.compile(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.I)

import re
import urllib.parse

from .constants import BAD_SLUGS, BOARD_PATTERNS


def extract_boards(text: str):
    found = set()
    for ats, pattern in BOARD_PATTERNS:
        for match in pattern.finditer(text or ""):
            if ats == "lever":
                region, slug = ("eu" if match.group(1) else ""), match.group(2)
            elif ats == "personio":
                slug, region = match.group(1), match.group(2).lower()
            elif ats == "workday":
                tenant, region, site = match.groups()
                if site.lower() in BAD_SLUGS | {"job", "details", "search"}:
                    continue
                slug, region = f"{tenant.lower()}/{site}", region.lower()
            else:
                slug, region = match.group(1), ""
            slug = urllib.parse.unquote(slug).strip().strip(".")
            if (
                slug.lower() in BAD_SLUGS
                or len(slug) < 2
                or (ats == "workday" and slug.split("/", 1)[-1].lower() in BAD_SLUGS | {"job", "details", "search"})
            ):
                continue
            key_slug = slug if ats in {"smartrecruiters", "workday"} else slug.lower()
            found.add((ats, key_slug, region))
    return found


def career_page(ats: str, slug: str, region: str) -> str:
    slug = urllib.parse.quote(slug, safe="._-~")
    if ats == "workday":
        return _workday_career_page(urllib.parse.unquote(slug), region)
    return {
        "ashby": f"https://jobs.ashbyhq.com/{slug}",
        "greenhouse": f"https://boards.greenhouse.io/{slug}",
        "lever": f"https://api.{'eu.' if region == 'eu' else ''}lever.co/v0/postings/{slug}?mode=json",
        "personio": f"https://{slug}.jobs.personio.{region or 'de'}",
        "recruitee": f"https://{slug}.recruitee.com",
        "workable": f"https://apply.workable.com/{slug}",
        "smartrecruiters": f"https://careers.smartrecruiters.com/{slug}",
    }[ats]


def _workday_career_page(slug: str, region: str) -> str:
    tenant, separator, site = slug.partition("/")
    if not separator or not re.fullmatch(r"wd\d+", region, re.IGNORECASE):
        raise ValueError("Workday board keys must contain a tenant/site and wdN region")
    return (
        f"https://{tenant}.{region.lower()}.myworkdayjobs.com/"
        f"{urllib.parse.quote(site, safe='._-')}"
    )

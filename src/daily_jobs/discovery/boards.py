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
            else:
                slug, region = match.group(1), ""
            slug = urllib.parse.unquote(slug).strip().strip(".")
            if slug.lower() in BAD_SLUGS or len(slug) < 2:
                continue
            key_slug = slug if ats == "smartrecruiters" else slug.lower()
            found.add((ats, key_slug, region))
    return found


def career_page(ats: str, slug: str, region: str) -> str:
    slug = urllib.parse.quote(slug, safe="._-~")
    return {
        "ashby": f"https://jobs.ashbyhq.com/{slug}",
        "greenhouse": f"https://boards.greenhouse.io/{slug}",
        "lever": f"https://api.{'eu.' if region == 'eu' else ''}lever.co/v0/postings/{slug}?mode=json",
        "personio": f"https://{slug}.jobs.personio.{region or 'de'}",
        "recruitee": f"https://{slug}.recruitee.com",
        "workable": f"https://apply.workable.com/{slug}",
        "smartrecruiters": f"https://careers.smartrecruiters.com/{slug}",
    }[ats]

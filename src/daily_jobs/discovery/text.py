import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from ..job_taxonomy import classify_role


def norm_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", (value or "").replace("\\u0026", "&")).encode("ascii", "ignore").decode()
    value = re.sub(r"\(.*?\)", " ", value.casefold())
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\b(gmbh|se|ag|kg|kgaa|inc|ltd|llc|co|plc|bv|nv|sa|sas|holding|group|gruppe|"
                   r"tech|technologies|internet|europe|germany|deutschland|berlin|hq|labs?)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def name_similarity(left: str, right: str) -> float:
    a, b = norm_name(left), norm_name(right)
    if not a or not b:
        return 0.0
    if a.replace(" ", "") == b.replace(" ", ""):
        return 1.0
    return SequenceMatcher(None, a.replace(" ", ""), b.replace(" ", "")).ratio()


def norm_title(value: str) -> str:
    value = re.sub(r"\((?:m|w|f|d|x|all|gn|div)[^)]*\)", " ", (value or "").casefold())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def registrable_domain(host: str) -> str:
    host = (host or "").lower().split(":")[0].strip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gv", "ac"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def is_berlin(location: str) -> bool:
    return "berlin" in (location or "").casefold()


def is_engineering(title: str) -> bool:
    return bool(classify_role({"Job Title": title or ""}))


def title_overlap(linkedin: list[str], board_titles: list[str]) -> bool:
    left = {norm_title(title) for title in linkedin if title}
    right = {norm_title(title) for title in board_titles if title}
    return len(left & right) >= 3


def is_demo_or_test_slug(slug: str) -> bool:
    value = (slug or "").casefold()
    if "demo" in value or "sandbox" in value:
        return True
    return bool({"test", "staging"} & set(re.split(r"[-_.]", value)))


def domain_from_url(value: str) -> str:
    return registrable_domain(urlsplit(value).hostname or "")

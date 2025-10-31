import re
from django.utils.text import slugify

ROUTE_RE = re.compile(r"^\s*([A-Z]{3,})\s+\d+[A-Z]?\s*$")
TIME_RE  = re.compile(r"^\s*\d{1,2}:\d{2}(\s*[AP]M)?\s*$", re.I)
NOISE = {"PICK UP", "TIME NAME", "MEMBER", "DRIVER ID", "ADDRESS PICK"}

def strip_route_or_time(s: str) -> str:
    s = (s or "").strip()
    if not s: return ""
    if ROUTE_RE.match(s): return ""
    if TIME_RE.match(s):  return ""
    return s

def normalize_place(addr: str, city: str):
    addr = strip_route_or_time(addr)
    city = strip_route_or_time(city).title() if city else ""
    return addr, city

def client_slug(name, phone=None, city=None):
    # deterministic, avoids your UNIQUE slug collisions
    aug = phone or (city and city.lower()) or "na"
    return slugify(f"{name}|{aug}")

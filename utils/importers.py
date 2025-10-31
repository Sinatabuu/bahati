# utils/importers.py
import re
from datetime import time as _time

DRIVER_RE = re.compile(r'^([A-Z][A-Z]+)\s*(\d+[A-Z]?)?\b')            # e.g., DAVID 1A
TIME_RE   = re.compile(r'\b(\d{1,2}:\d{2})\b')
ADDR_RE   = re.compile(r'\b\d{1,5}\s+[A-Za-z0-9\'\.\- ]+\b')          # start of address (street name continues)
CITY_STOP = re.compile(r'\b(?:[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b')      # simple city word(s)

def _to_time(tok):
    try:
        h, m = map(int, tok.split(':'))
        return _time(h, m) if 0 <= h < 24 and 0 <= m < 60 else None
    except Exception:
        return None

def parse_row(line: str):
    """
    Return dict:
      driver_name, route_code, start_time, client_name,
      pickup_address, pickup_city, dropoff_address, dropoff_city, notes
    """
    s = ' '.join(line.split())
    notes_parts = []

    # 1) driver + route
    m = DRIVER_RE.search(s)
    driver_name = route_code = None
    if m:
        driver_name = m.group(1).title()        # DAVID -> David
        route_code  = (m.group(2) or '').upper()
        s = s[m.end():].strip()

    # 2) time
    t = None
    mt = TIME_RE.search(s)
    if mt:
        t = _to_time(mt.group(1))
        s = s[:mt.start()] + s[mt.end():]   # drop time token from scanning

    # 3) client name = text before first numeric-address
    ma = re.search(r'\d{1,5}\s', s)
    client_name = s[:ma.start()].strip() if ma else s.strip()

    # 4) addresses: find two address starts, then collect city tokens after each
    # Simplify: split by 2 addresses
    addr_starts = list(re.finditer(r'\d{1,5}\s', s))
    pickup_address = pickup_city = dropoff_address = dropoff_city = ''
    try:
        a1_idx = addr_starts[0].start()
        # find end of pickup address by searching for the next city-capitalized token run;
        rest = s[a1_idx:]
        # naive split: pickup fields until we hit another address start
        if len(addr_starts) >= 2:
            a2_idx = addr_starts[1].start() - a1_idx
            pickup_chunk  = rest[:a2_idx].strip()
            dropoff_chunk = rest[a2_idx:].strip()
        else:
            pickup_chunk, dropoff_chunk = rest.strip(), ''

        def split_addr_city(chunk):
            # assume "... STREET CITY" tail; last token(s) after street is city
            tokens = chunk.split()
            # heuristic: take last 1-2 tokens as city if capitalized/mixed
            if len(tokens) >= 2:
                city = tokens[-1]
                # allow two-word cities (e.g., "Westford", "North Chelmsford")
                if len(tokens) >= 3 and tokens[-2][0].isupper():
                    city = f"{tokens[-2]} {tokens[-1]}"
                    street = ' '.join(tokens[:-2])
                else:
                    street = ' '.join(tokens[:-1])
            else:
                street, city = chunk, ''
            return street.strip(), city.strip()

        if pickup_chunk:
            pickup_address, pickup_city = split_addr_city(pickup_chunk)
        if dropoff_chunk:
            dropoff_address, dropoff_city = split_addr_city(dropoff_chunk)

    except Exception:
        notes_parts.append(f"[PARSE-WARN:{line}]")

    # 5) notes = anything that didn’t fit (broker IDs, phones, DOB)
    # (You can get fancier by extracting specific fields.)
    notes = ' '.join(notes_parts).strip()

    return dict(
        driver_name=driver_name, route_code=route_code,
        start_time=t, client_name=client_name,
        pickup_address=pickup_address, pickup_city=pickup_city,
        dropoff_address=dropoff_address, dropoff_city=dropoff_city,
        notes=notes,
    )

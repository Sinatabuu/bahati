# /tmp/backfill_schedule.py
from datetime import datetime, date
import csv, io, re, sys
from django.db import transaction
from scheduler.models import ScheduleEntry, Driver

# -------- CONFIG --------
SCHEDULE_DATE = date(2025, 10, 17)  # or whatever day you're backfilling
CSV_PATH = "/mnt/c/Users/User/OneDrive/Desktop/BAHATI/csv_files/BAHA AUGUST 8TH.csv"


# -------- Helpers --------
TIME_RE   = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d$")
PUNCT_RE  = re.compile(r"[^A-Z ]+")
MISSPELL  = {
    "BILLERRICA": "BILLERICA",
    "CARLISTLE": "CARLISLE",
    "TYNGSBOORO": "TYNGSBOROUGH",
    "TYNGSBORO": "TYNGSBOROUGH",
    "FITCHURG": "FITCHBURG",
    "LITON": "LITTLETON",
    "WEUGH": "WESTBOROUGH",
}

ALIASES = {
    "KHAN BH": "BAN KHIN KHAW",
    "KRISTINE S": "KRISTINE SWIFT",
    "LOW, SAMBO": "SAMBO LOW",
    "ALLISON M": "ALISON M",
    "PATRICA M": "PATRICIA M",
    # add more as you discover them
}


def norm_city(s):
    if not s: return None
    u = str(s).strip().upper()
    u = MISSPELL.get(u, u)
    return " ".join(w.capitalize() for w in u.split())

def clean_addr(s):
    if not s: return None
    s = str(s).strip()
    if not s or TIME_RE.match(s): return None
    return " ".join(p.capitalize() if not p.isupper() else p for p in s.split())

def parse_hm(t):
    if not t: return None
    t = t.strip()
    # normalize e.g. "7:5" -> "07:05"
    if re.match(r"^\d{1,2}:\d{1,2}$", t):
        hh, mm = t.split(":")
        t = f"{int(hh):02d}:{int(mm):02d}"
    if not TIME_RE.match(t): return None
    return datetime.strptime(t, "%H:%M").time()

def name_key(s):
    if not s: return ""
    s = s.upper().strip().replace(",", " ")
    s = PUNCT_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()

def name_variants(s):
    out = set()
    k = name_key(s)
    if not k: return out
    out.add(k)
    parts = k.split()
    if len(parts) == 1:
        out.add(parts[0])
        return out
    first, last = parts[0], parts[-1]
    # Tolerate CSV “LAST, FIRST”
    if "," in (s or "") and len(parts) >= 2:
        last = parts[0]
        first = parts[1]
    out.add(f"{first} {last}")
    out.add(f"{first} {last[:1]}")
    out.add(f"{first[:1]} {last}")
    if len(parts) >= 2:
        out.add(f"{parts[0]} {parts[1][:1]}")
    # collapse spaces
    return {re.sub(r"\s+", " ", v).strip() for v in out if v.strip()}

def apply_alias(name: str) -> str:
    if not name: return name
    key = name_key(name)
    # try exact alias
    for k,v in ALIASES.items():
        if name_key(k) == key:
            return v
    return name

def soft_member_keys(s: str) -> set[str]:
    """
    Very tolerant keys to catch 'Julio C' <-> 'Julio C.' <-> 'JULIO C'.
    Produces:
      - FIRST
      - FIRST LAST_INITIAL
      - FIRST LAST
    """
    out = set()
    k = name_key(s)
    if not k: return out
    parts = k.split()
    if len(parts) == 1:
        out.add(parts[0])  # FIRST
        return out
    first, last = parts[0], parts[-1]
    out.add(first)                 # FIRST
    out.add(f"{first} {last[:1]}") # FIRST L
    out.add(f"{first} {last}")     # FIRST LAST
    return out

def driver_first(s):
    return (s or "").strip().split()[0].upper() if s else ""

# get with multiple possible header names
def get_field(row, *names):
    for n in names:
        if n in row: return row.get(n)
    return None

def read_csv_rows(path):
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "driver_token": (get_field(r, "DRIVER") or "").strip(),
                "time":         (get_field(r, "TIME") or "").strip(),
                "member":       (get_field(r, "MEMBER") or "").strip(),
                "pu_addr": clean_addr(get_field(r, "ADDRESS PICK", "ADDRESS PICK ")),
                "pu_city": norm_city(get_field(r, "CITY PICK", "CITY PICK ")),
                "do_addr": clean_addr(get_field(r, "DROP ADDRESS", "DROP ADDRESS ")),
                "do_city": norm_city(get_field(r, "DROP CITY", "DROP CITY ")),
            })
    return rows

def build_driver_map():
    m = {}
    for d in Driver.objects.only("id", "name"):
        if not d.name: continue
        key = d.name.split()[0].upper()
        if key not in m or len(d.name) > len(m[key].name):
            m[key] = d
    return m

# Tuning knobs
# Tuning
WINDOW_MEMBER_SECS = 120 * 60   # ±120 min
WINDOW_DRIVER_SECS = 60 * 60    # ±60 min

def choose_csv_row(entry, csv_rows, member_index, drv_time_index, soft_index):
    # normalize entry time
    t  = entry.start_time.strftime("%H:%M") if entry.start_time else None
    df = driver_first(getattr(entry.driver, "name", None))

    # normalize/alias entry display name
    disp_raw = entry.client_name or (getattr(entry.client, "name", "") or "")
    disp = apply_alias(disp_raw)

    # 1) exact (driver_first, time)
    if t and df and (df, t) in drv_time_index:
        return drv_time_index[(df, t)], "driver+time"

    # 2) member fuzzy (exact time)
    cands = []
    for v in name_variants(disp):
        cands.extend(member_index.get(v, []))
    if cands and t:
        for r in cands:
            rt = parse_hm(r["time"])
            if rt and rt.strftime("%H:%M") == t:
                return r, "member+time"

    # 3) same-driver nearest time within WINDOW_DRIVER_SECS
    if t and df:
        goal = datetime.strptime(t, "%H:%M")
        best = None; bestd = None
        for r in csv_rows:
            if driver_first(r["driver_token"]) != df: 
                continue
            pt = parse_hm(r["time"])
            if not pt: 
                continue
            d = abs((datetime.combine(datetime.today(), pt) - datetime.combine(datetime.today(), goal.time())).total_seconds())
            if d <= WINDOW_DRIVER_SECS and (bestd is None or d < bestd):
                best, bestd = r, d
        if best:
            return best, "driver~time(±60m)"

    # 4) soft member (FIRST or FIRST L or FIRST LAST) nearest time within WINDOW_MEMBER_SECS
    soft_cands = []
    for k in soft_member_keys(disp):
        soft_cands.extend(soft_index.get(k, []))
    if soft_cands and t:
        goal = datetime.strptime(t, "%H:%M")
        best = None; bestd = None
        for r in soft_cands:
            pt = parse_hm(r["time"])
            if not pt:
                continue
            d = abs((datetime.combine(datetime.today(), pt) - datetime.combine(datetime.today(), goal.time())).total_seconds())
            if d <= WINDOW_MEMBER_SECS and (bestd is None or d < bestd):
                best, bestd = r, d
        if best:
            return best, "member~time(±120m-soft)"

    # 5) unique soft member (no time requirement)
    if soft_cands:
        uniq = []
        seen = set()
        for r in soft_cands:
            key = (r.get("member"), r.get("pu_addr"), r.get("do_addr"), r.get("time"))
            if key not in seen:
                uniq.append(r); seen.add(key)
        if len(uniq) == 1:
            return uniq[0], "member(unique-soft)"

    # 6) member fuzzy (no time) unique
    if cands:
        uniq = []
        seen = set()
        for r in cands:
            key = (r.get("member"), r.get("pu_addr"), r.get("do_addr"), r.get("time"))
            if key not in seen:
                uniq.append(r); seen.add(key)
        if len(uniq) == 1:
            return uniq[0], "member(unique)"

    return None, "no-match"



@transaction.atomic
def main():
    csv_rows = read_csv_rows(CSV_PATH)
    row, why = choose_csv_row(e, csv_rows, member_index, drv_time_index, soft_index)

    # indexes
    member_index = {}
    for row in csv_rows:
        for v in name_variants(row["member"]):
            member_index.setdefault(v, []).append(row)

    soft_index = {}
    for row in csv_rows:
        m = apply_alias(row["member"])
        for k in soft_member_keys(m):
            soft_index.setdefault(k, []).append(row)

    drv_time_index = {}
    for row in csv_rows:
        t = row["time"]
        df = driver_first(row["driver_token"])
        if t and df:
            # normalize time to HH:MM
            nt = parse_hm(t)
            if nt:
                drv_time_index[(df, nt.strftime("%H:%M"))] = row

    driver_map = build_driver_map()

    qs = (ScheduleEntry.objects
          .select_related("client", "schedule", "driver")
          .filter(schedule__date=SCHEDULE_DATE)
          .order_by("start_time", "id"))

    updated = 0
    no_match = []

    for e in qs:
        row, why = choose_csv_row(e, csv_rows, member_index, drv_time_index)
        if not row:
            no_match.append((e.id, e.client_name, e.start_time, "NO MATCH"))
            continue

        pu_addr = e.pickup_address  or row["pu_addr"]
        pu_city = e.pickup_city     or row["pu_city"]
        do_addr = e.dropoff_address or row["do_addr"]
        do_city = e.dropoff_city    or row["do_city"]

        # time backfill
        if not e.start_time and row["time"]:
            pt = parse_hm(row["time"])
            if pt:
                e.start_time = pt

        # driver backfill
        if not e.driver_id and row["driver_token"]:
            d = driver_map.get(driver_first(row["driver_token"]))
            if d:
                e.driver = d

        fields = {}
        if pu_addr and pu_addr != e.pickup_address:   fields["pickup_address"]  = pu_addr
        if pu_city and pu_city != e.pickup_city:       fields["pickup_city"]     = pu_city
        if do_addr and do_addr != e.dropoff_address:   fields["dropoff_address"] = do_addr
        if do_city and do_city != e.dropoff_city:      fields["dropoff_city"]    = do_city
        if e.start_time:                               fields["start_time"]      = e.start_time
        if e.driver_id:                                fields["driver_id"]       = e.driver_id

        if fields:
            for k, v in fields.items(): setattr(e, k, v)
            e.save(update_fields=list(fields.keys()))
            updated += 1

    print(f"Schedule date: {SCHEDULE_DATE} | Entries: {qs.count()} | Updated: {updated}")
    if no_match:
        print("No-match (first 20):")
        for r in no_match[:20]:
            print(f"  id={r[0]} name={r[1]!r} time={r[2]} -> {r[3]}")

# Execute
main()

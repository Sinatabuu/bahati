# scheduler/management/commands/repair_day.py
from __future__ import annotations

import re
from datetime import datetime, time
from typing import Optional, Tuple, List

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from scheduler.models import Company, Schedule, ScheduleEntry, Client

# --------- heuristics ---------

HOUSE_NUM = re.compile(r"(?<!\d)\d{1,6}(?!\d)")
TIME_RE   = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")

HEADER_NOISE = [
    "TIME NAME", "PICK UP", "MEMBER", "DRIVER ID", "ADDRESS PICK",
    "PHONE", "DATE CLIENT DRIVER PICKUP DROPOFF TIME STATUS"
]

def norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def split_lines(blob: str) -> List[str]:
    if not blob:
        return []
    out: List[str] = []
    for raw in re.split(r"[\r\n]+", blob):
        x = norm(raw)
        if x:
            out.append(x)
    return out

def looks_like_header_row(text: str) -> bool:
    u = (text or "").upper()
    return any(h in u for h in HEADER_NOISE)

def is_name_line(line: str) -> bool:
    # A line is "name-like" if it contains no digits and at least one letter
    if not line:
        return False
    if any(ch.isdigit() for ch in line):
        return False
    return any(ch.isalpha() for ch in line)

def is_address_line(line: str) -> bool:
    # Require a house number and some letters (e.g., "34 PLAIN ROAD")
    return bool(line and HOUSE_NUM.search(line) and re.search(r"[A-Za-z]", line))

def try_parse_time(hh: str, mm: str) -> Optional[time]:
    try:
        h = int(hh); m = int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return time(hour=h, minute=m)
    except Exception:
        pass
    return None

def pull_times(blob: str) -> Tuple[Optional[time], Optional[time], str]:
    if not blob:
        return None, None, blob
    times: List[time] = []

    def _sub(m):
        t = try_parse_time(m.group(1), m.group(2))
        if t:
            times.append(t)
        return " "

    out = TIME_RE.sub(_sub, blob)
    out = norm(out)
    start = times[0] if times else None
    end   = times[1] if len(times) > 1 else None
    return start, end, out

def fuzzy_find_client(company: Company, raw: str) -> Optional[Client]:
    raw = (raw or "").strip()
    if not raw:
        return None
    # exact (iexact) first
    c = Client.objects.filter(company=company, name__iexact=raw).first()
    if c: return c
    # contains
    c = Client.objects.filter(company=company, name__icontains=raw).first()
    if c: return c

    def key(x: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (x or "").lower())

    k = key(raw)
    for cand in Client.objects.filter(company=company):
        ck = key(cand.name)
        if ck == k or k in ck or ck in k:
            return cand
    return None

def candidate_from_blob(blob: str) -> tuple[str, list[str]]:
    """
    From a dirty client_name blob, return (probable_client_name, address_lines[])
    Strategy:
      - split lines
      - collect address lines (with house number)
      - use the first contiguous block of 'name-like' lines before the first address as the candidate name
    """
    lines = split_lines(blob)
    if not lines:
        return "", []

    addr_idx = None
    addresses: List[str] = []
    for i, ln in enumerate(lines):
        if is_address_line(ln):
            addresses.append(ln)
            if addr_idx is None:
                addr_idx = i
        # keep scanning to collect a second address if present

    # name = first non-empty, name-like line before the first address
    name = ""
    search_upto = addr_idx if addr_idx is not None else len(lines)
    for ln in lines[:search_upto]:
        if is_name_line(ln):
            name = ln
            break

    # fallback: first name-like anywhere
    if not name:
        for ln in lines:
            if is_name_line(ln):
                name = ln
                break

    return name, addresses

# --------- command ---------

class Command(BaseCommand):
    help = "Repair a day's ScheduleEntry rows: clean names, extract times, safely hydrate from Client, and remove header junk."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
        parser.add_argument("--company", required=True, help="Company name")
        parser.add_argument("--dry", action="store_true", help="Dry-run (no writes)")
        parser.add_argument("--force", action="store_true",
                            help="Overwrite entry fields from CLIENT PROFILE only (never from blob text)")
        parser.add_argument("--show", action="store_true", help="Print before/after samples")

    def handle(self, *args, **opts):
        # date
        if opts.get("date"):
            try:
                day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("Invalid --date, expected YYYY-MM-DD")
        else:
            day = timezone.localdate()

        # company
        cname = opts["company"].strip()
        try:
            company = Company.objects.get(name=cname)
        except Company.DoesNotExist:
            raise CommandError(f"Company not found: {cname}")

        sched = Schedule.objects.filter(company=company, date=day).first()
        if not sched:
            raise CommandError(f"No schedule for {company} on {day}")

        qs = (ScheduleEntry.objects
              .filter(schedule=sched)
              .select_related("client"))

        def stats(prefix: str):
            total = qs.count()
            no_client = qs.filter(client__isnull=True).count()
            pu_blank = qs.filter(pickup_address__in=["", None]).count()
            do_blank = qs.filter(dropoff_address__in=["", None]).count()
            puc_blank = qs.filter(pickup_city__in=["", None]).count()
            doc_blank = qs.filter(dropoff_city__in=["", None]).count()
            self.stdout.write(f"{prefix}: total={total} no_client={no_client} "
                              f"PU_addr_blank={pu_blank} DO_addr_blank={do_blank} "
                              f"PU_city_blank={puc_blank} DO_city_blank={doc_blank}")

        stats("Before")
        if opts["show"]:
            for e in qs.order_by("start_time", "id")[:5]:
                self.stdout.write(f"  [#{e.id}] name={e.client_name!r} client={(e.client and e.client.name) or None!r} "
                                  f"PU={e.pickup_address!r}/{e.pickup_city!r} DO={e.dropoff_address!r}/{e.dropoff_city!r} "
                                  f"t={e.start_time}–{e.end_time}")

        dry   = opts["dry"]
        force = opts["force"]

        processed = linked = hydrated = soft_deleted = 0

        @transaction.atomic
        def run():
            nonlocal processed, linked, hydrated, soft_deleted

            for e in qs:
                raw_name = e.client_name or ""

                # obvious headers → soft delete to hide from UI
                if looks_like_header_row(raw_name):
                    if not e.client and not any([e.pickup_address, e.dropoff_address, e.start_time, e.end_time]):
                        e.is_deleted = True
                        e.save(update_fields=["is_deleted", "updated_at"])
                        soft_deleted += 1
                        processed += 1
                        continue

                # Pull times out (safe: times detected by regex)
                st, et, name_wo_time = pull_times(raw_name)

                # Pick candidate name and up to 2 addresses from the blob
                candidate_name, addr_lines = candidate_from_blob(name_wo_time)

                changed = False

                # Set start/end times only if blank OR we are sure and force
                if st and (force or not e.start_time):
                    e.start_time = st; changed = True
                if et and (force or not e.end_time):
                    e.end_time = et; changed = True

                # Clean name (prefer the candidate name)
                if candidate_name and candidate_name != e.client_name:
                    e.client_name = candidate_name; changed = True

                # Link client FK if missing
                if e.client is None and candidate_name:
                    c = fuzzy_find_client(company, candidate_name)
                    if c:
                        e.client = c; linked += 1; changed = True

                # SAFETY: Never “force from blob”
                # Only write addresses from blob when entry fields are blank AND we do NOT have a Client FK.
                if e.client is None:
                    if len(addr_lines) >= 1 and not (e.pickup_address or "").strip():
                        e.pickup_address = addr_lines[0]; changed = True
                    if len(addr_lines) >= 2 and not (e.dropoff_address or "").strip():
                        e.dropoff_address = addr_lines[1]; changed = True

                # Hydrate from client profile
                if e.client:
                    c = e.client
                    # blank-only unless --force
                    def set_from_client(field: str, value: str):
                        nonlocal changed, hydrated
                        cur = getattr(e, field)
                        if force:
                            if value and cur != value:
                                setattr(e, field, value); changed = True; hydrated += 1
                        else:
                            if (cur or "").strip():
                                return
                            if value:
                                setattr(e, field, value); changed = True; hydrated += 1

                    set_from_client("pickup_address", c.pickup_address)
                    set_from_client("dropoff_address", c.dropoff_address)
                    set_from_client("pickup_city", c.pickup_city)
                    set_from_client("dropoff_city", c.dropoff_city)
                    # also ensure client_name at least equals client.name when empty
                    if not (e.client_name or "").strip():
                        e.client_name = c.name; changed = True

                if changed:
                    e.save()

                processed += 1

            if dry:
                raise transaction.TransactionManagementError("DRY-RUN")

        try:
            run()
        except transaction.TransactionManagementError:
            pass  # expected for --dry

        self.stdout.write(
            f"{'Dry run' if dry else 'Committed'}: processed={processed}, linked={linked}, hydrated={hydrated}, soft_deleted_noise={soft_deleted}"
        )
        stats("After")

        if opts["show"]:
            for e in qs.order_by("start_time", "id")[:5]:
                self.stdout.write(f"  [#{e.id}] name={e.client_name!r} client={(e.client and e.client.name) or None!r} "
                                  f"PU={e.pickup_address!r}/{e.pickup_city!r} DO={e.dropoff_address!r}/{e.dropoff_city!r} "
                                  f"t={e.start_time}–{e.end_time}")

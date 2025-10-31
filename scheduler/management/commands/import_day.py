# scheduler/management/commands/import_day.py
from __future__ import annotations

import re
from datetime import datetime, date as date_type, time as time_type
from typing import Iterable, List, Dict, Tuple, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

try:
    import pdfplumber  # optional
except Exception:  # pragma: no cover
    pdfplumber = None

from scheduler.models import (
    Company,
    Schedule,
    ScheduleEntry,
    Client,
    Driver,
)

TIME_RE = re.compile(
    r"\b((?:[01]?\d|2[0-3])[:.][0-5]\d)(?:\s*([AP]M))?\b",
    flags=re.IGNORECASE,
)
LOGI_LINE = re.compile(r'^\s*\d+\-\d+')

GARBAGE_PATTERNS = [
    "TIME NAME",
    "PICK UP MEMBER",
    "DATE CLIENT DRIVER PICKUP DROPOFF",
    "TRIPS FOR THE SELECTED WINDOW",
    "—",           # the em dash column filler
    "PHONE",
    "NAME",
]

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _looks_like_garbage(line: str) -> bool:
    u = line.upper().strip()
    if not u:
        return True
    for pat in GARBAGE_PATTERNS:
        if pat in u:
            return True
    # Lines that are only numbers or only AM/PM time fragments
    if re.fullmatch(r"[0-9:/.\sAPMapm-]+", line.strip() or ""):
        return False  # allow pure time lines (we’ll use them with the next client hit)
    return False

def _extract_times(line: str) -> List[time_type]:
    times: List[time_type] = []
    for m in TIME_RE.finditer(line):
        hhmm = m.group(1).replace(".", ":")
        ampm = (m.group(2) or "").upper()
        # Normalize to 24h
        try:
            if ampm in ("AM", "PM"):
                t = datetime.strptime(f"{hhmm} {ampm}", "%I:%M %p").time()
            else:
                t = datetime.strptime(hhmm, "%H:%M").time()
            times.append(t)
        except Exception:
            continue
    return times

def _read_pdf_lines(pdf_path: str) -> List[str]:
    if not pdfplumber:
        raise CommandError("pdfplumber is not installed. `pip install pdfplumber` or pass a pre-extracted text file.")
    lines: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw in text.splitlines():
                line = raw.strip()
                # Collapse in-line double spaces
                line = re.sub(r"\s{2,}", " ", line)
                if line:
                    lines.append(line)
    return lines

def _read_txt_lines(txt_path: str) -> List[str]:
    lines: List[str] = []
    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if line:
                lines.append(line)
    return lines

def _choose_start_time(candidate_times: List[time_type]) -> Optional[time_type]:
    if not candidate_times:
        return None
    # Heuristic: if two times present (e.g., "8:40 9:00") pick the first as pickup window start
    return candidate_times[0]

class Command(BaseCommand):
    help = "Import a daily schedule from a PDF (or text) by matching known Clients; skip headers; use client canonicals."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, help="YYYY-MM-DD (schedule date)")
        parser.add_argument("--company", required=True, help="Company name")
        parser.add_argument("--pdf", help="Path to source PDF")
        parser.add_argument("--txt", help="Path to pre-extracted text (one line per row)")
        parser.add_argument("--replace", action="store_true", help="Delete existing entries for that date before import")
        parser.add_argument("--dry", action="store_true", help="Dry run (no DB writes)")
        parser.add_argument("--show", action="store_true", help="Print summary of what will be imported")

    def handle(self, *args, **opts):
        # --- inputs
        d = parse_date(opts["date"])
        if not d:
            raise CommandError("Invalid --date (expected YYYY-MM-DD)")

        try:
            company = Company.objects.get(name=opts["company"])
        except Company.DoesNotExist as e:
            raise CommandError(f"Company not found: {opts['company']}") from e

        pdf_path = opts.get("pdf")
        txt_path = opts.get("txt")
        if not pdf_path and not txt_path:
            raise CommandError("Provide either --pdf or --txt")

        if pdf_path:
            lines = _read_pdf_lines(pdf_path)
        else:
            lines = _read_txt_lines(txt_path)

        # --- build lookup tables
        clients = list(Client.objects.filter(company=company))
        if not clients:
            raise CommandError(f"No clients defined for company '{company.name}'. Create clients first.")

        drivers = list(Driver.objects.filter(company=company, active=True))

        client_map: Dict[str, Client] = {_norm(c.name): c for c in clients}
        driver_map: Dict[str, Driver] = {_norm(dr.name): dr for dr in drivers}

        # --- ensure schedule
        schedule, _ = Schedule.objects.get_or_create(company=company, date=d)

        # --- optional replace
        if opts["replace"] and not opts["dry"]:
            ScheduleEntry.objects.filter(schedule=schedule).delete()

        # --- pass 1: normalize raw lines, filter garbage
        clean_lines: List[str] = []
        for line in lines:
            if _looks_like_garbage(line):
                continue
            clean_lines.append(line)

        # --- pass 2: infer candidate records
        # Strategy: for each line, if it contains a known client name token -> create one entry for that client.
        # Use client canonicals for addresses/cities. Parse time if present.
        to_create: List[Tuple[Client, Optional[Driver], Optional[time_type], str]] = []
        # Keep a simple “recent time” context for lines where times and names are on separate lines
        last_seen_time: Optional[time_type] = None

        client_keys = list(client_map.keys())
        driver_keys = list(driver_map.keys())

        for line in lines:
            if _looks_like_garbage(line):
                continue
            if LOGI_LINE.match(line):   # <— NEW: skip job-ID lines entirely
                continue
            clean_lines.append(line)


            # find first client in line
            chosen_client: Optional[Client] = None
            for ck in client_keys:
                if ck and ck in clean_lines:
                    chosen_client = client_map[ck]
                    break

            if not chosen_client:
                continue  # no client -> skip

            # optional driver if present
            chosen_driver: Optional[Driver] = None
            for dk in driver_keys:
                if dk and dk in norm_line:
                    chosen_driver = driver_map[dk]
                    break

            to_create.append((chosen_client, chosen_driver, line_time, line))
            # update time context
            if times:
                last_seen_time = line_time

        # --- persist
        created = 0
        if opts["dry"]:
            mode = "DRY-RUN"
        else:
            mode = "WRITE"

        with transaction.atomic():
            for client, driver, start_time, raw in to_create:
                entry = ScheduleEntry(
                    schedule=schedule,
                    company=company,
                    client=client,
                    client_name=client.name,  # freeze label cleanly
                    driver=driver,
                    start_time=start_time,
                    # hydrate from Client canonicals (do not scrape addresses from PDF)
                    pickup_address=(client.pickup_address or ""),
                    pickup_city=(getattr(client, "pickup_city", "") or ""),
                    dropoff_address=(client.dropoff_address or ""),
                    dropoff_city=(getattr(client, "dropoff_city", "") or ""),
                    status="scheduled",
                    notes="",  # optional: store raw line for traceability
                )
                if not opts["dry"]:
                    entry.save()
                created += 1

            if opts["dry"]:
                transaction.set_rollback(True)

        # --- summary
        if opts["show"]:
            self.stdout.write(f"{mode}: parsed {len(lines)} raw lines; {len(clean_lines)} after filtering.")
            self.stdout.write(f"Matched {len(to_create)} client hits; created {created} entries.")
            for client, driver, start_time, raw in to_create[:20]:
                t = start_time.strftime("%H:%M") if start_time else "--:--"
                self.stdout.write(
                    f"  + {client.name} @ {t}"
                    + (f"  (drv: {driver.name})" if driver else "")
                    + f"    <- {raw[:80]}"
                )

        self.stdout.write(
            f"Imported {created} entries into schedule {schedule.id} for {schedule.date} ({mode})."
        )

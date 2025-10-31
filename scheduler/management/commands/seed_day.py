from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date
from django.utils.text import slugify
from django.db import transaction
from scheduler.models import Company, Schedule, ScheduleEntry, Client, Driver
import csv, os, datetime, re

TIME_TOKEN = re.compile(r"^\s*(\d{1,2}):(\d{2})(?:\s*([AP]M))?\s*$", re.I)

def parse_time_token(s: str):
    if not s:
        return None
    m = TIME_TOKEN.match(str(s).strip())
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    ampm = (m.group(3) or "").upper()
    if ampm == "PM" and hh < 12:
        hh += 12
    if ampm == "AM" and hh == 12:
        hh = 0
    try:
        return datetime.time(hour=hh, minute=mm)
    except ValueError:
        return None

# ... imports ...

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--company", required=True)
        parser.add_argument("--date", required=True)
        parser.add_argument("--csv", required=True)
        parser.add_argument("--replace", action="store_true")
        parser.add_argument("--show", action="store_true")
        parser.add_argument("--dry", action="store_true")

    def handle(self, *args, **opts):
        from django.utils.dateparse import parse_date
        import csv

        co = Company.objects.get(name=opts["company"])
        day = parse_date(opts["date"])
        sched, _ = Schedule.objects.get_or_create(company=co, date=day)

        # optional: clear day if --replace
        if opts["replace"]:
            ScheduleEntry.objects.filter(schedule=sched, company=co).delete()

        with open(opts["csv"], newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            created = 0
            for row in reader:
                # look up foreign keys by slug already in your DB
                driver = Driver.objects.filter(company=co, slug=row.get("driver_slug") or "").first()
                client = Client.objects.filter(company=co, slug=row.get("client_slug") or "").first()

                entry = ScheduleEntry(
                    company=co,              # <<< CRITICAL
                    schedule=sched,          # <<< CRITICAL
                    driver=driver,
                    client=client,
                    client_name=(client.name if client else row.get("client_name") or ""),
                    start_time=(row.get("time") or None),
                    status=(row.get("status") or "scheduled"),
                    pickup_address=row.get("pickup_address") or "",
                    pickup_city=row.get("pickup_city") or "",
                    dropoff_address=row.get("dropoff_address") or "",
                    dropoff_city=row.get("dropoff_city") or "",
                )
                if opts["show"]:
                    self.stdout.write(f" + {entry.client_name or '(no name)'} @ {entry.start_time or '—'}")
                if not opts["dry"]:
                    entry.save()
                    created += 1

        self.stdout.write(f"Seeded entries: {created} (dry={opts['dry']})")

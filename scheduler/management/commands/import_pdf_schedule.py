from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from datetime import datetime, time
import re, pathlib
from scheduler.models import Driver, Client, Schedule, ScheduleEntry  # adjust if names differ

ROW = re.compile(
    r"""^(?P<driver>[A-Z]+)\s+(?P<seq>\d+[A-C]?)\s+(?P<when>\d{1,2}:\d{2})\s+
        (?P<member>.+?)\s+(?P<pickup>.+?)\s+(?P<pick_city>[A-Za-z ]+)\s+
        (?P<drop>.+?)\s+(?P<drop_city>[A-Za-z ]+)""",
    re.X
)

def parse_time(hhmm: str):
    # PDF times look like 8:30, 13:30, 0:00, etc. Assume local tz
    h, m = map(int, hhmm.split(":"))
    return time(h, m)

class Command(BaseCommand):
    help = "Import Bahati PDF text export (one day)."

    def add_arguments(self, parser):
        parser.add_argument("txt_path", help="Path to pdftotext -layout output")
        parser.add_argument("--date", required=True, help="YYYY-MM-DD")

    def handle(self, txt_path, date, **_):
        day = make_aware(datetime.strptime(date, "%Y-%m-%d"))
        created = 0
        schedule, _ = Schedule.objects.get_or_create(date=day.date())  # adjust to your model

        for line in pathlib.Path(txt_path).read_text().splitlines():
            line = line.strip()
            if not line or not line[0].isalpha():  # skip headers/blanks
                continue
            m = ROW.match(line)
            if not m:
                continue

            g = m.groupdict()
            driver_name = g["driver"].title()  # e.g. DAVID -> David
            when = parse_time(g["when"])
            member = g["member"].strip()
            pickup = f'{g["pickup"].strip()}, {g["pick_city"].title()}'
            drop   = f'{g["drop"].strip()}, {g["drop_city"].title()}'

            driver, _ = Driver.objects.get_or_create(name=driver_name)  # or username mapping
            client, _ = Client.objects.get_or_create(name=member)

            ScheduleEntry.objects.create(          # field names: adjust to yours
                schedule=schedule,
                driver=driver,
                client=client,
                pickup_address=pickup,
                dropoff_address=drop,
                pickup_time=when,
                status="scheduled",
                source_ref=f"{driver_name} {g['seq']}",
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Imported {created} rows for {date}"))

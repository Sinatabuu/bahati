from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_date
import csv
from scheduler.models import Driver, Client, Schedule, ScheduleEntry  # adjust names if different

class Command(BaseCommand):
    help = "Import drivers.csv, clients.csv and daily_template.csv into DB"

    def add_arguments(self, parser):
        parser.add_argument("--drivers", default="/home/maigwa/work/BAHATI/pdfs/drivers.csv")
        parser.add_argument("--clients", default="/home/maigwa/work/BAHATI/pdfs/clients.csv")
        parser.add_argument("--template", default="/home/maigwa/work/BAHATI/pdfs/daily_template.csv")
        parser.add_argument("--date", default="", help="YYYY-MM-DD to apply if template date is blank")

    @transaction.atomic
    def handle(self, *args, **opts):
        d_csv, c_csv, t_csv = opts["drivers"], opts["clients"], opts["template"]
        default_date = parse_date(opts["date"]) if opts["date"] else None

        # Drivers
        created_d = 0
        try:
            with open(d_csv, newline="") as f:
                for row in csv.DictReader(f):
                    name = (row.get("name") or "").strip()
                    if not name: continue
                    Driver.objects.get_or_create(name=name)
                    created_d += 1
        except FileNotFoundError:
            pass

        # Clients
        created_c = 0
        try:
            with open(c_csv, newline="") as f:
                for row in csv.DictReader(f):
                    name = (row.get("name") or "").strip()
                    if not name: continue
                    pu = (row.get("pickup_address") or "").strip()
                    do = (row.get("dropoff_address") or "").strip()
                    obj, _ = Client.objects.get_or_create(name=name, defaults={})
                    # only set if empty
                    if pu and not getattr(obj, "pickup_address", ""):
                        setattr(obj, "pickup_address", pu)
                    if do and not getattr(obj, "dropoff_address", ""):
                        setattr(obj, "dropoff_address", do)
                    obj.save()
                    created_c += 1
        except FileNotFoundError:
            pass

        # Template to Schedule+Entries (NOTE: ScheduleEntry has NO date; use schedule.date)
        created_e = 0
        try:
            with open(t_csv, newline="") as f:
                for row in csv.DictReader(f):
                    date_str = (row.get("date") or "").strip()
                    day = parse_date(date_str) if date_str else default_date
                    if not day:
                        # skip rows without a usable date
                        continue

                    # Get or create Schedule for that date
                    schedule, _ = Schedule.objects.get_or_create(date=day)

                    drv_name = (row.get("driver_name") or "").strip()
                    cli_name = (row.get("client_name") or "").strip()
                    start_time = (row.get("start_time") or "").strip()
                    pu = (row.get("pickup_address") or "").strip()
                    do = (row.get("dropoff_address") or "").strip()

                    driver = None
                    if drv_name:
                        driver = Driver.objects.filter(name=drv_name).first()

                    client = None
                    if cli_name:
                        client = Client.objects.filter(name=cli_name).first()

                    # Build entry fields we actually have in the model
                    kwargs = {
                        "schedule": schedule,
                        "driver": driver,
                        "client": client,
                        "client_name": cli_name or (getattr(client, "name", None) or ""),
                        "status": "scheduled",
                    }

                    # If your model has these fields:
                    # start_time, pickup_address, dropoff_address
                    if hasattr(ScheduleEntry, "start_time") and start_time:
                        # simple HH:MM parser
                        from datetime import time
                        try:
                            hh, mm = [int(x) for x in start_time.split(":", 1)]
                            kwargs["start_time"] = time(hh, mm)
                        except Exception:
                            pass
                    if hasattr(ScheduleEntry, "pickup_address") and pu:
                        kwargs["pickup_address"] = pu
                    if hasattr(ScheduleEntry, "dropoff_address") and do:
                        kwargs["dropoff_address"] = do

                    ScheduleEntry.objects.create(**kwargs)
                    created_e += 1
        except FileNotFoundError:
            pass

        self.stdout.write(self.style.SUCCESS(
            f"Imported: drivers={created_d}, clients={created_c}, entries={created_e}"
        ))

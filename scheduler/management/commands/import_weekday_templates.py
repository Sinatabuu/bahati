from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import csv
from scheduler.models import (Company, Client, Driver, Vehicle,
                              ScheduleTemplate, ScheduleTemplateEntry)

WEEKDAYS = {"monday":0, "tuesday":1, "wednesday":2, "thursday":3, "friday":4}

class Command(BaseCommand):
    help = "Import a weekday ScheduleTemplate + Entries from CSV"

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--weekday", required=True, choices=WEEKDAYS.keys())
        parser.add_argument("--name", required=True, help="Template name")
        parser.add_argument("--csv", required=True, help="Path to CSV")

    @transaction.atomic
    def handle(self, *args, **opts):
        company_id = opts["company_id"]
        weekday = WEEKDAYS[opts["weekday"]]
        name = opts["name"]
        path = opts["csv"]

        # Create/replace template
        tmpl, _ = ScheduleTemplate.objects.get_or_create(
            company_id=company_id, weekday=weekday, name=name,
            defaults={"active": True}
        )
        tmpl.entries.all().delete()

        # Helper: resolve by slug then by name (case-insensitive)
        def resolve(model, val):
            if not val:
                return None
            obj = model.objects.filter(company_id=company_id, slug=val).first()
            if obj:
                return obj
            return model.objects.filter(company_id=company_id, name__iexact=val).first()

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # normalize keys to lowercase for safety
            headers = [h.lower() for h in reader.fieldnames]
            row_iter = ( {k.lower(): v for k,v in row.items()} for row in reader )

            required = {"order","start_time","client_slug_or_name","driver_slug_or_name","pickup_address","dropoff_address"}
            missing = required - set(headers)
            if missing:
                raise CommandError(f"CSV missing columns: {missing}")

            for row in row_iter:
                order = int(row.get("order") or 0)
                start_time = row["start_time"] or None
                

                client_label  = (row.get("client_slug_or_name") or "").strip()
                driver_label  = (row.get("driver_slug_or_name") or "").strip()
                vehicle_label = (row.get("vehicle_slug_or_name") or "").strip()

                client  = resolve(Client, client_label)
                driver  = resolve(Driver, driver_label)
                vehicle = resolve(Vehicle, vehicle_label)

                ScheduleTemplateEntry.objects.create(
                    template=tmpl, order=order,
                    client=client,   client_name=("" if client  else (client_label  or "")),
                    driver=driver,   driver_name=("" if driver  else (driver_label  or "")),
                    vehicle=vehicle, vehicle_name=("" if vehicle else (vehicle_label or "")),
                    start_time=start_time,
                    pickup_address=(row.get("pickup_address") or "").strip(),
                    dropoff_address=(row.get("dropoff_address") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                )

        self.stdout.write(self.style.SUCCESS(
            f"Imported template '{name}' for {opts['weekday'].title()} from {path}"
        ))

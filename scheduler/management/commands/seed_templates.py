# before
# import csv
# ...
# def handle(self, *args, **opts):
#     csv = opts["csv"]
#     with open(csv, newline="", encoding="utf-8") as f:
#         for row in csv.DictReader(f):

import csv
from django.core.management.base import BaseCommand
from scheduler.models import Company, Driver

class Command(BaseCommand):
    help = "Seed drivers from a CSV"

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True)
        parser.add_argument("--csv", dest="csv_path", required=True)
        parser.add_argument("--dry", action="store_true")

    def handle(self, *args, **opts):
        company = Company.objects.get(name=opts["company"])
        csv_path = opts["csv_path"]
        dry = opts["dry"]

        # let .txt work too
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            created = updated = 0
            for row in reader:
                name = (row.get("name") or "").strip()
                phone = (row.get("phone") or "").strip()
                if not name:
                    continue
                drv, was_created = Driver.objects.update_or_create(
                    company=company, name=name,
                    defaults={"phone": phone}
                )
                created += 1 if was_created else 0
                updated += 0 if was_created else 1
                if dry:
                    drv.delete()
            self.stdout.write(f"Drivers upserted. created={created} updated={updated} (dry={dry})")

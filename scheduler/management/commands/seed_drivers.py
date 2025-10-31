from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from scheduler.models import Company, Driver
import csv, os

class Command(BaseCommand):
    help = "Upsert drivers from a CSV. Lookup key is (company, slug)."

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True, help="Company name")
        parser.add_argument("--csv", required=True, help="Path to drivers CSV")
        parser.add_argument("--dry", action="store_true", help="Dry-run (no writes)")

    def handle(self, *args, **opts):
        company_name = opts["company"].strip()
        csv_path = opts["csv"].strip()
        dry = bool(opts["dry"])

        if not os.path.exists(csv_path):
            raise CommandError(f"CSV not found: {csv_path}")

        try:
            co = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            raise CommandError(f"Company not found: {company_name}")

        created, updated, skipped = 0, 0, 0

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            required = ["name"]
            for r in required:
                if r not in reader.fieldnames:
                    raise CommandError(f"CSV missing required column: {r}")

            for row in reader:
                name = (row.get("name") or "").strip()
                if not name:
                    skipped += 1
                    continue

                want_slug = (row.get("slug") or "").strip() or slugify(name) or "driver"
                phone = (row.get("phone") or "").strip()
                active = (row.get("active") or "").strip().lower()
                active_val = None
                if active in {"1", "true", "yes", "y"}:
                    active_val = True
                elif active in {"0", "false", "no", "n"}:
                    active_val = False

                # Upsert by (company, slug)
                try:
                    drv = Driver.objects.get(company=co, slug=want_slug)
                    # Update only when changed
                    changed = False
                    if drv.name != name:
                        drv.name = name; changed = True
                    if phone and getattr(drv, "phone", "") != phone:
                        drv.phone = phone; changed = True
                    if active_val is not None and getattr(drv, "active", None) != active_val:
                        drv.active = active_val; changed = True
                    if changed and not dry:
                        drv.save()
                        updated += 1
                    elif changed:
                        updated += 1
                except Driver.DoesNotExist:
                    if not dry:
                        drv = Driver(company=co, name=name, slug=want_slug or slugify(name) or "driver")
                        if phone:
                            drv.phone = phone
                        if active_val is not None:
                            drv.active = active_val
                        drv.save()
                    created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Drivers upserted. created={created} updated={updated} skipped={skipped} (dry={dry})"
        ))

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from scheduler.models import Company, Client, Driver
import csv, os

class Command(BaseCommand):
    help = "Upsert clients from a CSV. Lookup key is (company, slug)."

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True, help="Company name")
        parser.add_argument("--csv", required=True, help="Path to clients CSV")
        parser.add_argument("--dry", action="store_true", help="Dry-run (no writes)")
        parser.add_argument("--driver-column", default="default_driver_slug",
                            help="Optional CSV column with a driver slug to set as preferred driver")

    def handle(self, *args, **opts):
        company_name = opts["company"].strip()
        csv_path = opts["csv"].strip()
        dry = bool(opts["dry"])
        driver_col = opts["driver_column"]

        if not os.path.exists(csv_path):
            raise CommandError(f"CSV not found: {csv_path}")

        try:
            co = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            raise CommandError(f"Company not found: {company_name}")

        created, updated, skipped = 0, 0, 0
        warnings = 0

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

                want_slug = (row.get("slug") or "").strip() or slugify(name) or "client"

                # Addresses / cities
                pu_addr = (row.get("pickup_address") or "").strip()
                pu_city = (row.get("pickup_city") or "").strip()
                do_addr = (row.get("dropoff_address") or "").strip()
                do_city = (row.get("dropoff_city") or "").strip()

                phone = (row.get("phone") or "").strip()
                notes = (row.get("notes") or "").strip()

                # Optional default driver by slug
                default_driver_slug = (row.get(driver_col) or "").strip()
                default_driver = None
                if default_driver_slug:
                    try:
                        default_driver = Driver.objects.get(company=co, slug=default_driver_slug)
                    except Driver.DoesNotExist:
                        warnings += 1
                        self.stdout.write(self.style.WARNING(
                            f"Warning: default driver slug not found for client '{name}': {default_driver_slug}"
                        ))

                try:
                    cl = Client.objects.get(company=co, slug=want_slug)
                    changed = False
                    if cl.name != name:
                        cl.name = name; changed = True
                    if pu_addr and getattr(cl, "pickup_address", "") != pu_addr:
                        cl.pickup_address = pu_addr; changed = True
                    if pu_city and getattr(cl, "pickup_city", "") != pu_city:
                        cl.pickup_city = pu_city; changed = True
                    if do_addr and getattr(cl, "dropoff_address", "") != do_addr:
                        cl.dropoff_address = do_addr; changed = True
                    if do_city and getattr(cl, "dropoff_city", "") != do_city:
                        cl.dropoff_city = do_city; changed = True
                    if phone and getattr(cl, "phone", "") != phone:
                        cl.phone = phone; changed = True
                    if notes and getattr(cl, "notes", "") != notes:
                        cl.notes = notes; changed = True
                    if default_driver and getattr(cl, "default_driver_id", None) != default_driver.id:
                        cl.default_driver = default_driver; changed = True

                    if changed and not dry:
                        cl.save()
                        updated += 1
                    elif changed:
                        updated += 1
                except Client.DoesNotExist:
                    if not dry:
                        cl = Client(company=co, slug=want_slug, name=name)
                        cl.pickup_address = pu_addr
                        cl.pickup_city = pu_city
                        cl.dropoff_address = do_addr
                        cl.dropoff_city = do_city
                        if phone: cl.phone = phone
                        if notes: cl.notes = notes
                        if default_driver: cl.default_driver = default_driver
                        cl.save()
                    created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Clients upserted. created={created} updated={updated} skipped={skipped} warnings={warnings} (dry={dry})"
        ))

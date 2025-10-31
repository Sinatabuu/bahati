# scheduler/management/commands/purge_old_locations.py
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from scheduler.models import DriverLocation


class Command(BaseCommand):
    help = "Delete DriverLocation rows older than N days (default 90)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90, help="Age threshold in days.")
        parser.add_argument("--batch-size", type=int, default=5000, help="Delete in batches of this size.")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted, do not write.")
        parser.add_argument("--verbose", action="store_true", help="Print extra progress info.")

    def handle(self, *args, **opts):
        days = opts["days"]
        batch = max(1, opts["batch_size"])
        cutoff = timezone.now() - timedelta(days=days)

        qs = DriverLocation.objects.filter(recorded_at__lt=cutoff).order_by("id")
        total = qs.count()
        self.stdout.write(self.style.NOTICE(f"DriverLocation cutoff: {cutoff.isoformat()}. Candidates: {total}"))

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to purge."))
            return

        deleted_total = 0
        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: no rows will be deleted."))
            return

        while True:
            ids = list(qs.values_list("id", flat=True)[:batch])
            if not ids:
                break
            with transaction.atomic():
                deleted, _ = DriverLocation.objects.filter(id__in=ids).delete()
                deleted_total += deleted
            if opts["verbose"]:
                self.stdout.write(f"Deleted batch: {deleted} (running total {deleted_total})")

        self.stdout.write(self.style.SUCCESS(f"Done. Deleted {deleted_total} DriverLocation rows > {days} days old."))


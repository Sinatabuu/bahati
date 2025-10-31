# scheduler/management/commands/purge_old_notifications.py
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction, models

from scheduler.models import DriverNotification


class Command(BaseCommand):
    help = (
        "Delete DriverNotification rows older than N days (default 180). "
        "By default deletes both read and unread if older than cutoff. "
        "Use --only-read to only delete notifications that have been read."
    )

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=180, help="Age threshold in days.")
        parser.add_argument("--batch-size", type=int, default=5000, help="Delete in batches of this size.")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted, do not write.")
        parser.add_argument("--only-read", action="store_true", help="Purge only notifications with read_at IS NOT NULL.")
        parser.add_argument("--verbose", action="store_true", help="Print extra progress info.")

    def handle(self, *args, **opts):
        days = opts["days"]
        batch = max(1, opts["batch_size"])
        cutoff = timezone.now() - timedelta(days=days)

        base = DriverNotification.objects.filter(created_at__lt=cutoff)
        if opts["only_read"]:
            base = base.filter(read_at__isnull=False)

        qs = base.order_by("id")
        total = qs.count()
        mode = "only read" if opts["only_read"] else "all"
        self.stdout.write(self.style.NOTICE(
            f"DriverNotification cutoff: {cutoff.isoformat()} ({mode}). Candidates: {total}"
        ))

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to purge."))
            return

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: no rows will be deleted."))
            return

        deleted_total = 0
        while True:
            ids = list(qs.values_list("id", flat=True)[:batch])
            if not ids:
                break
            with transaction.atomic():
                deleted, _ = DriverNotification.objects.filter(id__in=ids).delete()
                deleted_total += deleted
            if opts["verbose"]:
                self.stdout.write(f"Deleted batch: {deleted} (running total {deleted_total})")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Deleted {deleted_total} DriverNotification rows > {days} days old."
        ))

# scheduler/management/commands/sync_addresses.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from scheduler.models import Company, Client, ScheduleEntry, ScheduleTemplateEntry


class Command(BaseCommand):
    help = (
        "Sync addresses/cities from Client canonicals to templates and/or schedule entries.\n"
        "Examples:\n"
        "  python manage.py sync_addresses --company 'Bahati Transport' --targets templates --mode force\n"
        "  python manage.py sync_addresses --company 'Bahati Transport' --targets entries --since 2025-10-01 --mode blanks\n"
        "  python manage.py sync_addresses --company 'Bahati Transport' --targets both --mode blanks\n"
    )

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True, help="Company name")
        parser.add_argument("--targets", choices=["templates", "entries", "both"], default="both")
        parser.add_argument("--mode", choices=["blanks", "force"], default="blanks",
                            help="blanks: only fill empty fields; force: overwrite")
        parser.add_argument("--since", help="YYYY-MM-DD (for entries only). Default=today for entries; ignored for templates.")
        parser.add_argument("--until", help="YYYY-MM-DD (for entries only). Optional upper bound.")

    def handle(self, *args, **opts):
        name = opts["company"]
        targets = opts["targets"]
        mode = opts["mode"]
        since = opts.get("since")
        until = opts.get("until")

        try:
            company = Company.objects.get(name=name)
        except Company.DoesNotExist:
            raise CommandError(f"Company '{name}' not found")

        total_templates = 0
        total_entries = 0

        with transaction.atomic():
            if targets in ("templates", "both"):
                total_templates = self._sync_templates(company, mode)

            if targets in ("entries", "both"):
                total_entries = self._sync_entries(company, mode, since, until)

        self.stdout.write(self.style.SUCCESS(
            f"Done. Templates updated: {total_templates} | Entries updated: {total_entries}"
        ))

    def _sync_templates(self, company, mode):
        updated = 0
        clients = Client.objects.filter(company=company).only("id", "name", "pickup_address", "dropoff_address")
        # For each client, find template rows linked by FK or name
        for client in clients:
            q = ScheduleTemplateEntry.objects.filter(template__company=company).filter(
                Q(client=client) | Q(client__isnull=True, client_name__iexact=client.name)
            )
            for e in q:
                if mode == "force":
                    e.pickup_address  = client.pickup_address
                    e.dropoff_address = client.dropoff_address
                    e.save(update_fields=["pickup_address", "dropoff_address", "updated_at"])
                    updated += 1
                else:  # blanks
                    changed = False
                    if not (e.pickup_address or "").strip():
                        e.pickup_address = client.pickup_address
                        changed = True
                    if not (e.dropoff_address or "").strip():
                        e.dropoff_address = client.dropoff_address
                        changed = True
                    if changed:
                        e.save(update_fields=["pickup_address", "dropoff_address", "updated_at"])
                        updated += 1
        return updated

    def _sync_entries(self, company, mode, since, until):
        today = timezone.localdate()
        if not since:
            since_date = today
        else:
            try:
                since_date = timezone.datetime.fromisoformat(since).date()
            except ValueError:
                raise CommandError("--since must be YYYY-MM-DD")
        until_date = None
        if until:
            try:
                until_date = timezone.datetime.fromisoformat(until).date()
            except ValueError:
                raise CommandError("--until must be YYYY-MM-DD")

        qs = ScheduleEntry.objects.select_related("schedule", "client").filter(company=company, schedule__date__gte=since_date)
        if until_date:
            qs = qs.filter(schedule__date__lte=until_date)

        updated = 0
        for e in qs:
            c = e.client
            if not c:
                continue

            if mode == "force":
                e.pickup_address  = c.pickup_address
                e.dropoff_address = c.dropoff_address
                e.pickup_city     = c.pickup_city
                e.dropoff_city    = c.dropoff_city
                e.save(update_fields=[
                    "pickup_address", "dropoff_address", "pickup_city", "dropoff_city", "updated_at"
                ])
                updated += 1
            else:  # blanks
                changed = False
                if not (e.pickup_address or "").strip():
                    e.pickup_address = c.pickup_address
                    changed = True
                if not (e.dropoff_address or "").strip():
                    e.dropoff_address = c.dropoff_address
                    changed = True
                if not (e.pickup_city or "").strip():
                    e.pickup_city = c.pickup_city
                    changed = True
                if not (e.dropoff_city or "").strip():
                    e.dropoff_city = c.dropoff_city
                    changed = True
                if changed:
                    e.save(update_fields=[
                        "pickup_address", "dropoff_address", "pickup_city", "dropoff_city", "updated_at"
                    ])
                    updated += 1
        return updated

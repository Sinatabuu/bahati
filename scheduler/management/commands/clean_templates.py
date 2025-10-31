# scheduler/management/commands/clean_templates.py
from __future__ import annotations
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from scheduler.models import Company, ScheduleTemplate, ScheduleTemplateEntry
from scheduler.utils.normalize import strip_junk, split_addr_city, clean_label

class Command(BaseCommand):
    """
    Normalize ScheduleTemplateEntry rows:
      - Strip route/time tokens from pickup/dropoff fields.
      - Infer cities (via comma or known towns) when possible.
      - If entry has a linked Client, prefer its canonical address/city when entry fields are empty.
      - Optionally write cleansed values back to template entries (addresses only).
      - Optionally backfill Client canonicals if empty.
    """
    help = "Clean and normalize weekday schedule templates."

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True, help="Company name (exact)")
        parser.add_argument("--weekday", type=int, choices=range(0,7), help="Filter a single weekday (0=Mon..6=Sun)")
        parser.add_argument("--apply", action="store_true", help="Persist changes to DB")
        parser.add_argument("--backfill-client", action="store_true",
                            help="If client has blank canonical addr/city, fill from cleaned entry")
        parser.add_argument("--show", action="store_true", help="Print preview lines")

    def handle(self, *args, **opts):
        company_name: str = opts["company"]
        weekday: Optional[int] = opts.get("weekday")
        do_apply: bool = bool(opts.get("apply"))
        backfill_client: bool = bool(opts.get("backfill_client"))
        do_show: bool = bool(opts.get("show"))

        try:
            co = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Company not found: {company_name}"))
            return

        tqs = ScheduleTemplate.objects.filter(company=co, active=True)
        if weekday is not None:
            tqs = tqs.filter(weekday=weekday)

        total_entries = 0
        updated_entries = 0
        updated_clients = 0

        for tmpl in tqs.order_by("weekday", "name"):
            for e in tmpl.entries.all().order_by("order","id"):
                total_entries += 1

                # raw (strip junk first)
                pu_raw = strip_junk(e.pickup_address or "")
                do_raw = strip_junk(e.dropoff_address or "")

                # try to split into addr/city
                pu_addr, pu_city = split_addr_city(pu_raw)
                do_addr, do_city = split_addr_city(do_raw)

                # if client exists, and a field is missing, pull canonical
                c = e.client
                if c:
                    pu_addr = pu_addr or (c.pickup_address or "")
                    pu_city = pu_city or (c.pickup_city or "")
                    do_addr = do_addr or (c.dropoff_address or "")
                    do_city = do_city or (c.dropoff_city or "")

                # Final clean labels (remove headers/noise)
                pu_addr = clean_label(pu_addr)
                do_addr = clean_label(do_addr)

                # nothing resolved? skip
                if not (pu_addr or pu_city or do_addr or do_city):
                    continue

                if do_show:
                    self.stdout.write(
                        f"{tmpl.get_weekday_display():<9} [{tmpl.name}] "
                        f"#{e.id:>4}  PU='{pu_addr}' / '{pu_city}'  DO='{do_addr}' / '{do_city}'"
                    )

                # Write back to template entry (addresses only; template has no city fields)
                changed = False
                new_pu = pu_addr or ""
                new_do = do_addr or ""
                if new_pu != (e.pickup_address or ""):
                    e.pickup_address = new_pu
                    changed = True
                if new_do != (e.dropoff_address or ""):
                    e.dropoff_address = new_do
                    changed = True

                if do_apply and changed:
                    e.save(update_fields=["pickup_address", "dropoff_address"])
                    updated_entries += 1

                # Optionally backfill client canonical (only if blank to avoid overwriting)
                if do_apply and backfill_client and c:
                    c_changed = False
                    if not (c.pickup_address or "").strip() and pu_addr:
                        c.pickup_address = pu_addr; c_changed = True
                    if not (c.pickup_city or "").strip() and pu_city:
                        c.pickup_city = pu_city; c_changed = True
                    if not (c.dropoff_address or "").strip() and do_addr:
                        c.dropoff_address = do_addr; c_changed = True
                    if not (c.dropoff_city or "").strip() and do_city:
                        c.dropoff_city = do_city; c_changed = True
                    if c_changed:
                        c.save(update_fields=[
                            "pickup_address","pickup_city","dropoff_address","dropoff_city","updated_at"
                        ])
                        updated_clients += 1

        self.stdout.write(self.style.SUCCESS(
            f"Templates scanned: entries={total_entries}, updated_entries={updated_entries}, "
            f"backfilled_clients={updated_clients} (apply={do_apply})"
        ))

# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.db import transaction
from scheduler.models import ScheduleEntry
import re

ROUTE_RX = re.compile(r'^[A-Z]{3,}\s+\d+[A-Z]?$', re.I)  # e.g. ERNEST 1A, JOCK 3B

class Command(BaseCommand):
    help = "Backfill pickup/dropoff_address from linked Client when missing, and strip misloaded route labels."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only, no writes.")
        parser.add_argument("--limit", type=int, default=0, help="Limit number of rows (0 = all).")

    def handle(self, *args, **opts):
        dry   = opts.get("dry_run", False)
        limit = int(opts.get("limit") or 0)

        qs = ScheduleEntry.objects.select_related("client").order_by("id")
        if limit > 0:
            qs = qs[:limit]

        scanned = 0
        filled_pick = filled_drop = stripped_pick = stripped_drop = saved = 0

        ctx = transaction.atomic() if not dry else _nullcontext()

        with ctx:
            for e in qs.iterator():
                scanned += 1
                changed = False
                c = e.client

                # Strip route tokens stored as addresses
                if e.pickup_address and ROUTE_RX.match(e.pickup_address.strip()):
                    e.pickup_address = ""
                    stripped_pick += 1
                    changed = True
                if e.dropoff_address and ROUTE_RX.match(e.dropoff_address.strip()):
                    e.dropoff_address = ""
                    stripped_drop += 1
                    changed = True

                # Fill from client if missing
                if (not e.pickup_address) and c and getattr(c, "pickup_address", None):
                    e.pickup_address = c.pickup_address.strip()
                    filled_pick += 1
                    changed = True
                if (not e.dropoff_address) and c and getattr(c, "dropoff_address", None):
                    e.dropoff_address = c.dropoff_address.strip()
                    filled_drop += 1
                    changed = True

                if changed and not dry:
                    e.save(update_fields=["pickup_address", "dropoff_address"])
                    saved += 1

        self.stdout.write(self.style.SUCCESS(
            f"Scanned: {scanned} | "
            f"Filled pickup: {filled_pick} | Filled dropoff: {filled_drop} | "
            f"Stripped pickup-route: {stripped_pick} | Stripped dropoff-route: {stripped_drop} | "
            f"Saved: {saved}{' (dry-run)' if dry else ''}"
        ))


# Minimal nullcontext for all Python versions
try:
    from contextlib import nullcontext as _nullcontext
except ImportError:
    class _nullcontext(object):
        def __enter__(self): return None
        def __exit__(self, *exc): return False

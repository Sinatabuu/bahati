# scheduler/management/commands/backfill_day.py
from __future__ import annotations

import re
from typing import Dict, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_date

from scheduler.models import Company, Client, ScheduleEntry


def _norm(s: str) -> str:
    """Normalize a name for tolerant matching."""
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _build_client_maps(company: Company) -> Tuple[Dict[str, Client], Dict[str, Client]]:
    """
    Returns:
      - by_norm: normalized-name -> Client
      - by_lower: lower(name) -> Client (fast exact)
    """
    by_norm, by_lower = {}, {}
    for c in Client.objects.filter(company=company):
        by_norm[_norm(c.name)] = c
        by_lower[c.name.lower()] = c
    return by_norm, by_lower


def _resolve_client_fk(entry: ScheduleEntry, by_norm: Dict[str, Client], by_lower: Dict[str, Client]) -> Client | None:
    """Try to find a Client for this entry based on client_name text."""
    if entry.client_id:
        return entry.client

    name = (entry.client_name or "").strip()
    if not name:
        return None

    # fast exact (case-insensitive)
    c = by_lower.get(name.lower())
    if c:
        return c

    # normalized exact
    c = by_norm.get(_norm(name))
    if c:
        return c

    # loose contains either way
    n = _norm(name)
    for cnorm, cobj in by_norm.items():
        if n in cnorm or cnorm in n:
            return cobj

    return None


def _hydrate_from_client(entry: ScheduleEntry, *, force: bool = False):
    """Fill denormalized fields from Client profile."""
    c = entry.client
    if not c:
        return

    # Always ensure client_name is present for the day
    if not entry.client_name:
        entry.client_name = c.name

    if force:
        entry.pickup_address  = c.pickup_address
        entry.dropoff_address = c.dropoff_address
        entry.pickup_city     = getattr(c, "pickup_city", "") or ""
        entry.dropoff_city    = getattr(c, "dropoff_city", "") or ""
    else:
        if not (entry.pickup_address or "").strip():
            entry.pickup_address = c.pickup_address
        if not (entry.dropoff_address or "").strip():
            entry.dropoff_address = c.dropoff_address
        if not (entry.pickup_city or "").strip():
            entry.pickup_city = getattr(c, "pickup_city", "") or ""
        if not (entry.dropoff_city or "").strip():
            entry.dropoff_city = getattr(c, "dropoff_city", "") or ""


class Command(BaseCommand):
    help = (
        "Backfill a day's ScheduleEntry rows: attach Client FKs by name and copy canonical "
        "pickup/dropoff + cities from Client profiles. Use --dry for a dry run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date", required=True, help="Target date in YYYY-MM-DD (e.g. 2025-10-07)"
        )
        parser.add_argument(
            "--company", required=True, help="Company name (e.g. 'Bahati Transport')"
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite addresses/cities from Client even if entry already has values.",
        )
        parser.add_argument(
            "--dry",
            action="store_true",
            help="Dry run: show counts, no writes.",
        )
        # Use --show instead of -v/--verbose to avoid Django verbosity conflict
        parser.add_argument(
            "--show",
            action="store_true",
            help="Print a few sample rows before/after.",
        )

    def handle(self, *args, **opts):
        date_str = opts["date"].strip()
        company_name = opts["company"].strip()
        force = bool(opts["force"])
        dry = bool(opts["dry"])
        show = bool(opts["show"])

        target_date = parse_date(date_str)
        if not target_date:
            raise CommandError("Invalid --date. Use YYYY-MM-DD.")

        try:
            company = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            raise CommandError(f"Company not found: {company_name!r}")

        qs = (
            ScheduleEntry.objects
            .select_related("client", "schedule", "driver")
            .filter(company=company, schedule__date=target_date)
            .order_by("start_time", "id")
        )

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING(f"No entries for {company.name} on {target_date}."))
            return

        # Show initial blanks
        def counts(label: str):
            pu_blank = qs.filter(Q(pickup_address__isnull=True) | Q(pickup_address="")).count()
            do_blank = qs.filter(Q(dropoff_address__isnull=True) | Q(dropoff_address="")).count()
            puc_blank = qs.filter(Q(pickup_city__isnull=True) | Q(pickup_city="")).count()
            doc_blank = qs.filter(Q(dropoff_city__isnull=True) | Q(dropoff_city="")).count()
            no_client = qs.filter(client__isnull=True).count()
            self.stdout.write(
                f"{label}: total={total} no_client={no_client} "
                f"PU_addr_blank={pu_blank} DO_addr_blank={do_blank} "
                f"PU_city_blank={puc_blank} DO_city_blank={doc_blank}"
            )

        counts("Before")

        if show:
            for e in qs[:5]:
                self.stdout.write(
                    f"  [#{e.id}] name={e.client_name!r} client={e.client and e.client.name!r} "
                    f"PU={e.pickup_address!r}/{getattr(e, 'pickup_city', '')!r} "
                    f"DO={e.dropoff_address!r}/{getattr(e, 'dropoff_city', '')!r}"
                )

        by_norm, by_lower = _build_client_maps(company)

        @transaction.atomic
        def _apply():
            resolved, hydrated, overwritten = 0, 0, 0

            # 1) Resolve missing Client FKs by name
            for e in qs.filter(client__isnull=True).exclude(client_name__isnull=True).exclude(client_name=""):
                c = _resolve_client_fk(e, by_norm, by_lower)
                if c:
                    e.client = c
                    if not e.client_name:
                        e.client_name = c.name
                    e.save(update_fields=["client", "client_name", "updated_at"])
                    resolved += 1

            # 2) Hydrate denormalized fields
            for e in qs.select_related("client"):
                if not e.client:
                    continue

                before = (
                    e.pickup_address or "",
                    e.dropoff_address or "",
                    getattr(e, "pickup_city", "") or "",
                    getattr(e, "dropoff_city", "") or "",
                )

                _hydrate_from_client(e, force=force)

                e.save(update_fields=[
                    "client_name",
                    "pickup_address", "dropoff_address",
                    "pickup_city", "dropoff_city",
                    "updated_at",
                ])
                hydrated += 1

                after = (
                    e.pickup_address or "",
                    e.dropoff_address or "",
                    getattr(e, "pickup_city", "") or "",
                    getattr(e, "dropoff_city", "") or "",
                )
                if force and before != after:
                    overwritten += 1

            return resolved, hydrated, overwritten

        if dry:
            self.stdout.write(self.style.WARNING("Dry run: no database changes will be committed."))
            with transaction.atomic():
                resolved, hydrated, overwritten = _apply()
                transaction.set_rollback(True)
        else:
            resolved, hydrated, overwritten = _apply()

        self.stdout.write(self.style.SUCCESS(
            f"Linked clients: {resolved}, hydrated entries: {hydrated}, "
            f"{'overwrote fields: ' + str(overwritten) if force else 'filled blanks only'}"
        ))

        counts("After")

        if show:
            for e in qs[:5]:
                self.stdout.write(
                    f"  [#{e.id}] name={e.client_name!r} client={e.client and e.client.name!r} "
                    f"PU={e.pickup_address!r}/{getattr(e, 'pickup_city', '')!r} "
                    f"DO={e.dropoff_address!r}/{getattr(e, 'dropoff_city', '')!r}"
                )

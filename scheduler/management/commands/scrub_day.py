# scheduler/management/commands/scrub_day.py
from __future__ import annotations

import re
from datetime import date as date_type
from typing import Iterable, Set

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

from scheduler.models import Company, Schedule, ScheduleEntry, Client


NOISE_DEFAULT: Set[str] = {
    "MEMBER", "NAME", "PHONE",
    "JOCK 4",  # table artifact
    "14:30", "8:00", "7:30", "2:15",  # stray times that slipped into addr fields
    "",  # treat pure empties uniformly
}

HEADER_PATTERNS = [
    re.compile(r"^\s*PICK\s*UP\s*MEMBER\s*$", re.I),
    re.compile(r"^\s*TIME\s*NAME\s*$", re.I),
]

# times like 7:00, 07:00, 7:20 AM
TIME_TOKEN_RE = re.compile(r"^\s*\d{1,2}:\d{2}(\s*[AP]M)?\s*$", re.I)


def is_header(name: str) -> bool:
    n = (name or "").strip()
    for rx in HEADER_PATTERNS:
        if rx.match(n):
            return True
    return False


def is_noise_token(s: str, noise: Set[str]) -> bool:
    t = (s or "").strip()
    if t in noise:
        return True
    if TIME_TOKEN_RE.match(t):
        return True
    return False


class Command(BaseCommand):
    help = "Scrub a day's ScheduleEntries: remove header rows, clear noise tokens so repair_day can hydrate."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, help="YYYY-MM-DD")
        parser.add_argument("--company", required=True, help="Company name")
        parser.add_argument(
            "--noise",
            nargs="*",
            default=[],
            help="Extra noise tokens to blank out in pickup/dropoff fields.",
        )
        parser.add_argument("--dry", action="store_true", help="Dry run (no DB changes)")
        parser.add_argument("--show", action="store_true", help="Print before/after samples")
        # tiny helper to link tricky names -> client (optional)
        parser.add_argument(
            "--link",
            action="append",
            default=[],
            metavar="NAME==CLIENT_NAME",
            help='Optionally map stray names to a Client, e.g. --link "BABRA C==Babra C"',
        )

    def handle(self, *args, **opts):
        raw_date = opts["date"]
        day = parse_date(raw_date)
        if not day:
            raise CommandError(f"Bad --date {raw_date!r}")

        company_name = opts["company"].strip()
        try:
            company = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            raise CommandError(f"Company not found: {company_name}")

        schedule = Schedule.objects.filter(company=company, date=day).first()
        if not schedule:
            raise CommandError(f"No schedule for {company_name} on {day.isoformat()}")

        noise = NOISE_DEFAULT.union({t.strip() for t in opts["noise"] if t is not None})

        # Optional link map
        link_pairs = {}
        for spec in opts["link"]:
            if "==" not in spec:
                raise CommandError(f"--link must be NAME==CLIENT_NAME, got {spec!r}")
            k, v = [p.strip() for p in spec.split("==", 1)]
            if k and v:
                link_pairs[k.lower()] = v

        qs = (
            ScheduleEntry.objects
            .filter(schedule=schedule, is_deleted=False)
            .select_related("client")
            .order_by("start_time", "id")
        )

        if opts["show"]:
            self._print_snapshot("Before", qs)

        @transaction.atomic
        def scrub():
            deleted_headers = 0
            deleted_garbage = 0
            cleaned_fields = 0
            linked = 0

            # 1) delete header rows by name
            for e in qs:
                if is_header(e.client_name or ""):
                    e.is_deleted = True
                    e.save(update_fields=["is_deleted", "updated_at"])
                    deleted_headers += 1

            # Re-pull active rows after header delete
            active = (
                ScheduleEntry.objects
                .filter(schedule=schedule, is_deleted=False)
                .select_related("client")
            )

            # 2) blank out noise tokens in PU/DO (and cities if present)
            for e in active:
                changed = False
                if is_noise_token(e.pickup_address, noise):
                    e.pickup_address = ""
                    changed = True
                if is_noise_token(e.dropoff_address, noise):
                    e.dropoff_address = ""
                    changed = True

                # if your model has city fields (it does)
                if hasattr(e, "pickup_city") and is_noise_token(getattr(e, "pickup_city", ""), noise):
                    e.pickup_city = ""
                    changed = True
                if hasattr(e, "dropoff_city") and is_noise_token(getattr(e, "dropoff_city", ""), noise):
                    e.dropoff_city = ""
                    changed = True

                # Some imports shoved the whole line into pickup_address; if that line
                # looks like a person line (two+ words plus a number street), leave it;
                # otherwise if it looks like pure driver slot like "JOSHUA 2", blank it.
                driver_slot_like = re.compile(r"^[A-Z ]+\s+\d+[A-Z]?$")
                if driver_slot_like.match((e.pickup_address or "").strip()):
                    e.pickup_address = ""
                    changed = True

                if changed:
                    e.save(update_fields=[
                        "pickup_address", "dropoff_address",
                        "pickup_city", "dropoff_city", "updated_at"
                    ])
                    cleaned_fields += 1

            # 3) optional: link stray names to a client (exact/contains fallback too)
            if link_pairs:
                clients = list(Client.objects.filter(company=company))
                by_lower = {c.name.lower(): c for c in clients}

                for e in active.filter(client__isnull=True):
                    key = (e.client_name or "").strip().lower()
                    target_name = link_pairs.get(key)
                    if not target_name:
                        continue
                    c = by_lower.get(target_name.lower())
                    if not c:
                        c = next((x for x in clients if target_name.lower() in x.name.lower()), None)
                    if c:
                        e.client = c
                        e.client_name = e.client_name or c.name
                        e.save(update_fields=["client", "client_name", "updated_at"])
                        linked += 1

            return deleted_headers, deleted_garbage, cleaned_fields, linked

        if opts["dry"]:
            # wrap in atomic but rollback by raising
            try:
                with transaction.atomic():
                    stats = scrub()
                    raise RuntimeError("__dryrun__")
            except RuntimeError as ex:
                if str(ex) != "__dryrun__":
                    raise
                dh, dg, cf, ln = (0, 0, 0, 0) if "stats" not in locals() else stats
                self.stdout.write(self.style.WARNING(
                    f"Dry run: deleted_headers={dh} deleted_garbage={dg} cleaned_fields={cf} linked={ln}"
                ))
        else:
            dh, dg, cf, ln = scrub()
            self.stdout.write(self.style.SUCCESS(
                f"Committed: deleted_headers={dh} deleted_garbage={dg} cleaned_fields={cf} linked={ln}"
            ))

        # After snapshot
        qs_after = (
            ScheduleEntry.objects
            .filter(schedule=schedule, is_deleted=False)
            .order_by("start_time", "id")
        )
        if opts["show"]:
            self._print_snapshot("After", qs_after)

    def _print_snapshot(self, label: str, qs):
        from django.db.models import Q
        total = qs.count()
        no_client = qs.filter(client__isnull=True).count()
        pu_blank = qs.filter(Q(pickup_address__isnull=True) | Q(pickup_address="")).count()
        do_blank = qs.filter(Q(dropoff_address__isnull=True) | Q(dropoff_address="")).count()
        try:
            pu_city_blank = qs.filter(Q(pickup_city__isnull=True) | Q(pickup_city="")).count()
            do_city_blank = qs.filter(Q(dropoff_city__isnull=True) | Q(dropoff_city="")).count()
        except Exception:
            pu_city_blank = do_city_blank = 0

        self.stdout.write(
            f"{label}: total={total} no_client={no_client} "
            f"PU_addr_blank={pu_blank} DO_addr_blank={do_blank} "
            f"PU_city_blank={pu_city_blank} DO_city_blank={do_city_blank}"
        )

        sample = list(qs[:5])
        for e in sample:
            self.stdout.write(
                f"  [#{e.id}] name={e.client_name!r} "
                f"PU={e.pickup_address!r}/{getattr(e,'pickup_city','')!r} "
                f"DO={e.dropoff_address!r}/{getattr(e,'dropoff_city','')!r} "
                f"t={getattr(e,'start_time',None)}"
            )

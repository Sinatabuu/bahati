# scheduler/management/commands/infer_cities.py
from __future__ import annotations
import re
from collections import Counter, defaultdict
from typing import Iterable, Optional, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_date

from scheduler.models import Company, Client, ScheduleEntry

CITY_WORD = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")

# Seed list from the data you showed (extend as you like)
SEED_CITIES = {
    "Lowell", "Dracut", "Concord", "Boston", "Chelmsford", "Newton",
    "Newtonville", "Lunenburg", "Pepperell", "Littleton", "Haverhill",
    "Lawrence", "Andover", "North Andover", "Methuen", "Billerica",
    "Tewksbury", "Woburn", "Reading", "Wilmington", "Lynn", "Salem",
}

def _extract_city_candidates(text: str) -> Iterable[str]:
    """
    Heuristic: look for capitalized word sequences; keep ones that match our known/seed city list.
    We’re conservative to avoid street names.
    """
    if not text:
        return []
    found = set()
    for m in CITY_WORD.finditer(text):
        s = m.group(1).strip()
        if s in SEED_CITIES:
            found.add(s)
    return found

def _best_city_from_texts(texts: Iterable[str]) -> Optional[str]:
    c = Counter()
    for t in texts:
        for cand in _extract_city_candidates(t or ""):
            c[cand] += 1
    if not c:
        return None
    return c.most_common(1)[0][0]

class Command(BaseCommand):
    help = (
        "Infer and backfill missing pickup/dropoff city fields.\n"
        "Phase A: infer Client cities from all their ScheduleEntry addresses.\n"
        "Phase B: hydrate ScheduleEntry cities from their Client profile."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True, help="Company name, e.g. 'Bahati Transport'")
        parser.add_argument("--date-min", help="Optional lower bound (YYYY-MM-DD) to limit entries scanned")
        parser.add_argument("--date-max", help="Optional upper bound (YYYY-MM-DD) to limit entries scanned")
        parser.add_argument("--dry", action="store_true", help="Dry run (no writes)")
        parser.add_argument("--show", action="store_true", help="Show sample changes")

    def handle(self, *args, **opts):
        company_name = opts["company"].strip()
        date_min = parse_date(opts["date_min"]) if opts.get("date_min") else None
        date_max = parse_date(opts["date_max"]) if opts.get("date_max") else None
        dry = bool(opts["dry"])
        show = bool(opts["show"])

        try:
            company = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            raise CommandError(f"Company not found: {company_name!r}")

        entry_q = ScheduleEntry.objects.select_related("client", "schedule").filter(company=company)
        if date_min:
            entry_q = entry_q.filter(schedule__date__gte=date_min)
        if date_max:
            entry_q = entry_q.filter(schedule__date__lte=date_max)

        self.stdout.write(f"Scanning {entry_q.count()} entries for {company.name}")

        # ---------- Phase A: infer client cities from entries ----------
        # Build per-client address corpus
        client_pick_texts: dict[int, list[str]] = defaultdict(list)
        client_drop_texts: dict[int, list[str]] = defaultdict(list)

        for e in entry_q.exclude(client__isnull=True):
            cid = e.client_id
            if e.pickup_address:
                client_pick_texts[cid].append(e.pickup_address)
            if e.dropoff_address:
                client_drop_texts[cid].append(e.dropoff_address)
            # If entry addresses contain “City State” blobs you imported, those help too.

        client_updates = []
        for c in Client.objects.filter(company=company):
            want_pick = not (c.pickup_city or "").strip()
            want_drop = not (c.dropoff_city or "").strip()
            if not want_pick and not want_drop:
                continue

            pick_city = _best_city_from_texts(client_pick_texts.get(c.id, [])) if want_pick else None
            drop_city = _best_city_from_texts(client_drop_texts.get(c.id, [])) if want_drop else None

            if pick_city or drop_city:
                client_updates.append((c, pick_city, drop_city))

        if dry:
            self.stdout.write(self.style.WARNING(f"[DRY] Would update {len(client_updates)} clients with inferred cities"))
        else:
            with transaction.atomic():
                for c, pcity, dcity in client_updates:
                    changed_fields = []
                    if pcity:
                        c.pickup_city = pcity
                        changed_fields.append("pickup_city")
                    if dcity:
                        c.dropoff_city = dcity
                        changed_fields.append("dropoff_city")
                    if changed_fields:
                        c.save(update_fields=changed_fields + ["updated_at"])
                self.stdout.write(self.style.SUCCESS(f"Updated {len(client_updates)} client city fields"))

        # ---------- Phase B: hydrate entries’ cities from client ----------
        fill_q = entry_q.select_related("client").filter(
            Q(pickup_city__isnull=True) | Q(pickup_city="") |
            Q(dropoff_city__isnull=True) | Q(dropoff_city="")
        ).exclude(client__isnull=True)

        self.stdout.write(f"Hydrating entry city blanks from Client profile… candidates={fill_q.count()}")

        def _city_or_blank(v: Optional[str]) -> str:
            return (v or "").strip()

        changed = 0
        samples = []
        if dry:
            for e in fill_q[:10]:
                samples.append((e.id, e.client and e.client.name, e.pickup_city, e.dropoff_city,
                                e.client and e.client.pickup_city, e.client and e.client.dropoff_city))
            self.stdout.write(self.style.WARNING(f"[DRY] Would fill up to {fill_q.count()} entry cities"))
        else:
            with transaction.atomic():
                for e in fill_q:
                    if not e.client:
                        continue
                    before = (e.pickup_city, e.dropoff_city)
                    if not _city_or_blank(e.pickup_city):
                        e.pickup_city = _city_or_blank(e.client.pickup_city)
                    if not _city_or_blank(e.dropoff_city):
                        e.dropoff_city = _city_or_blank(e.client.dropoff_city)
                    after = (e.pickup_city, e.dropoff_city)
                    if before != after:
                        e.save(update_fields=["pickup_city", "dropoff_city", "updated_at"])
                        changed += 1
                        if len(samples) < 10 and show:
                            samples.append((e.id, e.client and e.client.name, before, after))
            self.stdout.write(self.style.SUCCESS(f"Hydrated {changed} entry city fields from Client"))

        if show and samples:
            self.stdout.write("Sample updates:")
            for row in samples:
                self.stdout.write(f"  {row}")

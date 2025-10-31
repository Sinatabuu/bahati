# scheduler/management/commands/import_csv_schedule.py
import csv
from datetime import datetime, time
from pathlib import Path
from typing import Optional, Iterable, Sequence, Dict, Any

from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.db import transaction

def norm(s): return (s or "").strip()
def parse_time(s: str) -> Optional[time]:
    s = norm(s)
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%H%M"):
        try: return datetime.strptime(s, fmt).time()
        except ValueError: pass
    if s.isdigit():
        v = int(s)
        if 0 <= v < 2400:
            return time(hour=v//100, minute=v%100)
    return None
def pick(headers: Sequence[str], *cand: Iterable[str]) -> Optional[str]:
    if not headers: return None
    lower = {str(h).strip().lower(): h for h in headers}
    for block in cand:
        if isinstance(block, (list, tuple)):
            for c in block:
                k = str(c).strip().lower()
                if k in lower: return lower[k]
        else:
            k = str(block).strip().lower()
            if k in lower: return lower[k]
    return None

class Command(BaseCommand):
    help = "Import schedule CSV into ScheduleEntry"

    def add_arguments(self, p):
        p.add_argument("csv_path")
        p.add_argument("--date", dest="day", help="YYYY-MM-DD override for all rows")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--verbose", action="store_true")
        p.add_argument("--create-drivers", action="store_true", help="Create missing Driver rows")

    def handle(self, *args, **opts):
        verbosity = int(opts.get("verbosity", 1))
        csv_path = Path(opts["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"CSV not found: {csv_path}")

        Entry = apps.get_model("scheduler", "ScheduleEntry")
        Driver = apps.get_model("scheduler", "Driver")

        target_date = None
        if opts.get("day"):
            try:
                target_date = datetime.strptime(opts["day"], "%Y-%m-%d").date()
            except ValueError as e:
                raise CommandError(f"--date must be YYYY-MM-DD: {e}")

        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            r = csv.DictReader(f)
            headers = r.fieldnames or []
            if not headers:
                raise CommandError("No header row")

            self.stdout.write(self.style.NOTICE(f"Headers: {headers}"))

            key_time  = pick(headers, ("time","pickup time","pu time","start","start time","appointment time"))
            key_driver = pick(headers, ("driver","driver_name","assigned","chauffeur"))
            key_client = pick(headers, ("client","member","passenger","patient","name","rider","client_name"))

            k_pick = pick(headers, ("pickup","pickup address","origin","from","from address"))
            k_drop = pick(headers, ("dropoff","dropoff address","destination","to","to address"))
            k_ps   = pick(headers, ("address pick","address_pick"))
            k_pc   = pick(headers, ("city pick","city_pick","pickup city","pickup_city"))
            k_ds   = pick(headers, ("drop address","address drop","drop_address"))
            k_dc   = pick(headers, ("drop city","drop_city"))
            k_date = pick(headers, ("date","day","service_date","schedule_date"))

            self.stdout.write(self.style.SUCCESS("Detected columns: " + str({
                "time": key_time, "driver": key_driver, "client": key_client,
                "pick_street": k_pick or k_ps, "pick_city": k_pc,
                "drop_street": k_drop or k_ds, "drop_city": k_dc,
                "date": k_date
            })))

            created = updated = row_idx = 0

            @transaction.atomic
            def import_all(commit: bool):
                nonlocal created, updated, row_idx
                for raw in r:
                    row_idx += 1

                    # date
                    d = target_date
                    if d is None and k_date:
                        ds = norm(raw.get(k_date, ""))
                        if ds:
                            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                                try:
                                    d = datetime.strptime(ds, fmt).date()
                                    break
                                except ValueError:
                                    pass
                    if d is None:
                        raise CommandError(f"Row {row_idx}: missing date")

                    t1 = parse_time(raw.get(key_time, "")) if key_time else None
                    driver_str = norm(raw.get(key_driver, "")) if key_driver else ""
                    client_str = norm(raw.get(key_client, "")) if key_client else ""

                    # addresses
                    if k_pick and "address" in k_pick.lower():
                        pu_addr = norm(raw.get(k_pick, ""))  # one-column form
                    else:
                        pu_addr = ", ".join([x for x in [norm(raw.get(k_ps, "")), norm(raw.get(k_pc, ""))] if x])

                    if k_drop and "address" in k_drop.lower():
                        do_addr = norm(raw.get(k_drop, ""))  # one-column form
                    else:
                        do_addr = ", ".join([x for x in [norm(raw.get(k_ds, "")), norm(raw.get(k_dc, ""))] if x])

                    # driver
                    drv = None
                    if driver_str:
                        drv = Driver.objects.filter(name__iexact=driver_str).first()
                        if not drv and opts.get("create_drivers"):
                            drv = Driver.objects.create(name=driver_str)

                    # build
                    kw: Dict[str, Any] = dict(
                        date=d,
                        client_name=client_str or "",
                        pickup_address=pu_addr or "",
                        dropoff_address=do_addr or "",
                        status="scheduled",
                    )
                    if t1: kw["start_time"] = t1
                    if drv: kw["driver"] = drv

                    if opts.get("verbose") or verbosity >= 2:
                        self.stdout.write(f"Row {row_idx} → {kw}")

                    # upsert: date + driver + start_time (or date+start_time)
                    lookup = {"date": d}
                    if drv: lookup["driver"] = drv
                    if t1:  lookup["start_time"] = t1
                    obj = Entry.objects.filter(**lookup).first()

                    if obj:
                        for k, v in kw.items(): setattr(obj, k, v)
                        if not opts["dry_run"]: obj.save()
                        updated += 1
                    else:
                        obj = Entry(**kw)
                        if not opts["dry_run"]: obj.save()
                        created += 1

                if opts["dry_run"]:
                    raise transaction.TransactionManagementError("dry-run rollback")

            try:
                import_all(commit=not opts["dry_run"])
            except transaction.TransactionManagementError:
                pass

            self.stdout.write(self.style.SUCCESS(f"Done. created={created} updated={updated} (dry_run={opts['dry_run']})"))

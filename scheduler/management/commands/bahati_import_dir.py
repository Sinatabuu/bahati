import re, csv, datetime as dt
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from django.apps import apps

MONTHS = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'SEPT':9,'OCT':10,'NOV':11,'DEC':12}

def parse_date_from_name(name: str, default_year: int|None=None) -> dt.date|None:
    s = name.upper().replace('_',' ').replace('-',' ')
    s = re.sub(r'\s+',' ', s)
    m = re.search(r'(20\d{2})[^\d]([01]?\d)[^\d]([0-3]?\d)', s)
    if m:
        y, mo, d = map(int, m.groups()); return dt.date(y, mo, d)
    m = re.search(r'\b([A-Z]{3,9})\s+([0-3]?\d)(?:ST|ND|RD|TH)?(?:\s+(20\d{2}))?\b', s)
    if m:
        mon_raw, day_str, year_str = m.groups()
        mon = MONTHS.get(mon_raw[:3]); 
        if mon:
            return dt.date(int(year_str) if year_str else (default_year or dt.date.today().year), mon, int(day_str))
    return None

def norm_header(h: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (h or '').strip().lower())

def parse_time_any(txt: str) -> dt.time|None:
    if not txt: return None
    s = txt.strip().upper().replace('.', ':')
    ampm = None
    m = re.search(r'\b(AM|PM)\b', s)
    if m:
        ampm = m.group(1); s = s.replace('AM','').replace('PM','').strip()
    if ':' in s:
        hh, mm = s.split(':', 1)
    else:
        s = re.sub(r'\D+','', s)
        if not s: return None
        if len(s) == 3: hh, mm = s[0], s[1:]
        else: hh, mm = s[:2], s[2:4]
    try:
        h, m = int(hh), int(mm)
        if ampm == 'PM' and h != 12: h += 12
        if ampm == 'AM' and h == 12: h = 0
        return dt.time(h, m)
    except Exception:
        return None

CANDIDATES = {
    "member": ["member","membername","membernames","client","clientname","clientnames","name","patient","patientname"],
    "time":   ["pickuptime","pickup","putime","time","pu","put","p/u","p/utime","pucollecttime","collectiontime","appttime","appointmenttime"],
    "paddr":  ["pickupaddress","pickup","pickupaddr","pickuplocation","putaddress","puaddress","p/uaddress","collectionaddress","origin","originaddress","addresspick","pickaddress","addresspickup"],
    "daddr":  ["dropoffaddress","dropoff","drop","do","destination","destinationaddress","droplocation","returnaddress","dropaddress","dropaddr"],
    "phone":  ["phone","phonenumber","contact","tel","telephone"],
    "driver": ["driver","drivername","assigneddriver"]
}

def choose_header(cols_norm, keys):
    for k in keys:
        if k in cols_norm: return cols_norm[k]
    return None

class Command(BaseCommand):
    help = "Import a directory of CSVs into ScheduleEntry. Detects numeric headers and uses next row as labels."

    def add_arguments(self, parser):
        parser.add_argument('--dir', required=True, help='Directory containing CSV files')
        parser.add_argument('--assume-year', type=int, default=dt.date.today().year)
        parser.add_argument('--mode', choices=['sync','replace'], default='sync')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--verbose', action='store_true')
        parser.add_argument('--only', help='Substring filter: import files whose name contains this text')

    @transaction.atomic
    def handle(self, *args, **opts):
        base = Path(opts['dir'])
        assume_year = opts['assume_year']; mode = opts['mode']; dry = opts['dry_run']
        verbose = opts['verbose']; only = opts.get('only')

        ScheduleEntry = apps.get_model('scheduler', 'ScheduleEntry')
        Driver        = apps.get_model('scheduler', 'Driver')
        Schedule      = apps.get_model('scheduler', 'Schedule')

        files = sorted(p for p in base.iterdir() if p.suffix.lower()=='.csv')
        if only:
            files = [p for p in files if only in p.name]
        if not files:
            self.stdout.write(self.style.WARNING("No CSV files found.")); return

        day_stats = {}
        for f in files:
            day = parse_date_from_name(f.name, default_year=assume_year)
            if not day:
                self.stdout.write(self.style.WARNING(f"Skip (no date parsed): {f.name}")); continue

            if not dry:
                Schedule.objects.get_or_create(date=day, defaults={'status':'draft'})
            if mode == 'replace' and not dry:
                ScheduleEntry.objects.filter(date=day).delete()

            created = 0; skipped = 0; skipped_missing_member = 0

            with f.open('r', encoding='utf-8', errors='ignore', newline='') as fh:
                rows = list(csv.reader(fh))
            if not rows:
                self.stdout.write(self.style.WARNING(f"{f.name}: empty")); continue

            # Detect header row
            raw_headers = rows[0]
            numeric_headers = all((h or '').strip().isdigit() for h in raw_headers)
            header_idx = 1 if (numeric_headers and len(rows)>=2) else 0

            # Heuristic: if first row isn't numeric but doesn't contain 'member', try row 2
            if header_idx == 0:
                tokens0 = {norm_header(h) for h in raw_headers}
                if 'member' not in tokens0 and len(rows) >= 2:
                    tokens1 = {norm_header(h) for h in rows[1]}
                    if 'member' in tokens1:
                        header_idx = 1

            headers = rows[header_idx]
            data_rows = rows[header_idx+1:]

            # Ensure non-empty header names
            headers = [h if (h and h.strip()) else f"col_{i}" for i,h in enumerate(headers)]

            if verbose:
                self.stdout.write(self.style.HTTP_INFO(f"{f.name}: day={day} header_idx={header_idx} headers={headers}"))

            def iter_dict():
                for r in data_rows:
                    if len(r) < len(headers):
                        r = r + ['']*(len(headers)-len(r))
                    elif len(r) > len(headers):
                        r = r[:len(headers)]
                    yield dict(zip(headers, r))

            cols_norm = {norm_header(h): h for h in headers}
            h_member = choose_header(cols_norm, CANDIDATES['member'])
            h_time   = choose_header(cols_norm, CANDIDATES['time'])
            h_paddr  = choose_header(cols_norm, CANDIDATES['paddr'])
            h_daddr  = choose_header(cols_norm, CANDIDATES['daddr'])
            h_phone  = choose_header(cols_norm, CANDIDATES['phone'])
            h_driver = choose_header(cols_norm, CANDIDATES['driver'])

            if verbose:
                self.stdout.write(self.style.HTTP_INFO(
                    f" map: member={h_member} time={h_time} paddr={h_paddr} daddr={h_daddr} phone={h_phone} driver={h_driver}"
                ))
                # show a sample row
                it = iter_dict()
                sample = next(it, None)
                if sample:
                    self.stdout.write(self.style.HTTP_INFO(f" sample: { {k: sample.get(v) for k,v in [('member',h_member),('time',h_time),('paddr',h_paddr),('daddr',h_daddr),('phone',h_phone),('driver',h_driver)]} }"))

            for i, row in enumerate(iter_dict(), start=header_idx+2):
                member = (row.get(h_member) or '').strip() if h_member else ''
                if not member:
                    skipped += 1; skipped_missing_member += 1; continue

                t_raw = (row.get(h_time) or '').strip() if h_time else ''
                start_time = parse_time_any(t_raw)
                paddr = (row.get(h_paddr) or '').strip() if h_paddr else ''
                daddr = (row.get(h_daddr) or '').strip() if h_daddr else ''
                phone = (row.get(h_phone) or '').strip() if h_phone else ''
                dname = (row.get(h_driver) or '').strip() if h_driver else ''

                # duplicate guard only when time exists
                if not dry and start_time and ScheduleEntry.objects.filter(
                    client_name__iexact=member, date=day, start_time=start_time
                ).exists():
                    skipped += 1; continue

                driver = None
                if dname:
                    try:
                        driver = Driver.objects.get(name__iexact=dname)
                    except Driver.DoesNotExist:
                        driver = None

                if dry:
                    created += 1; continue

                ScheduleEntry.objects.create(
                    date=day,
                    client_name=member,
                    pickup_address=paddr,
                    dropoff_address=daddr,
                    start_time=start_time,
                    status='scheduled',
                    driver=driver,
                    contact_phone=phone
                )
                created += 1

            dstat = day_stats.setdefault(day.isoformat(), {'created':0,'skipped':0,'files':0,'skipped_missing_member':0})
            dstat['created'] += created; dstat['skipped'] += skipped; dstat['files'] += 1
            dstat['skipped_missing_member'] += skipped_missing_member

            self.stdout.write(self.style.SUCCESS(
                f"{f.name}: day={day} created={created} skipped={skipped} (missing_member={skipped_missing_member})"
            ))

        self.stdout.write(self.style.MIGRATE_HEADING("Summary:"))
        for day, s in sorted(day_stats.items()):
            self.stdout.write(f"  {day}: created={s['created']} skipped={s['skipped']} (missing_member={s['skipped_missing_member']}) files={s['files']}")


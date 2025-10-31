from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from django.db import transaction
import pandas as pd
import re, unicodedata

from scheduler.models import Company, Driver, Client

def normalize_columns(df):
    df = df.copy()
    def slugg(s: str) -> str:
        import re
        s = str(s or "").strip().lower()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s\-]+", "_", s)
        return s
    df.columns = [slugg(c) for c in df.columns]
    return df

def coerce_str(x):
    import pandas as pd
    if pd.isna(x):
        return ""
    return str(x).strip()

def coalesce(*vals):
    import pandas as pd
    for v in vals:
        if v is None: continue
        if isinstance(v, float) and pd.isna(v): continue
        s = str(v).strip()
        if s != "": return s
    return ""

def smart_slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip()).encode("ascii","ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:200] or "item"

def unique_slug_for_company(company: Company, base: str, model_cls) -> str:
    base = (base or "item").strip("-") or "item"
    slug = base
    i = 1
    while model_cls.objects.filter(company=company, slug=slug).exists():
        i += 1
        slug = (base[:180] + f"-{i}")[:200]
    return slug

class Command(BaseCommand):
    help = "Seed Drivers and Clients from Excel files into current database."

    def add_arguments(self, parser):
        parser.add_argument("--drivers", required=False, help="Path to drivers.xlsx")
        parser.add_argument("--clients", required=False, help="Path to clients.xlsx")
        parser.add_argument("--company-default", default=None, help="Default company name if sheets omit it")
        parser.add_argument("--truncate", action="store_true", help="Delete existing Drivers/Clients before seeding")

    def get_company(self, name: str | None, default_name: str | None):
        name = coalesce(name, default_name)
        if not name:
            return None
        company, _ = Company.objects.get_or_create(name=name)
        return company

    @transaction.atomic
    def handle(self, *args, **opts):
        drivers_path = opts.get("drivers")
        clients_path = opts.get("clients")
        default_company_name = opts.get("company_default")

        if not drivers_path and not clients_path:
            raise CommandError("Provide at least one of --drivers or --clients")

        if opts["truncate"]:
            self.stdout.write(self.style.WARNING("Truncating Drivers and Clients..."))
            Driver.objects.all().delete()
            Client.objects.all().delete()

        # -------- DRIVERS --------
        if drivers_path:
            self.stdout.write(f"Loading drivers from: {drivers_path}")
            drv = pd.read_excel(drivers_path)
            drv = normalize_columns(drv)

            d_first  = next((c for c in ["first_name","firstname","given_name","fname"] if c in drv.columns), None)
            d_last   = next((c for c in ["last_name","lastname","surname","lname","family_name"] if c in drv.columns), None)
            d_name   = next((c for c in ["name","driver_name","full_name"] if c in drv.columns), None)
            d_phone  = next((c for c in ["phone","phone_number","mobile","tel","contact"] if c in drv.columns), None)
            d_addr   = next((c for c in ["home_base_address","address","addr","home_address"] if c in drv.columns), None)
            d_company= next((c for c in ["company_name","company","employer","fleet"] if c in drv.columns), None)
            d_active = next((c for c in ["active","is_active","status"] if c in drv.columns), None)

            created = 0
            for _, row in drv.iterrows():
                company = self.get_company(coerce_str(row.get(d_company)) if d_company else None, default_company_name)
                if not company:
                    self.stdout.write(self.style.WARNING("Skipping driver row without company (no default provided)."))
                    continue

                first = coerce_str(row.get(d_first)) if d_first else ""
                last  = coerce_str(row.get(d_last)) if d_last else ""
                name  = coalesce(f"{first} {last}".strip(), coerce_str(row.get(d_name)) if d_name else "", "Driver")
                phone = coerce_str(row.get(d_phone)) if d_phone else ""
                addr  = coerce_str(row.get(d_addr)) if d_addr else ""

                base_slug = smart_slug(name)
                slug = unique_slug_for_company(company, base_slug, Driver)

                active_val = coerce_str(row.get(d_active)).lower() if d_active else ""
                active = True if active_val in ("", "true","1","yes","y","active","enabled") else False

                Driver.objects.create(
                    company=company,
                    slug=slug,
                    name=name,
                    phone=phone,
                    user=None,  # you can link to a User later
                    active=active,
                    home_base_address=addr,
                    home_latitude=None,
                    home_longitude=None,
                )
                created += 1
            self.stdout.write(self.style.SUCCESS(f"Drivers created: {created}"))

        # -------- CLIENTS --------
        if clients_path:
            self.stdout.write(f"Loading clients from: {clients_path}")
            cli = pd.read_excel(clients_path)  # define cli
            cli = normalize_columns(cli)

            c_first  = next((c for c in ["first_name","firstname","given_name","fname"] if c in cli.columns), None)
            c_last   = next((c for c in ["last_name","lastname","surname","lname","family_name"] if c in cli.columns), None)
            c_name   = next((c for c in ["name","client_name","full_name"] if c in cli.columns), None)
            c_pick   = next((c for c in ["pickup_address","pickup_adress","default_pickup_time","pickup"] if c in cli.columns), None)
            c_drop   = next((c for c in ["dropoff_address","dropoff_adress","default_dropoff_time","dropoff"] if c in cli.columns), None)
            c_notes  = next((c for c in ["notes","note","remarks","comments","comment"] if c in cli.columns), None)
            c_company= next((c for c in ["company_name","company","agency","provider"] if c in cli.columns), None)

            created = 0
            for _, row in cli.iterrows():
                company = self.get_company(coerce_str(row.get(c_company)) if c_company else None, default_company_name)
                if not company:
                    self.stdout.write(self.style.WARNING("Skipping client row without company (no default provided)."))
                    continue

                first = coerce_str(row.get(c_first)) if c_first else ""
                last  = coerce_str(row.get(c_last)) if c_last else ""
                name  = coalesce(f"{first} {last}".strip(), coerce_str(row.get(c_name)) if c_name else "", "Client")

                pickup_address  = coerce_str(row.get(c_pick)) if c_pick else ""
                dropoff_address = coerce_str(row.get(c_drop)) if c_drop else ""
                notes = coerce_str(row.get(c_notes)) if c_notes else ""

                base_slug = smart_slug(name)
                slug = unique_slug_for_company(company, base_slug, Client)

                Client.objects.create(
                    company=company,
                    slug=slug,
                    name=name,
                    pickup_address=pickup_address,
                    pickup_latitude=None,
                    pickup_longitude=None,
                    dropoff_address=dropoff_address,
                    dropoff_latitude=None,
                    dropoff_longitude=None,
                    notes=notes,
                )
                created += 1
            self.stdout.write(self.style.SUCCESS(f"Clients created: {created}"))

        self.stdout.write(self.style.SUCCESS("Seeding complete."))

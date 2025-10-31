from django.core.management.base import BaseCommand, CommandError
from datetime import date as _date
from scheduler.services.schedule_materializer import materialize_schedule_for_date

class Command(BaseCommand):
    help = "Generate a real Schedule + Entries from weekday templates for a given date"

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--date", required=True, help="YYYY-MM-DD")
        parser.add_argument("--force", action="store_true", help="Overwrite existing entries for that date")

    def handle(self, *args, **opts):
        company_id = opts["company_id"]
        try:
            y, m, d = map(int, opts["date"].split("-"))
            the_date = _date(y, m, d)
        except Exception:
            raise CommandError("Invalid --date; use YYYY-MM-DD")

        ok, msg = materialize_schedule_for_date(company_id, the_date, force=opts["force"])
        if ok:
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            self.stdout.write(self.style.WARNING(msg))

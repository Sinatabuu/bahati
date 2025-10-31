# generate_from_templates.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import datetime
from scheduler.models import Company, Schedule, ScheduleEntry, Client, Driver, ScheduleTemplateEntry  # adjust names

WEEKDAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("--company", required=True)
        p.add_argument("--date", required=True)  # YYYY-MM-DD
        p.add_argument("--replace", action="store_true")

    @transaction.atomic
    def handle(self, company, date, replace, **kw):
        co = Company.objects.get(name=company)
        day = datetime.fromisoformat(date).date()
        weekday = WEEKDAYS[day.weekday()]
        sched, _ = Schedule.objects.get_or_create(company=co, date=day)

        if replace:
            ScheduleEntry.objects.filter(schedule=sched).delete()

        # pull templates for the weekday (adjust model/field names to your code)
        rows = ScheduleTemplateEntry.objects.filter(company=co, weekday=weekday).select_related("client","driver")

        created = 0
        for t in rows:
            c = t.client
            pu_addr = t.override_pickup_address or c.pickup_address
            pu_city = t.override_pickup_city or c.pickup_city
            do_addr = t.override_dropoff_address or c.dropoff_address
            do_city = t.override_dropoff_city or c.dropoff_city

            e = ScheduleEntry.objects.create(
                schedule=sched,
                client=c,
                client_name=c.name,
                driver=t.driver,           # None allowed
                start_time=t.start_time,   # time field
                status=t.status or "planned",
                pickup_address=pu_addr, pickup_city=pu_city,
                dropoff_address=do_addr, dropoff_city=do_city,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Generated {created} entries for {day} from {weekday} templates."
        ))

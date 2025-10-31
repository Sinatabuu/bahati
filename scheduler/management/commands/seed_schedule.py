from django.core.management.base import BaseCommand
from django.apps import apps
import datetime as dt

class Command(BaseCommand):
    help = "Seed a few ScheduleEntry rows for demo"

    def handle(self, *args, **kwargs):
        ScheduleEntry = apps.get_model('scheduler', 'ScheduleEntry')
        Driver = apps.get_model('scheduler', 'Driver')

        driver = Driver.objects.first()
        if not driver:
            self.stdout.write(self.style.ERROR("No Driver found"))
            return

        today = dt.date.today()
        rows = [
            dict(driver=driver, client_name="John Doe", address="123 Main St",
                 date=today, start_time=dt.time(9,0), end_time=dt.time(10,0),
                 start_latitude=42.3601, start_longitude=-71.0589,
                 end_latitude=42.3736, end_longitude=-71.1097),
            dict(driver=driver, client_name="Jane Roe", address="456 Elm St",
                 date=today, start_time=dt.time(11,0), end_time=dt.time(12,0),
                 start_latitude=42.3477, start_longitude=-71.0826,
                 end_latitude=42.3398, end_longitude=-71.0892),
        ]
        for r in rows:
            ScheduleEntry.objects.create(**r)

        self.stdout.write(self.style.SUCCESS("Seeded schedule entries"))

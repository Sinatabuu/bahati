# scheduler/management/commands/normalize_templates.py
from django.core.management.base import BaseCommand
from django.db.models import Q
from scheduler.models import ScheduleTemplateEntry, Driver, Client, Vehicle

JUNK = {"-", "—", "–", "-----", "--------", "---------"}

def clean_text(x):
    x = (x or "").strip()
    return "" if x in JUNK else x

class Command(BaseCommand):
    help = "Normalize ScheduleTemplateEntry rows: strip junk, resolve names to FKs, align *_name with FK."

    def handle(self, *args, **opts):
        updated = 0
        for e in ScheduleTemplateEntry.objects.select_related("template__company"):
            company = e.template.company

            before = (e.client_id, e.driver_id, e.vehicle_id, e.client_name, e.driver_name, e.vehicle_name, e.pickup_address, e.dropoff_address)

            e.client_name  = clean_text(e.client_name)
            e.driver_name  = clean_text(e.driver_name)
            e.vehicle_name = clean_text(e.vehicle_name)
            e.pickup_address  = clean_text(e.pickup_address)
            e.dropoff_address = clean_text(e.dropoff_address)

            if not e.client and e.client_name:
                e.client = Client.objects.filter(company=company).filter(Q(name__iexact=e.client_name) | Q(name__icontains=e.client_name)).first()
                if e.client: e.client_name = e.client.name
            if not e.driver and e.driver_name:
                e.driver = Driver.objects.filter(company=company).filter(Q(name__iexact=e.driver_name) | Q(name__icontains=e.driver_name)).first()
                if e.driver: e.driver_name = e.driver.name
            if not e.vehicle and e.vehicle_name:
                e.vehicle = Vehicle.objects.filter(company=company).filter(Q(name__iexact=e.vehicle_name) | Q(name__icontains=e.vehicle_name)).first()
                if e.vehicle: e.vehicle_name = e.vehicle.name

            # Align names with FK if present
            if e.client:  e.client_name  = e.client.name
            if e.driver:  e.driver_name  = e.driver.name
            if e.vehicle: e.vehicle_name = e.vehicle.name

            after = (e.client_id, e.driver_id, e.vehicle_id, e.client_name, e.driver_name, e.vehicle_name, e.pickup_address, e.dropoff_address)
            if before != after:
                e.save()
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Normalized {updated} template row(s)."))

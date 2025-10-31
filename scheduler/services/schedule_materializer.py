# scheduler/services/schedule_materializer.py
from datetime import datetime
from django.db import transaction
from django.utils import timezone

from scheduler.models import (
    Company, Client, Driver, Vehicle,
    Schedule, ScheduleEntry,
    ScheduleTemplate, ScheduleTemplateEntry,
)

WEEKEND = {5, 6}  # 5=Sat, 6=Sun

def _resolve(v, obj_attr, fallback_name):
    """
    helper: obj if provided else fallback_name (string) or None
    """
    if v:
        return v
    return fallback_name or None

@transaction.atomic
def materialize_schedule_for_date(company_id, the_date, force=False, template: ScheduleTemplate | None = None):
    """
    Create (or reuse) a Schedule for (company, the_date) from a weekday template.
    - Skips weekends with a friendly message.
    - Idempotent: if a schedule exists and force=False, do nothing.
    - If 'template' passed, use only that template; otherwise pick all active templates for that weekday.
    Returns (ok: bool, msg: str)
    """
    weekday = the_date.weekday()
    if weekday in WEEKEND:
        return False, f"{the_date} is weekend ({the_date.strftime('%A')}). No schedules generated."

    # Get templates
    if template is not None:
        templates = [template] if template.active else []
    else:
        templates = list(ScheduleTemplate.objects.filter(company_id=company_id, weekday=weekday, active=True))
    if not templates:
        return False, f"No active templates for {the_date.strftime('%A')}."

    # get or create the Schedule
    sched, created = Schedule.objects.get_or_create(company_id=company_id, date=the_date)

    if not created and not force:
        return True, f"Schedule already exists for {the_date}; not regenerating (use force=True to overwrite)."

    if not created and force:
        # cautious: remove only entries we own (same date/company)
        ScheduleEntry.objects.filter(company_id=company_id, schedule=sched).delete()

    # Build entries from all templates for this weekday
    total = 0
    now = timezone.now()

    for tmpl in templates:
        for e in tmpl.entries.all():
            # resolve FKs or names
            client = e.client
            driver = e.driver
            vehicle = e.vehicle

            client_name = _resolve(client, "name", e.client_name)
            driver_name = _resolve(driver, "name", e.driver_name)
            vehicle_name = _resolve(vehicle, "name", e.vehicle_name)

            # addresses: prefer explicit, else from client defaults
            pickup_address = e.pickup_address or (client and client.pickup_address) or ""
            dropoff_address = e.dropoff_address or (client and client.dropoff_address) or ""

            # Build a datetime for start_time on that date if your ScheduleEntry uses DateTime; else store TimeField
            start_time = e.start_time  # your model shows start_time in admin; assuming TimeField is fine

            ScheduleEntry.objects.create(
                company_id=company_id,
                schedule=sched,
                # core fields (adapt to your actual model names!)
                start_time=start_time,
                client=client,
                client_name=client_name or "",
                driver=driver,
                vehicle=vehicle,
                pickup_address=pickup_address,
                dropoff_address=dropoff_address,
                status=getattr(ScheduleEntry, "Status", None) and getattr(ScheduleEntry.Status, "PLANNED", None) or "planned",
                created_at=now if hasattr(ScheduleEntry, "created_at") else None,
                updated_at=now if hasattr(ScheduleEntry, "updated_at") else None,
            )
            total += 1

    return True, f"Materialized {total} entries into schedule {sched.id} for {the_date}."

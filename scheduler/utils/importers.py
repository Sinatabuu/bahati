# scheduler/utils/materialize.py
from django.db import transaction
from django.db.models import Q
from scheduler.models import (
    Company, Schedule, ScheduleEntry, ScheduleTemplate, ScheduleTemplateEntry
)

TEMPLATE_TAG_PREFIX = "[TEMPLATE:"

def _resolve_client(e):
    return e.client

def _resolve_driver(e):
    if e.driver_id:
        return e.driver
    name = (e.driver_name or "").strip()
    if not name:
        return None
    from scheduler.models import Driver
    return Driver.objects.filter(Q(name__iexact=name) | Q(name__icontains=name), company=e.template.company).first()

def _resolve_vehicle(e):
    if e.vehicle_id:
        return e.vehicle
    name = (e.vehicle_name or "").strip()
    if not name:
        return None
    from scheduler.models import Vehicle
    return Vehicle.objects.filter(Q(name__iexact=name) | Q(name__icontains=name), company=e.template.company).first()

@transaction.atomic
def apply_template_for_date(target_date, *, company, mode: str = "sync"):
    """
    Materialize active templates for (company, weekday) into a Schedule + ScheduleEntry.
    mode: "replace" | "append" | "sync"
    """
    weekday = target_date.weekday()
    templates = (ScheduleTemplate.objects
                 .filter(company=company, active=True, weekday=weekday)
                 .prefetch_related("entries"))
    if not templates.exists():
        return {"created": False, "message": "No active templates", "schedule_id": None, "entry_count": 0}

    schedule, created = Schedule.objects.get_or_create(
        company=company, date=target_date, defaults={"meta": {"source": "template", "weekday": weekday}}
    )

    qs_all = ScheduleEntry.objects.filter(company=company, schedule=schedule)
    if mode == "replace":
        qs_all.delete()
    elif mode == "sync":
        qs_all.filter(notes__icontains=TEMPLATE_TAG_PREFIX).delete()

    new_entries = []
    for tmpl in templates:
        tag = f"{TEMPLATE_TAG_PREFIX}{tmpl.id}]"
        for e in tmpl.entries.all().order_by("order", "id"):
            client = _resolve_client(e)
            driver = _resolve_driver(e)
            vehicle = _resolve_vehicle(e)

            client_name = (client.name if client else (e.client_name or "")).strip()

            pickup_address  = (e.pickup_address or (client.pickup_address if client else "")).strip()
            dropoff_address = (e.dropoff_address or (client.dropoff_address if client else "")).strip()

            # Cities: from entry (if you added fields to the template) else from client
            if hasattr(e, "pickup_city"):
                pickup_city = (e.pickup_city or (client and client.pickup_city) or "").strip()
                dropoff_city = (e.dropoff_city or (client and client.dropoff_city) or "").strip()
            else:
                pickup_city  = (client and client.pickup_city) or ""
                dropoff_city = (client and client.dropoff_city) or ""

            base_notes = (e.notes or "").strip()
            notes = f"{base_notes}\n{tag}" if base_notes else tag

            entry = ScheduleEntry(
                schedule=schedule,
                company=company,
                driver=driver,
                vehicle=vehicle,
                client=client,
                client_name=client_name,
                start_time=e.start_time,
                pickup_address=pickup_address,
                dropoff_address=dropoff_address,
                pickup_city=pickup_city,
                dropoff_city=dropoff_city,
                status="scheduled",
                notes=notes,
            )
            new_entries.append(entry)

    ScheduleEntry.objects.bulk_create(new_entries, ignore_conflicts=False)
    return {
        "created": created,
        "message": f"{mode.title()} materialized {len(new_entries)} entries into schedule {schedule.id}.",
        "schedule_id": schedule.id,
        "entry_count": len(new_entries),
    }

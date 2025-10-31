import json
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.utils.timezone import localdate
from django.views.decorators.csrf import csrf_exempt   # keep only for DEV on POST views that aren’t form-based
from django.views.decorators.http import require_GET, require_http_methods

from .models import (
    ScheduleEntry, Driver, Client,
    
)

User = get_user_model()

# ---------- helpers ----------

def _parse_date(ds: str):
    try:
        return datetime.strptime(ds, "%Y-%m-%d").date()
    except Exception:
        return None

def _parse_date_param(request, default_today=True):
    ds = request.GET.get("date") or request.POST.get("date")
    if ds:
        try:
            return datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            return None
    return localdate() if default_today else None

def _entry_trip(e: ScheduleEntry):
    return {
        "id": e.id,
        "client": e.client_name,
        "start_time": e.start_time.isoformat() if e.start_time else None,
        "end_time": e.end_time.isoformat() if e.end_time else None,
        "pickup": {"address": e.pickup_address, "city": e.pickup_city},
        "dropoff": {"address": e.dropoff_address, "city": e.dropoff_city},
        "status": e.status,
    }

def _trip_dict(e: ScheduleEntry):
    return {
        "id": e.id,
        "client": e.client_name,
        "start_time": e.start_time.isoformat() if e.start_time else None,
        "end_time": e.end_time.isoformat() if e.end_time else None,
        "pickup": {"address": e.pickup_address, "city": e.pickup_city},
        "dropoff": {"address": e.dropoff_address, "city": e.dropoff_city},
        "status": e.status,
        "driver": getattr(e.driver, "name", None),
        "date": e.date.isoformat(),
    }

# ---------- tiny utilities for SPA ----------

@require_http_methods(["GET", "HEAD"])
def health(request):
    return JsonResponse({"ok": True, "app": "scheduler", "user": None})

@require_GET
def session_json(request):
    u = request.user
    return JsonResponse({
        "authenticated": u.is_authenticated,
        "username": u.username if u.is_authenticated else None,
        "is_staff": bool(getattr(u, "is_staff", False)),
        "is_superuser": bool(getattr(u, "is_superuser", False)),
    })

@require_http_methods(["GET", "HEAD"])
def me(request):
    u = request.user
    if not u.is_authenticated:
        return JsonResponse({"user": None})
    payload = {
        "id": u.id,
        "username": u.username,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "email": u.email,
        "is_staff": bool(getattr(u, "is_staff", False)),
        "is_superuser": bool(getattr(u, "is_superuser", False)),
    }
    driver_obj = getattr(u, "driver", None)
    payload["driver"] = {"id": driver_obj.id, "name": driver_obj.name} if driver_obj else None
    return JsonResponse({"user": payload})

# ---------- dashboard feeds ----------

@require_GET
def my_schedule_json(request):
    """Driver’s own schedule for a given date – used by the Vite dashboard."""
    d = _parse_date_param(request)
    if d is None:
        return HttpResponseBadRequest("Bad or missing date (YYYY-MM-DD)")
    drv = getattr(request.user, "driver", None)
    trips = []
    if drv:
        qs = ScheduleEntry.objects.filter(date=d, driver=drv).order_by("start_time", "id")
        trips = [_entry_trip(e) for e in qs]
    return JsonResponse({
        "date": d.isoformat(),
        "driver": request.user.username,
        "defaults": {"lat": 42.60055, "lng": -71.34866},
        "trips": trips,
        "features": [],
    })

@require_GET
def schedule_entries_json(request):
    """All entries for a date (admin view)."""
    d = _parse_date_param(request)
    if d is None:
        return HttpResponseBadRequest("Bad or missing date (YYYY-MM-DD)")
    # Optionally enforce admin:
    # if not request.user.is_staff: return HttpResponseBadRequest("Staff only")
    qs = ScheduleEntry.objects.filter(date=d).select_related("driver").order_by("driver_id","start_time","id")
    entries = []
    for e in qs:
        obj = _trip_dict(e)
        entries.append(obj)
    return JsonResponse({"date": d.isoformat(), "count": len(entries), "entries": entries})

@require_GET
@login_required
def driver_live(request):
    ds = request.GET.get("date")
    day = _parse_date(ds) or datetime.utcnow().date()

    # Resolve driver
    drv = getattr(request.user, "driver", None)
    if not drv:
        did = request.GET.get("driver_id")
        if did:
            drv = Driver.objects.filter(pk=did).first()
        elif request.GET.get("driver"):
            drv = Driver.objects.filter(name__iexact=request.GET["driver"]).first()
    if not drv:
        drv = Driver.objects.filter(name__iexact=request.user.username).first()

    qs = ScheduleEntry.objects.filter(date=day)
    if drv:
        qs = qs.filter(driver=drv)

    trips = []
    for e in qs.order_by("start_time","client_name"):
        trips.append({
            "id": e.id,
            "status": e.status,
            "client_name": e.client_name,
            "start_time": e.start_time.isoformat() if e.start_time else None,
            "end_time": e.end_time.isoformat() if e.end_time else None,
            "pickup_address": e.pickup_address or e.address or "",
            "pickup_city": e.pickup_city or "",
            "dropoff_address": e.dropoff_address or "",
            "dropoff_city": e.dropoff_city or "",
        })

    lat = getattr(drv, "last_lat", None) or 42.60055
    lng = getattr(drv, "last_lng", None) or -71.34866

    return JsonResponse({
        "date": day.isoformat(),
        "driver": getattr(drv, "name", request.user.username),
        "defaults": {"lat": lat, "lng": lng},
        "trips": trips,
        "features": [],
    })

# ---------- admin tools ----------

@require_GET
def drivers_list(request):
    data = list(Driver.objects.values("id", "name"))
    return JsonResponse({"count": len(data), "drivers": data})

@require_GET
def all_schedules_json(request):
    ds = request.GET.get("date")
    d = _parse_date(ds) if ds else None
    if not d:
        return HttpResponseBadRequest("Missing or invalid ?date=YYYY-MM-DD")

    qs = (ScheduleEntry.objects
          .filter(date=d)
          .select_related("driver")
          .order_by("driver__name", "start_time", "id"))

    grouped = {}
    for e in qs:
        key = getattr(e.driver, "name", "Unassigned")
        grouped.setdefault(key, []).append(_trip_dict(e))

    return JsonResponse({
        "date": d.isoformat(),
        "count": qs.count(),
        "drivers": [
            {"driver": k, "trips": v, "count": len(v)}
            for k, v in grouped.items()
        ],
    })

# ---------- actions ----------

@login_required
def cancel_entry(request, pk):
    try:
        e = ScheduleEntry.objects.get(pk=pk)
    except ScheduleEntry.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    reason = request.POST.get("reason")
    if not reason:
        try:
            body = json.loads(request.body or "{}")
            reason = body.get("reason","")
        except Exception:
            reason = (request.body or b"").decode("utf-8", "ignore")
    reason = (reason or "").strip()

    e.status = "cancelled"
    e.cancelled_at = timezone.now()
    e.cancelled_by = request.user
    e.cancellation_reason = reason[:255]
    e.save()
    return JsonResponse({"ok": True, "id": e.id, "status": e.status})

@login_required
def reassign_entry(request, pk):
    try:
        e = ScheduleEntry.objects.get(pk=pk)
    except ScheduleEntry.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    payload = request.POST.get("driver_id") or request.POST.get("driver") or None
    if not payload:
        try:
            body = json.loads(request.body or "{}")
            payload = body.get("driver_id") or body.get("driver")
        except Exception:
            payload = (request.body or b"").decode("utf-8", "ignore")
    payload = (payload or "").strip()

    new_driver = None
    if payload.isdigit():
        new_driver = Driver.objects.filter(pk=int(payload)).first()
    if not new_driver:
        new_driver = Driver.objects.filter(name__iexact=payload).first()

    if not new_driver:
        return HttpResponseBadRequest("Driver not found")

    e.driver = new_driver
    e.save()
    return JsonResponse({"ok": True, "id": e.id, "driver": {"id": new_driver.id, "name": new_driver.name}})

# ---------- generator ----------
from django.views.decorators.http import require_POST
@csrf_exempt
@require_POST
def generate_schedule_for_date(request):
    try:
        body = json.loads(request.body or "{}")
    except Exception:
        body = request.POST
    ds = body.get("date")
    if not ds:
        return HttpResponseBadRequest("date required")
    day = _parse_date(ds)
    if not day:
        return HttpResponseBadRequest("bad date")

    mode = (body.get("mode") or "all").lower()
    learn_weeks = int(body.get("learn_weeks") or 8)
    weekday = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][day.weekday()]

    created = reused = 0

    def upsert(client_name, start_time, pickup_addr="", pickup_city="", dropoff_addr="", dropoff_city="", driver=None):
        nonlocal created, reused
        if not client_name or not start_time:
            return
        obj, was_created = ScheduleEntry.objects.get_or_create(
            date=day, client_name=client_name.strip(), start_time=start_time,
            defaults={
                "pickup_address": pickup_addr or "",
                "pickup_city": pickup_city or "",
                "dropoff_address": dropoff_addr or "",
                "dropoff_city": dropoff_city or "",
                "status": "scheduled",
                "driver": driver,
            },
        )
        if was_created: created += 1
        else: reused += 1

    if mode in ("all","templates"):
        for t in DailyScheduleTemplate.objects.filter(day_of_week=weekday):
            cli = t.client
            upsert(cli.name, t.pickup_time, cli.pickup_address, cli.pickup_city,
                   cli.dropoff_address, cli.dropoff_city, t.driver)

    if mode in ("all","standing"):
        for s in StandingOrder.objects.filter(active=True, weekday=weekday):
            upsert(s.client_name, s.default_start_time, s.pickup_address, s.pickup_city,
                   s.dropoff_address, s.dropoff_city, s.preferred_driver)

    if mode in ("all","learn"):
        since = day - timedelta(days=7*learn_weeks)
        agg = (ScheduleEntry.objects
               .filter(date__gte=since, date__lt=day)
               .values("client_name","start_time","driver")
               .annotate(n=Count("id"))
               .order_by("-n"))
        seen = set()
        for row in agg:
            key = (row["client_name"], row["start_time"])
            if key in seen: continue
            seen.add(key)
            latest = (ScheduleEntry.objects
                      .filter(client_name=row["client_name"], start_time=row["start_time"])
                      .order_by("-date","-id")
                      .first())
            upsert(
                row["client_name"], row["start_time"],
                getattr(latest, "pickup_address", "") or "",
                getattr(latest, "pickup_city", "") or "",
                getattr(latest, "dropoff_address", "") or "",
                getattr(latest, "dropoff_city", "") or "",
                Driver.objects.filter(pk=row["driver"]).first() if row["driver"] else None,
            )

    return JsonResponse({"ok": True, "date": day.isoformat(), "created": created, "reused": reused})

# scheduler/api/views.py
from datetime import date
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes

from django.utils.dateparse import parse_date

from scheduler.models import ScheduleEntry, Company
from .serializers import ScheduleEntrySerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def schedule_for_day(request):
    """
    Query params:
      - date=YYYY-MM-DD (required)
      - company=<company name> (required)
    """
    d = parse_date(request.GET.get("date") or "")
    company_name = (request.GET.get("company") or "").strip()
    if not d or not company_name:
        return Response({"ok": False, "error": "date and company are required"}, status=400)

    try:
        company = Company.objects.get(name=company_name)
    except Company.DoesNotExist:
        return Response({"ok": False, "error": "company not found"}, status=404)

    qs = (ScheduleEntry.objects
          .select_related("schedule", "client", "driver")
          .filter(company=company, schedule__date=d)
          .order_by("start_time", "id"))

    ser = ScheduleEntrySerializer(qs, many=True)
    return Response({"ok": True, "date": d.isoformat(), "company": company.name, "entries": ser.data})



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def day_schedule(request):
    company = request.user.company  # or however you scope company
    day = request.GET.get("date") or timezone.localdate()
    qs = (ScheduleEntry.objects
          .select_related("client","driver","schedule")
          .filter(company=company, schedule__date=day)
          .order_by("start_time","id"))
    return Response(ScheduleEntrySerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def driver_today(request, driver_id):
    day = request.GET.get("date") or timezone.localdate()
    qs = (ScheduleEntry.objects
            .select_related("client","driver","schedule","company")
            .filter(schedule__date=day, driver_id=driver_id)
            .order_by("start_time","id"))
    return Response(ScheduleEntrySerializer(qs, many=True).data)


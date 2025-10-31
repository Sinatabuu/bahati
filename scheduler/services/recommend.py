from collections import Counter
from datetime import date as date_cls
from django.db.models import Q
from scheduler.models import ScheduleEntry, Driver
def recommend_driver_for(client_id, when: date_cls, pickup_address=None, limit=3):
    qs = ScheduleEntry.objects.filter(client_id=client_id, status="completed").order_by("-start_time")[:200]
    freq = Counter(e.driver_id for e in qs if e.driver_id)
    candidates = [ (driver_id, count) for driver_id, count in freq.most_common() ]

    # Fallback to all drivers if none seen before
    if not candidates:
      candidates = [(d.id, 0) for d in Driver.objects.filter(active=True).values_list("id", flat=False)]

    # Simple availability: driver not already at same time
    day_assigned = set(ScheduleEntry.objects.filter(date=when).values_list("driver_id", flat=True))
    ranked = []
    for driver_id, score in candidates:
        penalty = 1 if driver_id in day_assigned else 0
        ranked.append((driver_id, score - penalty))
    ranked.sort(key=lambda t: (-t[1], t[0]))
    return [driver_id for driver_id, _ in ranked[:limit]]

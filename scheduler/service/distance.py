# scheduler/services/distance.py
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from django.db import transaction, models
from django.utils import timezone

# ---- Model you should have (or create) ---------------------------------------
class DistanceCache(models.Model):
    origin = models.CharField(max_length=128, db_index=True)
    dest = models.CharField(max_length=128, db_index=True)
    bucket = models.CharField(max_length=32, db_index=True)  # e.g. "08:00"
    duration_sec = models.IntegerField()
    distance_m = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("origin", "dest", "bucket"),)

# ---- Helpers -----------------------------------------------------------------
def _coord_key(lat: float, lng: float) -> str:
    # 6-decimal rounding keeps cache keys tidy
    return f"{round(lat, 6)},{round(lng, 6)}"

def _bucket_for(dt_local: datetime) -> str:
    # 15-min traffic bucket. Adjust as you like.
    return dt_local.strftime("%H") + f":{(dt_local.minute // 15) * 15:02d}"

@dataclass
class Leg:
    duration_sec: int
    distance_m: int

# ---- Public API ---------------------------------------------------------------
def get_leg_duration(
    origin_lat: float, origin_lng: float,
    dest_lat: float, dest_lng: float,
    when_local: datetime | None = None,
) -> Leg:
    """
    Returns a Leg(duration_sec, distance_m).
    Strategy today: DB cache; if miss -> constant-speed estimate (no external API).
    Later you can drop in OSRM/Google here and keep the same signature.
    """
    if when_local is None:
        when_local = timezone.localtime()
    origin = _coord_key(origin_lat, origin_lng)
    dest = _coord_key(dest_lat, dest_lng)
    bucket = _bucket_for(when_local)

    try:
        dc = DistanceCache.objects.get(origin=origin, dest=dest, bucket=bucket)
        return Leg(duration_sec=dc.duration_sec, distance_m=dc.distance_m)
    except DistanceCache.DoesNotExist:
        pass

    # Fallback: straight-line “as-the-crow-flies” -> drive minutes via 30km/h avg.
    # (Very conservative; OSRM later will overwrite cache naturally.)
    import math
    R = 6371000.0
    def rad(x): return x * math.pi / 180.0
    dlat = rad(dest_lat - origin_lat)
    dlon = rad(dest_lng - origin_lng)
    a = math.sin(dlat/2)**2 + math.cos(rad(origin_lat))*math.cos(rad(dest_lat))*math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    meters = int(R * c)
    # Assume avg 30km/h -> 0.5 km/min = 120 sec/ km
    duration_sec = max(60, int((meters / 1000.0) * 120))

    with transaction.atomic():
        DistanceCache.objects.update_or_create(
            origin=origin, dest=dest, bucket=bucket,
            defaults={"duration_sec": duration_sec, "distance_m": meters},
        )
    return Leg(duration_sec=duration_sec, distance_m=meters)

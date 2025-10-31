# scheduler/services/scheduling.py
from django.db.models import Max
import re

TIME_TOKEN = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")
DRIVER_TOKENS = re.compile(r"\b(ERNEST|STEVE|WILLIAM|KENNEDY|JOCK|TONY|SAMMY|JOSHUA|CHARLES|DAVID|WAIYAKI|MUNIU|GUDOYI)\b", re.I)
MULTI_WS = re.compile(r"\s+")

def _norm(s: str|None) -> str|None:
    if not s:
        return None
    s = s.strip()
    if s in {"", "-", "—"}:
        return None
    return MULTI_WS.sub(" ", s)

def _strip_noise(s: str|None) -> str|None:
    if not s:
        return None
    s = DRIVER_TOKENS.sub(" ", s)
    s = TIME_TOKEN.sub(" ", s)
    return _norm(s)

def _best(*candidates):
    """Return the first non-empty candidate after normalizing/stripping noise."""
    for c in candidates:
        v = _strip_noise(c)
        if v:
            return v
    return None

def build_latest_entry_map(ScheduleEntry):
    """Return {client_id: latest_scheduleentry} for quick lookups."""
    latest_ids = (ScheduleEntry.objects.values("client_id")
                  .annotate(latest=Max("id")))
    latest_map = {}
    for row in latest_ids:
        se = ScheduleEntry.objects.select_related("client").filter(id=row["latest"]).first()
        if se:
            latest_map[se.client_id] = se
    return latest_map

def resolve_addresses(tmpl, client, latest_map=None):
    """
    Returns tuple: (pickup_addr, dropoff_addr, pickup_city, dropoff_city)
    Works even if your model doesn't have city fields (callers can ignore).
    """
    # Try last known entry for this client
    last = latest_map.get(client.id) if (latest_map and client and client.id) else None

    pickup_addr = _best(
        getattr(tmpl, "pickup_address", None),
        getattr(client, "default_pickup_address", None),
        getattr(last, "pickup_address", None),
    )

    dropoff_addr = _best(
        getattr(tmpl, "dropoff_address", None),
        getattr(client, "default_dropoff_address", None),
        getattr(last, "dropoff_address", None),
    )

    # Optional cities if your models have these fields
    pickup_city = _best(
        getattr(tmpl, "pickup_city", None),
        getattr(client, "pickup_city", None),
        getattr(last, "pickup_city", None),
    ) if hasattr(tmpl, "pickup_city") else None

    dropoff_city = _best(
        getattr(tmpl, "dropoff_city", None),
        getattr(client, "dropoff_city", None),
        getattr(last, "dropoff_city", None),
    ) if hasattr(tmpl, "dropoff_city") else None

    return pickup_addr, dropoff_addr, pickup_city, dropoff_city

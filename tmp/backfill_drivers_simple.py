# /tmp/backfill_drivers_simple.py
from django.apps import apps
from django.db.models import Q

DRY_RUN = False
VERBOSE = True

def get_model(app_label, name):
    try:
        return apps.get_model(app_label, name)
    except Exception:
        return None

Driver   = get_model("scheduler", "Driver")
Client   = get_model("scheduler", "Client")
SEntry   = get_model("scheduler", "ScheduleEntry")
STEntry  = get_model("scheduler", "ScheduleTemplateEntry")
Standing = get_model("scheduler", "StandingOrder")

if not Driver:
    raise SystemExit("Driver model missing")
if not (STEntry or Standing):
    raise SystemExit("No ScheduleTemplateEntry / StandingOrder models found")
if not SEntry:
    print("WARNING: ScheduleEntry not found; last-known mapping will be unavailable.")

# ---------- Utilities ----------
def _norm(s):
    return (s or "").strip()

def _tokens(s):
    import re
    return [t.lower() for t in re.findall(r"[A-Za-z]+", s or "") if t]

def unique_driver_by_tokens(tokens):
    """
    Try to find a unique Driver by tokens (first+last, or a single unique token).
    Only returns a Driver if the match is unique.
    """
    if not tokens:
        return None
    # Try exact 'first last' contains
    if len(tokens) >= 2:
        q = Driver.objects.all()
        q = q.filter(name__icontains=tokens[0]).filter(name__icontains=tokens[1])
        if q.count() == 1:
            return q.first()

    # Else try single-token unique
    for t in tokens:
        q = Driver.objects.filter(name__icontains=t)
        if q.count() == 1:
            return q.first()
    return None

def set_driver(obj, driver):
    if getattr(obj, "driver_id", None):
        return False
    if DRY_RUN:
        return True
    setattr(obj, "driver", driver)
    obj.save(update_fields=["driver"])
    return True

# ---------- Build last-known driver maps from ScheduleEntry ----------
client_fk_to_driver = {}
client_name_to_driver = {}

if SEntry:
    # Prefer FK mapping (client id) — more reliable than names
    rows = (SEntry.objects
            .filter(driver__isnull=False)
            .select_related("client", "driver")
            .order_by("client_id", "-id"))
    seen = set()
    for e in rows:
        cid = getattr(e, "client_id", None)
        if cid and cid not in seen:
            client_fk_to_driver[cid] = e.driver
            seen.add(cid)

    # Fallback: client_name mapping (if your model has client_name)
    if hasattr(SEntry, "client_name"):
        rows2 = (SEntry.objects
                 .filter(driver__isnull=False)
                 .exclude(Q(client_name__isnull=True) | Q(client_name=""))
                 .order_by("client_name", "-id"))
        seen2 = set()
        for e in rows2:
            nm = _norm(getattr(e, "client_name", None))
            if nm and nm not in seen2:
                client_name_to_driver[nm] = e.driver
                seen2.add(nm)

if VERBOSE:
    print(f"[MAP] client_fk_to_driver: {len(client_fk_to_driver)} entries")
    print(f"[MAP] client_name_to_driver: {len(client_name_to_driver)} entries")

# ---------- Backfill ScheduleTemplateEntry ----------
templ_checked = templ_set = templ_name_detect = 0
if STEntry:
    qs = STEntry.objects.select_related("client", "driver")
    for te in qs:
        templ_checked += 1
        if getattr(te, "driver_id", None):
            continue

        # Try client FK map
        cobj = getattr(te, "client", None) if hasattr(te, "client") else None
        if cobj and cobj.id in client_fk_to_driver:
            drv = client_fk_to_driver[cobj.id]
            if set_driver(te, drv):
                templ_set += 1
                if VERBOSE:
                    print(f"[TEMPLATE] id={te.id} client(FK) -> {drv.name}")
                continue

        # Try client_name map
        cname = _norm(getattr(te, "client_name", None)) if hasattr(te, "client_name") else _norm(getattr(cobj, "name", None))
        if cname and cname in client_name_to_driver:
            drv = client_name_to_driver[cname]
            if set_driver(te, drv):
                templ_set += 1
                if VERBOSE:
                    print(f"[TEMPLATE] id={te.id} client(name) -> {drv.name}")
                continue

        # Optional: try text tokens (route/notes/etc.)
        # Look through likely text fields for a driver name
        text_fields = [n for n in ("driver_name","route","route_name","notes","description","pickup_address","dropoff_address") if hasattr(te, n)]
        joined = " | ".join(str(getattr(te, n) or "") for n in text_fields)
        drv = unique_driver_by_tokens(_tokens(joined))
        if drv and set_driver(te, drv):
            templ_set += 1
            templ_name_detect += 1
            if VERBOSE:
                print(f"[TEMPLATE] id={te.id} tokens -> {drv.name}")

# ---------- Backfill StandingOrder ----------
stand_checked = stand_set = stand_name_detect = 0
if Standing:
    qs = Standing.objects.select_related("client", "driver")
    for so in qs:
        stand_checked += 1
        if getattr(so, "driver_id", None):
            continue

        # Client FK map
        cobj = getattr(so, "client", None) if hasattr(so, "client") else None
        if cobj and cobj.id in client_fk_to_driver:
            drv = client_fk_to_driver[cobj.id]
            if set_driver(so, drv):
                stand_set += 1
                if VERBOSE:
                    print(f"[STANDING] id={so.id} client(FK) -> {drv.name}")
                continue

        # Client name map
        cname = _norm(getattr(so, "client_name", None)) if hasattr(so, "client_name") else _norm(getattr(cobj, "name", None))
        if cname and cname in client_name_to_driver:
            drv = client_name_to_driver[cname]
            if set_driver(so, drv):
                stand_set += 1
                if VERBOSE:
                    print(f"[STANDING] id={so.id} client(name) -> {drv.name}")
                continue

        # Optional: tokens
        text_fields = [n for n in ("driver_name","route","route_name","notes","description","pickup_address","dropoff_address") if hasattr(so, n)]
        joined = " | ".join(str(getattr(so, n) or "") for n in text_fields)
        drv = unique_driver_by_tokens(_tokens(joined))
        if drv and set_driver(so, drv):
            stand_set += 1
            stand_name_detect += 1
            if VERBOSE:
                print(f"[STANDING] id={so.id} tokens -> {drv.name}")

print("\n=== Driver Backfill Summary ===")
print(f"TEMPLATE checked: {templ_checked} | set: {templ_set} | via tokens: {templ_name_detect}")
print(f"STANDING  checked: {stand_checked} | set: {stand_set} | via tokens: {stand_name_detect}")
print(f"DRY_RUN={DRY_RUN}")

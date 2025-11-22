# --- at top of admin.py (ensure these are imported) ---
from datetime import time
from django.utils import timezone
from django.db import transaction
from django.contrib import admin, messages

from .models import (
    Company, Client, Driver, Vehicle,
    Schedule, ScheduleEntry,
    ScheduleTemplate, ScheduleTemplateEntry,
)

def has_field(model, name: str) -> bool:
    try:
        return any(f.name == name for f in model._meta.get_fields())
    except Exception:
        return False

DEFAULT_START_TIME = time(8, 0)

def _client_defaults(client):
    out = {}
    if hasattr(client, "default_pickup_address"):
        out["pickup_address"] = client.default_pickup_address
    if hasattr(client, "default_dropoff_address"):
        out["dropoff_address"] = client.default_dropoff_address
    for f in ("pickup_city", "pickup_state", "dropoff_city", "dropoff_state"):
        if hasattr(client, f):
            out[f] = getattr(client, f, None)
    return out

def _ensure_weekday_template(company, weekday):
    qs = ScheduleTemplate.objects.all()
    if has_field(ScheduleTemplate, "company"):
        qs = qs.filter(company=company)
    if has_field(ScheduleTemplate, "weekday"):
        qs = qs.filter(weekday=weekday)
    tpl = qs.first()
    if tpl:
        return tpl
    kwargs = {}
    if has_field(ScheduleTemplate, "company"):
        kwargs["company"] = company
    if has_field(ScheduleTemplate, "weekday"):
        kwargs["weekday"] = weekday
    if has_field(ScheduleTemplate, "name"):
        wk = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][weekday]
        kwargs["name"] = f"{getattr(company, 'name', 'Default')} · {wk}"
    return ScheduleTemplate.objects.create(**kwargs)

def _ensure_schedule_for(company, date_obj):
    qs = Schedule.objects.all()
    if has_field(Schedule, "company"):
        qs = qs.filter(company=company)
    if has_field(Schedule, "date"):
        qs = qs.filter(date=date_obj)
    sch = qs.first()
    if sch:
        return sch
    kwargs = {}
    if has_field(Schedule, "company"):
        kwargs["company"] = company
    if has_field(Schedule, "date"):
        kwargs["date"] = date_obj
    return Schedule.objects.create(**kwargs)

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    # make sure actions bar renders
    actions_on_top = True
    actions_on_bottom = True

    list_display = tuple([n for n in ("name","phone","default_pickup_address","default_dropoff_address","active") if has_field(Client, n)])
    search_fields = tuple([n for n in ("name","phone","default_pickup_address","default_dropoff_address") if has_field(Client, n)])
    list_filter  = tuple([n for n in ("active",) if has_field(Client, n)])
    ordering = ("name",)

    # ---------- bulk actions ----------
    def _add_to_weekday(self, request, queryset, weekday):
        company = Company.objects.order_by("id").first()
        if not company:
            self.message_user(request, "No Company found.", level=messages.ERROR); return
        tpl = _ensure_weekday_template(company, weekday)
        created = 0
        with transaction.atomic():
            for client in queryset:
                payload = {"template": tpl}
                if has_field(ScheduleTemplateEntry, "client"):
                    payload["client"] = client
                if has_field(ScheduleTemplateEntry, "client_name") and hasattr(client, "name"):
                    payload["client_name"] = client.name
                if has_field(ScheduleTemplateEntry, "start_time"):
                    payload["start_time"] = DEFAULT_START_TIME
                defs = _client_defaults(client)
                for f in ("pickup_address","pickup_city","pickup_state","dropoff_address","dropoff_city","dropoff_state"):
                    if has_field(ScheduleTemplateEntry, f) and defs.get(f) is not None:
                        payload[f] = defs[f]
                ScheduleTemplateEntry.objects.create(**payload)
                created += 1
        wk = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][weekday]
        self.message_user(request, f"Added {created} entr{'y' if created==1 else 'ies'} to the {wk} template.", level=messages.SUCCESS)

    @admin.action(description="Add to Monday template (08:00)")
    def action_add_mon(self, request, queryset): self._add_to_weekday(request, queryset, 0)

    @admin.action(description="Add to Tuesday template (08:00)")
    def action_add_tue(self, request, queryset): self._add_to_weekday(request, queryset, 1)

    @admin.action(description="Add to Wednesday template (08:00)")
    def action_add_wed(self, request, queryset): self._add_to_weekday(request, queryset, 2)

    @admin.action(description="Add to Thursday template (08:00)")
    def action_add_thu(self, request, queryset): self._add_to_weekday(request, queryset, 3)

    @admin.action(description="Add to Friday template (08:00)")
    def action_add_fri(self, request, queryset): self._add_to_weekday(request, queryset, 4)

    @admin.action(description="Add to today’s schedule (08:00, scheduled)")
    def action_add_today(self, request, queryset):
        company = Company.objects.order_by("id").first()
        if not company:
            self.message_user(request, "No Company found.", level=messages.ERROR); return
        sch = _ensure_schedule_for(company, timezone.localdate())
        created = 0
        with transaction.atomic():
            for client in queryset:
                payload = {"schedule": sch}
                if has_field(ScheduleEntry, "company"): payload["company"] = company
                if has_field(ScheduleEntry, "client"): payload["client"] = client
                if has_field(ScheduleEntry, "client_name") and hasattr(client, "name"): payload["client_name"] = client.name
                if has_field(ScheduleEntry, "start_time"): payload["start_time"] = DEFAULT_START_TIME
                if has_field(ScheduleEntry, "status"): payload["status"] = "scheduled"
                defs = _client_defaults(client)
                for f in ("pickup_address","pickup_city","pickup_state","dropoff_address","dropoff_city","dropoff_state"):
                    if has_field(ScheduleEntry, f) and defs.get(f) is not None:
                        payload[f] = defs[f]
                ScheduleEntry.objects.create(**payload); created += 1
        self.message_user(request, f"Added {created} entr{'y' if created==1 else 'ies'} to today’s schedule.", level=messages.SUCCESS)

    actions = [
        "action_add_mon",
        "action_add_tue",
        "action_add_wed",
        "action_add_thu",
        "action_add_fri",
        "action_add_today",
    ]




@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = tuple([n for n in ("name","vehicle","phone","active") if has_field(Driver,n)])
    search_fields = tuple([n for n in ("name","phone") if has_field(Driver,n)])
    list_filter = tuple([f for f in ("active","vehicle") if has_field(Driver,f)])
    list_select_related = tuple([f for f in ("vehicle",) if has_field(Driver,f)])
    ordering = ("name",)

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = tuple([n for n in ("name","plate_number","capacity","active") if has_field(Vehicle,n)])
    search_fields = tuple([n for n in ("name","plate_number") if has_field(Vehicle,n)])
    list_filter  = tuple([n for n in ("active",) if has_field(Vehicle,n)])
    ordering = ("name",)

class ScheduleEntryInline(admin.TabularInline):
    model = ScheduleEntry
    fk_name = "schedule"
    extra = 0
    fields = tuple([f for f in ("start_time","client","driver","vehicle","pickup_address","dropoff_address","status") if has_field(ScheduleEntry,f)])
    autocomplete_fields = tuple([f for f in ("client","driver","vehicle") if has_field(ScheduleEntry,f)])
    show_change_link = True

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = tuple([n for n in ("date","company") if has_field(Schedule,n)] + ["entries_count"])
    if has_field(Schedule,"date"):
        date_hierarchy = "date"
        ordering = ("-date","-id")
        search_fields = ("date",)
    else:
        ordering = ("-id",)
        search_fields = ("id",)
    inlines = (ScheduleEntryInline,)

    def entries_count(self, obj):
        rel = getattr(obj, "scheduleentry_set", None)
        return rel.count() if rel else 0
    entries_count.short_description = "Entries"

    # ---- safe copy-from-template actions (no custom URLs) ----
    def _weekday_template_for(self, schedule):
        if not has_field(Schedule,"date") or not schedule.date:
            return None
        qs = ScheduleTemplate.objects.all()
        if has_field(ScheduleTemplate,"weekday"):
            qs = qs.filter(weekday=schedule.date.weekday())
        if has_field(ScheduleTemplate,"company") and has_field(Schedule,"company"):
            qs = qs.filter(company=getattr(schedule,"company",None))
        return qs.order_by("id").first()

    def _copy_from_template(self, schedule, mode: str):
        created, skipped = 0, 0
        tpl = self._weekday_template_for(schedule)
        if not tpl:
            return (0,0)

        tentries = (ScheduleTemplateEntry.objects
                    .filter(template=tpl)
                    .select_related("client","driver","vehicle")
                    .order_by("id"))

        if mode == "replace":
            schedule.scheduleentry_set.all().delete()

        existing = set()
        if mode == "append":
            for e in schedule.scheduleentry_set.all().only("client","client_name","start_time","pickup_address","dropoff_address"):
                cname = getattr(e,"client_name",None) or getattr(getattr(e,"client",None),"name","") or ""
                key = (cname.strip().lower(),
                       str(getattr(e,"start_time","")),
                       (getattr(e,"pickup_address","") or "").strip().lower(),
                       (getattr(e,"dropoff_address","") or "").strip().lower())
                existing.add(key)

        for te in tentries:
            cname = getattr(te,"client_name",None) or getattr(getattr(te,"client",None),"name","") or ""
            key = (cname.strip().lower(),
                   str(getattr(te,"start_time","")),
                   (getattr(te,"pickup_address","") or "").strip().lower(),
                   (getattr(te,"dropoff_address","") or "").strip().lower())
            if mode == "append" and key in existing:
                skipped += 1
                continue

            payload = {"schedule": schedule}
            if has_field(ScheduleEntry,"company") and has_field(Schedule,"company"):
                payload["company"] = getattr(schedule,"company",None)
            if has_field(ScheduleEntry,"status"):
                payload["status"] = "scheduled"
            if has_field(ScheduleEntry,"client") and getattr(te,"client_id",None):
                payload["client"] = te.client
            if has_field(ScheduleEntry,"client_name") and getattr(te,"client_name",None):
                payload["client_name"] = te.client_name
            if has_field(ScheduleEntry,"driver") and getattr(te,"driver_id",None):
                payload["driver"] = te.driver
            if has_field(ScheduleEntry,"vehicle") and getattr(te,"vehicle_id",None):
                payload["vehicle"] = te.vehicle
            if has_field(ScheduleEntry,"start_time"):
                payload["start_time"] = getattr(te,"start_time",None)
            for f in ("pickup_address","pickup_city","pickup_state","dropoff_address","dropoff_city","dropoff_state"):
                if has_field(ScheduleEntry,f):
                    payload[f] = getattr(te,f,None)

            ScheduleEntry.objects.create(**payload)
            created += 1
            if mode == "append":
                existing.add(key)

        return (created, skipped)

    @admin.action(description="Append from weekday template (skip dupes)")
    def action_append_from_template(self, request, queryset):
        added_total, skipped_total = 0, 0
        with transaction.atomic():
            for sch in queryset:
                c, s = self._copy_from_template(sch, mode="append")
                added_total += c; skipped_total += s
        self.message_user(request, f"Appended: added {added_total}, skipped {skipped_total}.", level=messages.SUCCESS)

    @admin.action(description="Replace from weekday template")
    def action_replace_from_template(self, request, queryset):
        created_total = 0
        with transaction.atomic():
            for sch in queryset:
                c, _ = self._copy_from_template(sch, mode="replace")
                created_total += c
        self.message_user(request, f"Replaced from template. Created {created_total} entries.", level=messages.SUCCESS)

    actions = ["action_append_from_template","action_replace_from_template"]



def existing_fields(model, preferred_order):
    existing = {f.name for f in model._meta.get_fields()}
    return [f for f in preferred_order if f in existing]

class ScheduleTemplateEntryInline(admin.TabularInline):
    model = ScheduleTemplateEntry
    fk_name = 'template'  # <-- ensure your FK is named 'template'
    extra = 0
    show_change_link = True
    autocomplete_fields = [f for f in ['client', 'driver', 'vehicle']
                           if f in {f.name for f in ScheduleTemplateEntry._meta.get_fields()}]

    # Build a safe field list that only includes columns that exist
    base_order = [
        'order', 'client', 'client_name', 'driver', 'vehicle', 'start_time',
        # addresses
        'pickup_address', 'dropoff_address',
        # optional location extras (will be filtered out if not present)
        'pickup_city', 'dropoff_city', 'pickup_state', 'dropoff_state',
        # any descriptive text columns you might have
        'route', 'route_name', 'notes', 'description',
    ]
    fields = existing_fields(ScheduleTemplateEntry, base_order)

    class Media:
        js = ("scheduler/admin_client_defaults.js",)

@admin.register(ScheduleTemplate)
class ScheduleTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'weekday', 'company', 'entry_count')
    list_filter  = ('weekday', 'company')
    search_fields = ('name',)
    inlines = [ScheduleTemplateEntryInline]

    def entry_count(self, obj):
        # If FK uses related_name='entries', this is fast; else fallback query
        try:
            return obj.entries.count()
        except Exception:
            return ScheduleTemplateEntry.objects.filter(template=obj).count()

@admin.register(ScheduleTemplateEntry)
class ScheduleTemplateEntryAdmin(admin.ModelAdmin):
    # Only include fields that exist on the model
    readonly_fields = ('client_name',)
    base_list = [
        'id', 'template', 'order', 'client_name', 'client', 'driver', 'vehicle', 'start_time',
        'pickup_address', 'dropoff_address'
    ]
    list_display = existing_fields(ScheduleTemplateEntry, base_list)

    base_filters = ['template', 'driver', 'vehicle']
    list_filter = existing_fields(ScheduleTemplateEntry, base_filters)

    base_search = [
        'client_name', 'pickup_address', 'dropoff_address', 'notes', 'route', 'route_name', 'description'
    ]
    search_fields = existing_fields(ScheduleTemplateEntry, base_search)

    autocomplete_fields = [f for f in ['client', 'driver', 'vehicle']
                           if f in {f.name for f in ScheduleTemplateEntry._meta.get_fields()}]


from django.contrib import admin
from django import forms

def _existing_fields(model, names):
    have = {f.name for f in model._meta.get_fields()}
    return [n for n in names if n in have]

# --- optional server-side autofill mixin (fills blanks from client defaults) ---
class _EntryAutofillMixin:
    """
    Mixin for cleaning methods to automatically sync and fill
    client-related fields based on the selected client object.
    """
    def clean(self):
        cleaned = super().clean()
        client = cleaned.get("client")
        
        # --- 1. Client Name Sync Logic ---
        client_name = (cleaned.get("client_name") or "").strip()
        
        if client and client_name and client.name.strip() != client_name:
            # Case 1: Client selected, name mismatch -> Force sync
            cleaned["client_name"] = client.name
        elif client and not client_name:
            # Case 2: Client selected, name field empty -> Autofill
            cleaned["client_name"] = client.name

        # --- 2. Address Autofill Logic ---
        if client:
            
            # Helper function to find and set the value from client defaults
            def _set(field_name: str, client_attrs: list):
                """Sets the cleaned[field_name] from the first non-empty attribute in client_attrs."""
                # Only autofill if the field is currently empty in the form
                if not cleaned.get(field_name):
                    for attr in client_attrs:
                        value = getattr(client, attr, None)
                        if value:
                            cleaned[field_name] = value
                            break

            # Apply autofill logic for addresses and cities/states
            _set("pickup_address",  ["default_pickup_address", "pickup_address"])
            _set("pickup_city",     ["pickup_city"])
            _set("pickup_state",    ["pickup_state"])
            _set("dropoff_address", ["default_dropoff_address", "dropoff_address"])
            _set("dropoff_city",    ["dropoff_city"])
            _set("dropoff_state",   ["dropoff_state"])

        return cleaned

# --- ScheduleEntry admin (NEW) ---
class ScheduleEntryForm(_EntryAutofillMixin, forms.ModelForm):
    class Meta:
        model = ScheduleEntry
        fields = "__all__"

@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(admin.ModelAdmin):
    form = ScheduleEntryForm

    list_display = _existing_fields(ScheduleEntry, [
        "id","schedule","start_time","client_name","client","driver","vehicle",
        "pickup_address","dropoff_address","status"
    ])
    list_filter  = _existing_fields(ScheduleEntry, ["schedule","driver","vehicle","status"])
    search_fields = _existing_fields(ScheduleEntry, [
        "client_name","pickup_address","dropoff_address","notes","route","route_name","description"
    ])
    autocomplete_fields = _existing_fields(ScheduleEntry, ["client","driver","vehicle"])

    class Media:
        # loads the JS that auto-fills + provides dropdown suggestions
        js = ("scheduler/js/autofill_client_admin.js",)

# --- Optional: show entries inline under each Schedule detail page ---
class ScheduleEntryInline(admin.TabularInline):
    model = ScheduleEntry
    fk_name = "schedule"  # FK on ScheduleEntry -> Schedule
    extra = 0
    show_change_link = True
    fields = _existing_fields(ScheduleEntry, [
        "start_time","client","client_name","driver","vehicle",
        "pickup_address","dropoff_address","status"
    ])
    autocomplete_fields = _existing_fields(ScheduleEntry, ["client","driver","vehicle"])

    class Media:
        js = ("scheduler/admin_client_defaults.js",)


from django.contrib import admin
from .models import TripEventLog

@admin.register(TripEventLog)
class TripEventLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "event_type", "schedule_entry", "driver", "vehicle", "latitude", "longitude")
    list_filter = ("event_type", "timestamp", "driver")
    search_fields = ("schedule_entry__client_name", "driver__name", "notes")

    # make it read-only in admin, so no one edits audit logs
    readonly_fields = (
        "schedule_entry",
        "event_type",
        "timestamp",
        "driver",
        "vehicle",
        "latitude",
        "longitude",
        "notes",
        "ip_address",
        "user_agent",
    )

    def has_add_permission(self, request):
        # no manual creation via admin
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

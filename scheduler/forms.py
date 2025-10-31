# scheduler/forms.py
from django import forms
from .models import Client, Driver, ScheduleEntry


def _has(model, field: str) -> bool:
    try:
        model._meta.get_field(field)
        return True
    except Exception:
        return False

# scheduler/forms.py
from django import forms
try:
    from .models import AutoSchedule
except Exception:
    AutoSchedule = None

if AutoSchedule is not None:
    class AutoScheduleForm(forms.ModelForm):
        class Meta:
            model = AutoSchedule
            fields = ["client", "driver", "date", "pickup_time", "status", "notes",
                      "pickup_address", "pickup_city", "dropoff_address", "dropoff_city"]

# Ask for a superset; we’ll only keep fields that truly exist.
_WISH = [
    "schedule", "driver", "client", "client_name",
    "start_time", "end_time", "status",
    "pickup_address", "pickup_city",
    "dropoff_address", "dropoff_city",
    # coords (some schemas use *_latitude/longitude, others *_lat/lng)
    "start_latitude", "start_longitude", "end_latitude", "end_longitude",
    "start_lat", "start_lng", "end_lat", "end_lng",
]
_FIELDS = [f for f in _WISH if _has(ScheduleEntry, f)]


# scheduler/forms.py
from django import forms
from django.db.models import Q
from .models import ScheduleTemplateEntry, Driver, Client, Vehicle

JUNK_TOKENS = {"-", "—", "–", "-----", "--------", "---------"}

def _clean_name(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    if s in JUNK_TOKENS:
        return ""
    return s

def _resolve_by_name(qs, name: str):
    if not name:
        return None
    name = name.strip()
    # Try exact (case-insensitive), then contains
    obj = qs.filter(name__iexact=name).first()
    if obj:
        return obj
    return qs.filter(name__icontains=name).first()

class ScheduleTemplateEntryForm(forms.ModelForm):
    class Meta:
        model = ScheduleTemplateEntry
        fields = (
            "order", "start_time",
            "client", "client_name",
            "driver", "driver_name",
            "vehicle", "vehicle_name",
            "pickup_address", "dropoff_address",
            "notes",
        )

    def clean(self):
        cleaned = super().clean()

        # Strip junk & whitespace from free-text fields
        cleaned["client_name"]  = _clean_name(cleaned.get("client_name")  or "")
        cleaned["driver_name"]  = _clean_name(cleaned.get("driver_name")  or "")
        cleaned["vehicle_name"] = _clean_name(cleaned.get("vehicle_name") or "")

        e: ScheduleTemplateEntry = self.instance
        company = e.template.company if e and e.template_id else None

        # If no FK chosen, try to resolve from name (within the same company)
        if company:
            if not cleaned.get("client") and cleaned.get("client_name"):
                cleaned["client"] = _resolve_by_name(Client.objects.filter(company=company), cleaned["client_name"])
            if not cleaned.get("driver") and cleaned.get("driver_name"):
                cleaned["driver"] = _resolve_by_name(Driver.objects.filter(company=company), cleaned["driver_name"])
            if not cleaned.get("vehicle") and cleaned.get("vehicle_name"):
                cleaned["vehicle"] = _resolve_by_name(Vehicle.objects.filter(company=company), cleaned["vehicle_name"])

        # If FK exists but free-text is junk or mismatched, normalize the free-text to FK name (optional)
        c = cleaned.get("client")
        if c:
            cleaned["client_name"] = c.name
        d = cleaned.get("driver")
        if d:
            cleaned["driver_name"] = d.name
        v = cleaned.get("vehicle")
        if v:
            cleaned["vehicle_name"] = v.name

        # Normalize pickup/dropoff placeholders
        for fld in ("pickup_address", "dropoff_address"):
            val = _clean_name(cleaned.get(fld) or "")
            cleaned[fld] = val

        return cleaned

# scheduler/forms.py
from django import forms
from django.apps import apps

def _get_or_create_company():
    Company = apps.get_model("scheduler", "Company")
    if not Company:
        return None
    return Company.objects.first() or Company.objects.create(name="Default")

# scheduler/forms.py
from django import forms
from .models import ScheduleEntry, Client

_FIELDS = [
    "client",
    "driver",
    "pickup_address",
    "dropoff_address",
    "start_time",
    "notes",
]

from django import forms
from .models import ScheduleEntry, Client

from django import forms
from .models import ScheduleEntry, Client

class ScheduleEntryForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        queryset=Client.objects.order_by("name"),
        widget=forms.Select(attrs={"id": "id_client"})
    )

    class Meta:
        model = ScheduleEntry
        fields = ["client", "driver", "pickup_address", "dropoff_address", "start_time", "pickup_city","dropoff_city", "notes"]
        widgets = {
            "driver":          forms.Select(attrs={"id": "id_driver"}),
            "pickup_address":  forms.TextInput(attrs={"id": "id_pickup_address"}),
            "dropoff_address": forms.TextInput(attrs={"id": "id_dropoff_address"}),
            "pickup_city":    forms.TextInput(attrs={"id": "id_pickup_city"}),
            "dropoff_city":   forms.TextInput(attrs={"id": "id_dropoff_city"}),
            "start_time":      forms.TimeInput(attrs={"id": "id_start_time", "type": "time"}),
            "notes":           forms.Textarea(attrs={"id": "id_notes", "rows": 2}),
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = "__all__"


class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = "__all__"


class ScheduleEntryForm(forms.ModelForm):
    class Meta:
        model = ScheduleEntry
        fields = "__all__"
       


class GenerateScheduleForm(forms.Form):
    date  = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )
    force = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Overwrite if a schedule already exists.",
        label="Force overwrite"
    )

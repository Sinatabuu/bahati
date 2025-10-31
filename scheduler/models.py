# scheduler/models.py
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify



# --- Effective (fallback) helpers ---
def eff_pickup_address(self) -> str:
    return (self.pickup_address or (self.client and self.client.pickup_address) or "").strip()

def eff_dropoff_address(self) -> str:
    return (self.dropoff_address or (self.client and self.client.dropoff_address) or "").strip()

def eff_pickup_city(self) -> str:
    return (self.pickup_city or (self.client and self.client.pickup_city) or "").strip()

def eff_dropoff_city(self) -> str:
    return (self.dropoff_city or (self.client and self.client.dropoff_city) or "").strip()

# ==========
# Base types
# ==========

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):   return self.filter(is_deleted=False)
    def deleted(self): return self.filter(is_deleted=True)


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects     = SoftDeleteQuerySet.as_manager()
    all_objects = models.Manager()  # raw, includes deleted

    def delete(self, using=None, keep_parents=False, hard=False):
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        # relies on updated_at from TimeStampedModel in concrete subclasses
        self.save(update_fields=["is_deleted", "updated_at"])

    class Meta:
        abstract = True


# ===============
# Tenancy anchor
# ===============

class Company(TimeStampedModel):
    """
    Tenant/org. All business data is FK-scoped to one Company.
    """
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    # optional org settings
    timezone = models.CharField(max_length=64, default="America/New_York")
    meta = models.JSONField(default=dict, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):  # admin uses this a lot
        return self.name


# =====================
# People / Addresses
# =====================

class Driver(TimeStampedModel, SoftDeleteModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="drivers")
    slug    = models.SlugField(max_length=200)  # unique within company
    name    = models.CharField(max_length=200)
    phone   = models.CharField(max_length=50, blank=True)
    user    = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="driver"
    )
    active  = models.BooleanField(default=True)
    
    # Optional: where a driver usually starts/end
    home_base_address = models.CharField(max_length=300, blank=True)
    home_latitude     = models.FloatField(null=True, blank=True)
    home_longitude    = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "slug"], name="uniq_driver_slug_per_company"
            )
        ]
        indexes = [
            models.Index(fields=["company", "active"]),
            models.Index(fields=["company", "name"]),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Client(TimeStampedModel, SoftDeleteModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="clients")
    slug    = models.SlugField(max_length=200)  # unique within company
    name    = models.CharField(max_length=200)

    # canonical pickup/dropoff (can be overridden per entry)
    pickup_address   = models.CharField(max_length=300, blank=True)
    pickup_latitude  = models.FloatField(null=True, blank=True)
    pickup_longitude = models.FloatField(null=True, blank=True)
    pickup_city      = models.CharField(max_length=100, blank=True)
    dropoff_city      = models.CharField(max_length=100, blank=True)
    dropoff_address   = models.CharField(max_length=300, blank=True)
    dropoff_latitude  = models.FloatField(null=True, blank=True)
    dropoff_longitude = models.FloatField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "slug"], name="uniq_client_slug_per_company"
            )
        ]
        indexes = [
            models.Index(fields=["company", "name"]),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


# ==========
# Vehicles (optional but useful for capacity/assignments)
# ==========

class Vehicle(TimeStampedModel, SoftDeleteModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="vehicles")
    slug    = models.SlugField(max_length=200)
    name    = models.CharField(max_length=200)
    plate   = models.CharField(max_length=64, blank=True)
    capacity = models.PositiveIntegerField(default=4, validators=[MinValueValidator(1)])  # seats

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "slug"], name="uniq_vehicle_slug_per_company"
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


# ==========
# Scheduling
# ==========

class Schedule(TimeStampedModel):
    """
    One logical schedule per day per company (you can extend with shifts/regions later).
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="schedules")
    date    = models.DateField(db_index=True)
    meta    = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "date"], name="uniq_schedule_per_company_date"
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company} – {self.date}"


class ScheduleEntry(TimeStampedModel, SoftDeleteModel):
    """
    A single pickup→dropoff (or stop) assigned to a driver/vehicle, part of a Schedule.
    """
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("en route", "En route"),
        ("arrived", "Arrived"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="entries")
    company  = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="entries")  # denormalize for fast filters
    driver   = models.ForeignKey(Driver, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")
    vehicle  = models.ForeignKey(Vehicle, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")
    client   = models.ForeignKey(Client,  null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")

    # freeze some human-readable client info for the day
    client_name = models.CharField(max_length=200, blank=True)

    # planned time windows
    start_time = models.TimeField(null=True, blank=True, db_index=True)
    end_time   = models.TimeField(null=True, blank=True)

    # addresses (resolved per entry; fallback to Client fields in your view if blank)
    pickup_address   = models.CharField(max_length=300, blank=True)
    pickup_latitude  = models.FloatField(null=True, blank=True)
    pickup_longitude = models.FloatField(null=True, blank=True)
    pickup_city      = models.CharField(max_length=100, blank=True)
    dropoff_city      = models.CharField(max_length=100, blank=True)
    dropoff_address   = models.CharField(max_length=300, blank=True)
    dropoff_latitude  = models.FloatField(null=True, blank=True)
    dropoff_longitude = models.FloatField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled", db_index=True)
    notes  = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "driver", "start_time"]),
            models.Index(fields=["company", "schedule", "start_time"]),
        ]
        ordering = ["start_time", "id"]

    def __str__(self):
        label = self.client_name or (self.client and self.client.name) or "—"
        t = self.start_time.strftime("%H:%M") if self.start_time else "--:--"
        d = self.driver.name if self.driver else "Unassigned"
        return f"[{t}] {label} → {d}"

    # convenience
    @property
    def date(self):
        return self.schedule.date if self.schedule_id else None

    # models.py (inside class ScheduleEntry)

def eff_pickup_address(self):
     return (self.pickup_address or (self.client and self.client.pickup_address) or "").strip()

def eff_dropoff_address(self):
    return (self.dropoff_address or (self.client and self.client.dropoff_address) or "").strip()

def eff_pickup_city(self):
    # if you have pickup_city field on entry; else only client
        return (getattr(self, "pickup_city", "") or (self.client and getattr(self.client, "pickup_city", "")) or "").strip()

def eff_dropoff_city(self):
        return (getattr(self, "dropoff_city", "") or (self.client and getattr(self.client, "dropoff_city", "")) or "").strip()

def eff_client_name(self):
        return (self.client_name or (self.client and self.client.name) or "").strip()

def eff_time_str(self):
    # your “Time” column is start_time; render as 12-hour or 24-hour as you prefer
    return self.start_time.strftime("%-I:%M %p") if self.start_time else ""


# ======================
# Live driver telemetry
# ======================

class DriverLocation(TimeStampedModel):
    """
    Append-only pings (do NOT FK to ScheduleEntry to keep it simple).
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="driver_locations")
    driver  = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="locations")
    when    = models.DateTimeField(default=timezone.now, db_index=True)

    latitude  = models.FloatField()
    longitude = models.FloatField()
    accuracy  = models.FloatField(null=True, blank=True)
    heading   = models.FloatField(null=True, blank=True)
    speed     = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "driver", "-when"]),
        ]
        ordering = ["-when"]

    def __str__(self):
        return f"{self.driver} @ {self.when:%Y-%m-%d %H:%M:%S}"[:80]


# --- Back-compat shim for legacy imports ---
# If you have a replacement model (e.g. ScheduleTemplate), alias it.
try:
    ScheduleTemplate  # noqa: F401
except NameError:
    ScheduleTemplate = None

if ScheduleTemplate is not None:
    class AutoSchedule(ScheduleTemplate):  # proxy model, no new table
        class Meta:
            proxy = True
            verbose_name = "Auto schedule"
            verbose_name_plural = "Auto schedules"


# --- WEEKDAY TEMPLATES FOR STATIC SCHEDULES ---

class ScheduleTemplate(models.Model):
    """
    A template for a weekday (Mon-Fri) that defines default trips.
    Admin edits this once; we materialize it for any matching date.
    """
    MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
    WEEKDAY_CHOICES = (
        (MON, "Monday"),
        (TUE, "Tuesday"),
        (WED, "Wednesday"),
        (THU, "Thursday"),
        (FRI, "Friday"),
        (SAT, "Saturday"),
        (SUN, "Sunday"),
    )

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="schedule_templates")
    name = models.CharField(max_length=200, help_text="e.g. 'Weekday AM–PM default route'")
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES, help_text="Only Mon–Fri will be materialized.")
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "weekday", "name"],
                                    name="uniq_template_name_per_company_weekday")
        ]
        ordering = ["company", "weekday", "name"]

    def __str__(self):
        return f"{self.company} · {self.get_weekday_display()} · {self.name}"


class ScheduleTemplateEntry(models.Model):
    """
    One line (trip) in a weekday template.
    We let admins pick FKs OR type free-text; during materialization we resolve.
    """
    template = models.ForeignKey(ScheduleTemplate, on_delete=models.CASCADE, related_name="entries")
    order = models.PositiveIntegerField(default=0, help_text="Display/materialize order")

    # Optional direct FKs
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL)
    driver = models.ForeignKey(Driver, null=True, blank=True, on_delete=models.SET_NULL)
    vehicle = models.ForeignKey(Vehicle, null=True, blank=True, on_delete=models.SET_NULL)

    # Fallback free-text (if you prefer picking by name/slug later)
    client_name = models.CharField(max_length=500, blank=True)
    driver_name = models.CharField(max_length=200, blank=True)
    vehicle_name = models.CharField(max_length=200, blank=True)

    # When this trip usually starts (time-of-day)
    start_time = models.TimeField(null=True, blank=True)

    # Addresses: if blank, we'll pull from Client defaults
    pickup_address = models.CharField(max_length=300, blank=True)
    dropoff_address = models.CharField(max_length=300, blank=True)
    dropoff_city = models.CharField(max_length=100, blank=True)
    pickup_city = models.CharField(max_length=100, blank=True) 
    
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["order", "id"]


    def __str__(self):
        who = self.client_name or (self.client and self.client.name) or "Client"
        return f"{self.template} · {self.start_time} · {who}"

    def clean(self):
        """Validate that we don't save junk placeholder data."""
        # Prevent junk data patterns
        junk_patterns = [
            "PICK UP", "TIME NAME", "DRIVER ID", "ADDRESS PICK", 
            "MEMBER", "PHONE", "NAME", "CLIENT", "DRIVER", "VEHICLE",
            "---------", "--------", "-----", "---", "--"
        ]
        
        # Check client_name for junk patterns
        client_name_upper = (self.client_name or "").strip().upper()
        if any(pattern in client_name_upper for pattern in junk_patterns):
            raise ValidationError({
                'client_name': 'Client name contains invalid placeholder text. Use actual client name.'
            })
        
        # Check driver_name for junk patterns  
        driver_name_upper = (self.driver_name or "").strip().upper()
        if any(pattern in driver_name_upper for pattern in junk_patterns):
            raise ValidationError({
                'driver_name': 'Driver name contains invalid placeholder text. Use actual driver name.'
            })
            
        # Check vehicle_name for junk patterns
        vehicle_name_upper = (self.vehicle_name or "").strip().upper()
        if any(pattern in vehicle_name_upper for pattern in junk_patterns):
            raise ValidationError({
                'vehicle_name': 'Vehicle name contains invalid placeholder text. Use actual vehicle name.'
            })
        
        # Ensure we have meaningful client data (driver is optional for templates)
        if not self.client and not self.client_name:
            raise ValidationError('Either select a client or provide a client name.')
        
        # Prevent saving entries that are clearly template headers/footers
        if self.client_name and len(self.client_name.strip()) < 2:
            raise ValidationError('Client name is too short.')

    def save(self, *args, **kwargs):
        # Call full_clean to trigger validation
        self.full_clean()
        super().save(*args, **kwargs)
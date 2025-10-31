# scheduler/serializers.py
from __future__ import annotations

from rest_framework import serializers
from .models import ScheduleEntry


def _maps_for(address: str | None, city: str | None):
    addr = (address or "").strip()
    city = (city or "").strip()
    if not addr and not city:
        return {"google": None, "apple": None, "waze": None}
    q = ", ".join([p for p in (addr, city) if p])
    # Use URL-encoded query; let the client app open in the right app
    from urllib.parse import quote_plus
    enc = quote_plus(q)
    return {
        "google": f"https://www.google.com/maps/search/?api=1&query={enc}",
        "apple":  f"http://maps.apple.com/?q={enc}",
        "waze":   f"https://waze.com/ul?q={enc}",
    }


class ScheduleEntrySerializer(serializers.ModelSerializer):
    # Always send effective values (entry value OR client fallback)
    client_name     = serializers.SerializerMethodField()
    pickup_address  = serializers.SerializerMethodField()
    dropoff_address = serializers.SerializerMethodField()
    pickup_city     = serializers.SerializerMethodField()
    dropoff_city    = serializers.SerializerMethodField()

    pickup_maps     = serializers.SerializerMethodField()
    dropoff_maps    = serializers.SerializerMethodField()

    driver = serializers.SerializerMethodField()  # small, stable shape for FE

    class Meta:
        model = ScheduleEntry
        fields = (
            "id",
            "start_time", "end_time",
            "status", "notes",
            # names & addressing
            "client_name",
            "pickup_address", "pickup_city",
            "dropoff_address", "dropoff_city",
            # nav links
            "pickup_maps", "dropoff_maps",
            # assignment
            "driver",
        )

    # ---- Effective field helpers ----

    def get_client_name(self, obj: ScheduleEntry) -> str:
        # Prefer canonical Client.name if FK is present; fall back to stored client_name
        if obj.client_id and obj.client:
            return obj.client.name
        return (obj.client_name or "").strip()

    def get_pickup_address(self, obj: ScheduleEntry) -> str:
        if (obj.pickup_address or "").strip():
            return obj.pickup_address.strip()
        if obj.client_id and obj.client:
            return (obj.client.pickup_address or "").strip()
        return ""

    def get_dropoff_address(self, obj: ScheduleEntry) -> str:
        if (obj.dropoff_address or "").strip():
            return obj.dropoff_address.strip()
        if obj.client_id and obj.client:
            return (obj.client.dropoff_address or "").strip()
        return ""

    def get_pickup_city(self, obj: ScheduleEntry) -> str:
        # City may live only on Client for many rows
        if (getattr(obj, "pickup_city", "") or "").strip():
            return obj.pickup_city.strip()
        if obj.client_id and obj.client:
            return (getattr(obj.client, "pickup_city", "") or "").strip()
        return ""

    def get_dropoff_city(self, obj: ScheduleEntry) -> str:
        if (getattr(obj, "dropoff_city", "") or "").strip():
            return obj.dropoff_city.strip()
        if obj.client_id and obj.client:
            return (getattr(obj.client, "dropoff_city", "") or "").strip()
        return ""

    # ---- Maps ----

    def get_pickup_maps(self, obj: ScheduleEntry):
        return _maps_for(self.get_pickup_address(obj), self.get_pickup_city(obj))

    def get_dropoff_maps(self, obj: ScheduleEntry):
        return _maps_for(self.get_dropoff_address(obj), self.get_dropoff_city(obj))

    # ---- Driver mini-object ----

    def get_driver(self, obj: ScheduleEntry):
        if not obj.driver_id or not obj.driver:
            return None
        return {"id": obj.driver.id, "name": obj.driver.name}

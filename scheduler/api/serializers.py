# scheduler/api/serializers.py
from rest_framework import serializers
from scheduler.models import ScheduleEntry

class ScheduleEntrySerializer(serializers.ModelSerializer):
    date = serializers.SerializerMethodField()
    pickup_address = serializers.SerializerMethodField()
    dropoff_address = serializers.SerializerMethodField()
    pickup_city = serializers.SerializerMethodField()
    dropoff_city = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    driver = serializers.SerializerMethodField()

    class Meta:
        model = ScheduleEntry
        fields = [
            "id", "date", "start_time", "status",
            "client", "client_name", "driver",
            "pickup_address", "pickup_city",
            "dropoff_address", "dropoff_city",
            "notes",
        ]

    def get_date(self, obj):
        return obj.date.isoformat() if obj.date else None

    def get_pickup_address(self, obj):
        return obj.eff_pickup_address()

    def get_dropoff_address(self, obj):
        return obj.eff_dropoff_address()

    def get_pickup_city(self, obj):
        return obj.eff_pickup_city()

    def get_dropoff_city(self, obj):
        return obj.eff_dropoff_city()

    def get_client(self, obj):
        return obj.client.name if obj.client else None

    def get_driver(self, obj):
        return obj.driver.name if obj.driver else None

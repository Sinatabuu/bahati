import os
from datetime import time
from scheduler.models import ScheduleTemplate, ScheduleTemplateEntry, Company

SOURCE_DIR = "/home/maigwa/work/BAHATI/pdfs"
COMPANY_ID = 1  # Replace with your actual Company ID

WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
}

def parse_line(line):
    parts = [p.strip() for p in line.split(",")]
    return {
        "driver_name": parts[0],
        "start_time": time.fromisoformat(parts[1]),
        "client_name": parts[2],
        "pickup_address": parts[3],
        "pickup_city": parts[4],
        "dropoff_address": parts[5],
        "dropoff_city": parts[6],
    }

def import_templates():
    company = Company.objects.get(id=COMPANY_ID)

    for filename in os.listdir(SOURCE_DIR):
        if filename.endswith(".txt"):
            weekday_name = filename.replace(".txt", "").lower()
            if weekday_name not in WEEKDAY_MAP:
                continue

            weekday = WEEKDAY_MAP[weekday_name]
            template, _ = ScheduleTemplate.objects.get_or_create(
                company=company,
                weekday=weekday,
                name=f"{weekday_name.capitalize()} Default",
                defaults={"active": True}
            )

            with open(os.path.join(SOURCE_DIR, filename), "r", encoding="utf-8") as file:
                for i, line in enumerate(file):
                    data = parse_line(line)
                    ScheduleTemplateEntry.objects.create(
                        template=template,
                        order=i,
                        driver_name=data["driver_name"],
                        client_name=data["client_name"],
                        start_time=data["start_time"],
                        pickup_address=data["pickup_address"],
                        pickup_city=data["pickup_city"],
                        dropoff_address=data["dropoff_address"],
                        dropoff_city=data["dropoff_city"]
                    )

    print("✅ Schedule templates imported successfully.")

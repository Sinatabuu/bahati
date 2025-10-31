import datetime
import openpyxl
from scheduler.models import Schedule, ScheduleEntry, Client, Driver
from scheduler.models import Company
wb = openpyxl.load_workbook("clients.xlsx")
sheet = wb.active

for i, row in enumerate(sheet.iter_rows(min_row=2), start=2):
    try:
        client_name = row[0].value
        driver_name = row[1].value
        pickup_address = row[2].value
        pickup_city = row[3].value
        dropoff_address = row[4].value
        dropoff_city = row[5].value
        time_str = row[6].value

        if not client_name or "PICK UP" in str(client_name).upper():
            continue  # Skip header or junk rows

        # Parse time
        try:
            start_time = datetime.datetime.strptime(str(time_str), "%I:%M %p").time()
        except Exception:
            start_time = None

        # Get or create schedule
        schedule_date = datetime.date(2025, 10, 17)
        schedule, _ = Schedule.objects.get_or_create(date=schedule_date)
        company = Company.objects.get(name="Bahati Transport")
        # Match client and driver
        client = Client.objects.filter(name__icontains=client_name).first()
        driver = Driver.objects.filter(name__icontains=driver_name).first()

        # Create entry
        ScheduleEntry.objects.create(
            schedule=schedule,
            client=client,
            driver=driver,
            company=company,
            client_name=client_name,
            pickup_address=pickup_address,
            pickup_city=pickup_city,
            dropoff_address=dropoff_address,
            dropoff_city=dropoff_city,
            start_time=start_time,
            status="scheduled",
        )
    except Exception as e:
        print(f"❌ Row {i} failed: {e}")

print("✅ Schedule entries imported.")

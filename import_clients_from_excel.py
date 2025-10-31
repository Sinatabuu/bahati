import openpyxl
from scheduler.models import Client, Company
from django.utils.text import slugify

EXCEL_PATH = "/home/maigwa/work/BAHATI/clients.xlsx"
COMPANY_ID = 1  # Replace with your actual company ID

def import_clients():
    wb = openpyxl.load_workbook(EXCEL_PATH)
    sheet = wb.active
    company = Company.objects.get(id=COMPANY_ID)

    for row in sheet.iter_rows(min_row=2, values_only=True):
        first_name = str(row[0]).strip() if row[0] else ""
        last_name = str(row[1]).strip() if row[1] else ""
        pickup_address = str(row[2]).strip() if row[2] else ""
        pickup_city = str(row[3]).strip() if row[3] else ""
        dropoff_address = str(row[4]).strip() if row[4] else ""
        dropoff_city = str(row[5]).strip() if row[5] else ""
        phone = str(row[6]).strip() if row[6] else ""

        full_name = f"{first_name} {last_name}".strip()
        slug = slugify(full_name)

        client, created = Client.objects.update_or_create(
            company=company,
            slug=slug,
            defaults={
                "name": full_name,
                "pickup_address": pickup_address,
                "pickup_city": pickup_city,
                "dropoff_address": dropoff_address,
                "dropoff_city": dropoff_city,
                "notes": "",
            }
        )

        print(f"{'Created' if created else 'Updated'}: {full_name}")

    print("✅ All clients imported and cleaned.")

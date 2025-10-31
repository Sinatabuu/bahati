import os
import csv

SOURCE_DIR = "/home/maigwa/work/BAHATI/pdfs"
DEST_DIR = "/home/maigwa/work/BAHATI/csvs"

# Ensure destination folder exists
os.makedirs(DEST_DIR, exist_ok=True)

# Define CSV headers
headers = [
    "Driver", "Pickup Time", "Passenger", "Pickup Address", "Pickup City",
    "Drop-off Address", "Drop-off City", "Phone", "Distance", "Comments"
]

def parse_txt_line(line):
    # Customize this based on your actual .txt format
    parts = line.strip().split("\t")  # or use comma if comma-separated
    return parts[:len(headers)]

for filename in os.listdir(SOURCE_DIR):
    if filename.endswith(".txt"):
        txt_path = os.path.join(SOURCE_DIR, filename)
        csv_path = os.path.join(DEST_DIR, filename.replace(".txt", ".csv"))

        with open(txt_path, "r", encoding="utf-8") as txt_file, \
             open(csv_path, "w", newline="", encoding="utf-8") as csv_file:

            writer = csv.writer(csv_file)
            writer.writerow(headers)

            for line in txt_file:
                row = parse_txt_line(line)
                writer.writerow(row)

print("✅ All TXT files converted to CSV.")

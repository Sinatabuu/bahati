# clean_template.py
import os

template_path = 'scheduler/templates/scheduler/driver_dashboard.html'

# Read the file
with open(template_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace non-breaking spaces (U+00A0) with regular spaces
cleaned = content.replace('\u00a0', ' ')

# Write back
with open(template_path, 'w', encoding='utf-8') as f:
    f.write(cleaned)

print(f"✅ Cleaned non-breaking spaces in {template_path}")

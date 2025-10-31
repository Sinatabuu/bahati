# scheduler/management/commands/seed_templates_from_txt.py
import os
import re
from datetime import datetime
from django.core.management.base import BaseCommand
# Assuming these models exist:
from scheduler.models import Company, ScheduleTemplate, ScheduleTemplateEntry 

class Command(BaseCommand):
    help = 'Seed M-F schedule templates from text files in pdfs directory'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company',
            type=str,
            help='Company name to associate templates with',
            default='Bahati Transport'
        )
        parser.add_argument(
            '--pdfs-dir',
            type=str,
            help='Directory containing the schedule text files',
            default='./pdfs' 
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing template entries before seeding',
            default=True
        )

    def handle(self, *args, **options):
        # FIX: Argument parser converts hyphens to underscores ('-' -> '_').
        company_name = options['company']
        pdfs_dir = options['pdfs_dir'] # Use the provided path
        clear_existing = options['clear_existing'] 
        
        # Resolve the full path
        if not os.path.isabs(pdfs_dir):
            pdfs_dir = os.path.join(os.getcwd(), pdfs_dir)

        # Get or create company
        company, created = Company.objects.get_or_create(
            name=company_name,
            defaults={'timezone': 'America/New_York'}
        )
        if created:
            self.stdout.write(f'Created company: {company_name}')
        
        # Map weekday names to numbers (Mon-Fri only)
        weekday_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2,
            'thursday': 3, 'friday': 4
        }
        
        # Process each text file in the directory
        if not os.path.exists(pdfs_dir):
            self.stdout.write(
                self.style.ERROR(f'Directory not found: {pdfs_dir}. Please specify the correct --pdfs-dir.')
            )
            return
            
        txt_files = [f for f in os.listdir(pdfs_dir) if f.endswith('.txt')]
        
        valid_files = []
        for filename in txt_files:
            weekday_match = re.search(r'(monday|tuesday|wednesday|thursday|friday)', 
                                     filename.lower())
            if weekday_match:
                valid_files.append(filename)
        
        if not valid_files:
            self.stdout.write(
                self.style.WARNING(f'No M-F .txt files found in the directory: {pdfs_dir}')
            )
            return
            
        for filename in valid_files:
            filepath = os.path.join(pdfs_dir, filename)
            self.stdout.write(f'Processing {filename}...')
            
            weekday_match = re.search(r'(monday|tuesday|wednesday|thursday|friday)', 
                                     filename.lower())
            weekday_name = weekday_match.group(1)
            weekday_num = weekday_map[weekday_name]
            
            template_name = f"Static {weekday_name.capitalize()}"
            template, created = ScheduleTemplate.objects.get_or_create(
                company=company,
                weekday=weekday_num,
                name=template_name,
                defaults={'active': True}
            )
            
            if clear_existing and not created:
                deleted_count = template.entries.all().delete()[0]
                if deleted_count > 0:
                    self.stdout.write(f'  Cleared {deleted_count} existing entries')
            
            entry_count = self.parse_schedule_file(filepath, template)
            self.stdout.write(f'  Created {entry_count} entries for {weekday_name.capitalize()}')
            
        self.stdout.write(
            self.style.SUCCESS('Successfully seeded M-F schedule templates from text files')
        )

    # --- Helper methods (parse_time_from_string, is_driver_token, clean_client_name) remain the same ---

    def parse_time_from_string(self, line, time_str, am_pm):
        """Safely parses a time string into a time object, handling 24h and implied 12h formats."""
        try:
            if am_pm:
                return datetime.strptime(f"{time_str} {am_pm.upper()}", "%I:%M %p").time()
            else:
                try:
                    return datetime.strptime(time_str, "%H:%M").time()
                except ValueError:
                    # Implied AM/PM if 12h format is used without a marker
                    line_lower = line.lower()
                    if 'pm' in line_lower or 'p.m.' in line_lower:
                        return datetime.strptime(f"{time_str} PM", "%I:%M %p").time()
                    else:
                        return datetime.strptime(f"{time_str} AM", "%I:%M %p").time()
        except ValueError:
            return None

    def is_driver_token(self, token):
        """Checks if a string is likely a driver ID/token (e.g., JAVBE, ERNEST)."""
        if not token or len(token) < 2 or len(token) > 15:
            return False
        if not re.search(r'[A-Z]', token, re.IGNORECASE):
            return False
        # Exclude common client names that might be mistaken for a token
        if token.upper() in ['PHONE', 'TIWE', 'MASS', 'TRA', 'AM', 'PM', 'P', 'D', 'RYAN', 'ALISON', 'DUGAN', 'PATEL', 'JUDITH', 'RAUL', 'MARY', 'CURTIS', 'BARRY']:
            return False
        return True

    def clean_client_name(self, text):
        """Extract just a clean name from a string, stripping noise and non-name elements."""
        if not text:
            return ""
        
        cleaned = text.strip()
        
        # Aggressively remove known noise/IDs that bleed in
        cleaned = re.sub(r'(MARKE|PHONE|TIWE|ACORESE|ADORES|CIM|TRA|MASS|WIRLES|ARSE|JAVBE|LAVA|GEDOFT|QEDONI|LOGISTICARE|GUDOYI|CELL|PLEASE CALL|PATEL|RYAN|ALISON|DUGAN|DONALD|SANDRA|COUCH|THEOHARRIS)', '', cleaned, flags=re.IGNORECASE).strip()
        
        # Remove Route ID/Date/Time fragments
        cleaned = re.sub(r'(ERNEST\s*\d*[A-Z]?|KENNEDY\s*\d*[A-Z]?|STEVE\s*\d*[A-Z]?|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}:\d{2}(?:\s*(AM|PM))?)', '', cleaned, flags=re.IGNORECASE).strip()
            
        # Heuristic: Find words that look like a person's name (up to 3 capitalized words)
        name_match = re.match(r'([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+)?)', cleaned)
        if name_match:
            cleaned = name_match.group(0).strip()
        else:
            # Fallback: take the first 1-3 words
            words = cleaned.split()
            cleaned = " ".join(words[:3])

        # Final cleanup
        cleaned = re.sub(r'[,|"\-–—:;]+$', '', cleaned).strip()
        
        # Ensure it contains a decent name (at least two letters and not just an abbreviation or single letter)
        if len(cleaned.split()) < 2 and len(cleaned) < 5:
            return ""

        # Limit length
        return cleaned[:100].rsplit(' ', 1)[0] if len(cleaned) > 100 else cleaned

    def parse_trip_details(self, line):
        driver_token = ""
        time_obj = None
        pickup_info = ""
        dropoff_info = ""
        
        # --- 1. Extract Driver/Route Token (if at the very start) ---
        driver_match = re.match(r'^\s*([A-Z]{2,15}\s*\d{1,2}[A-Z]?)', line)
        if driver_match and self.is_driver_token(driver_match.group(1).split()[0]):
            driver_token = driver_match.group(1).strip()
            line = re.sub(re.escape(driver_token), '', line, 1).strip()
            
        # --- 2. Find and Parse the Time (Trip Anchor) ---
        time_match = re.search(r'(\d{1,2}:\d{2})(?:\s*(AM|PM))?', line, re.IGNORECASE)
        if not time_match:
            return None, "", "", "", ""
            
        time_str = time_match.group(1)
        am_pm = time_match.group(2)
        time_obj = self.parse_time_from_string(line, time_str, am_pm)

        # --- 3. Clean Remaining Text (remove time, date, junk) ---
        remaining_text = line
        remaining_text = remaining_text.replace(time_match.group(0), '', 1).strip()
        remaining_text = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}', '', remaining_text).strip() 
        remaining_text = re.sub(r'\d{4}', '', remaining_text).strip() # Remove years (2025)
        
        # Aggressively remove trailing junk from the *end* to prevent contamination
        junk_patterns_tail = [
            r'\(\d{3}\)\s*\d{3}-\d{4}.*$', # Phone number to end
            r'CELL|PLEASE CALL|GUDOYI|LOGISTICARE.*$', # Notes/IDs to end
        ]
        
        for pattern in junk_patterns_tail:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                remaining_text = remaining_text[:match.start()].strip()
                break

        # --- 4. Separate Client Name and Addresses ---
        
        client_name_raw = remaining_text
        pickup_info = ""
        dropoff_info = ""

        # Heuristic: Addresses start with a number. We need the first two numeric segments.
        address_segments = [p.strip() for p in re.split(r'(\s*\d+\s+[A-Z])', remaining_text, flags=re.IGNORECASE) if p.strip()]

        # Find the index where the first address starts
        first_address_index = -1
        for i, part in enumerate(address_segments):
            if re.match(r'^\d', part.strip()):
                first_address_index = i
                break
        
        if first_address_index != -1:
            # Text before the first address is the Client Name raw section
            client_name_raw = "".join(address_segments[:first_address_index]).strip()
            
            # Addresses and possible remaining junk
            address_junk_text = "".join(address_segments[first_address_index:]).strip()
            
            # Find the boundary between the two addresses (Address 1 ends just before Address 2 starts)
            # Look for the second address starting with a number and a capitalized word (e.g., '4 NOEL' or '22 PARKRIDGE')
            
            # Find the first occurrence of a number followed by a capitalized street name, *after* the initial address number
            second_address_match = re.search(r'(\s*\d+\s+[A-Z][a-z]+)', address_junk_text[5:], re.IGNORECASE)
            
            if second_address_match:
                # Calculate the exact start index of the second address in the original text chunk
                second_address_start_index = second_address_match.start(1) + 5
                
                pickup_candidate = address_junk_text[:second_address_start_index].strip()
                dropoff_candidate = address_junk_text[second_address_start_index:].strip()

                # Confirm split worked: P must start with a number and D must be reasonable
                if re.match(r'^\d', pickup_candidate):
                    pickup_info = pickup_candidate
                    dropoff_info = dropoff_candidate
                    
                    # Clean the dropoff info again, remove any lingering junk
                    dropoff_info = re.sub(r'\s+[A-Z]{3,}\s+\d{1,2}:\d{2}.*$', '', dropoff_info).strip()
                else:
                    # Single address only
                    pickup_info = address_junk_text
            else:
                # Only one address found
                pickup_info = address_junk_text

        # --- 5. Final Client Name Determination and Cleaning ---
        client_name = self.clean_client_name(client_name_raw)

        # Handle the failure case where the client name was incorrectly parsed into the address (e.g., Ernest_3)
        if not client_name and pickup_info:
            # Look for a capitalized name in the very beginning of the pickup info (e.g., 'DUGAN DONALD 22 PARKRIDGE...')
            name_match_in_address = re.match(r'([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)?)', pickup_info)
            if name_match_in_address:
                client_name = name_match_in_address.group(0).strip()
                # Remove the name from the pickup_info
                pickup_info = pickup_info.replace(client_name, '', 1).strip()
                
                # If the pickup info now starts with a number, the extraction was successful
                if not re.match(r'^\d', pickup_info):
                    # Revert: The removal broke the address format, so the name was not there.
                    client_name = ""
                    pickup_info = address_junk_text.strip()
            
        # Final Fallback for client name
        if not client_name:
            client_name = driver_token.replace(' ', '_') if driver_token else "UNKNOWN"

        # --- 6. Cleanup and Truncation ---
        pickup_info = pickup_info[:200].strip().replace('  ', ' ')
        dropoff_info = dropoff_info[:200].strip().replace('  ', ' ')
            
        return time_obj, driver_token.strip(), client_name, pickup_info, dropoff_info

    def parse_schedule_file(self, filepath, template):
        """Parse a schedule text file and create template entries."""
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
        
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        entries_created = 0
        order = 1
        
        for line in lines:
            # The parse_trip_details function returns:
            # time_obj, driver_token, client_name (only name), pickup_address_full, dropoff_address_full
            time_obj, driver_token, client_name, pickup_address_full, dropoff_address_full = self.parse_trip_details(line)
            
            if time_obj:
                # Fallback for client name if parsing failed
                if not client_name or client_name.upper() in ['ERNEST', 'JAVBE', 'KENNEDY', 'STEVE', 'UNKNOWN', '']:
                    if driver_token:
                        client_name = driver_token.replace(' ', '_')
                    else:
                        self.stdout.write(self.style.WARNING(f"  Skipping entry: Could not determine client name for time {time_obj}. Line: {line[:50]}..."))
                        continue

                # --- Data Mapping and Cleanup ---
                
                # 1. Client Name (only the name)
                final_client_name = client_name.title().strip().replace('  ', ' ')[:255]
                
                # 2. Addresses (map full parsed address to address fields)
                final_pickup_address = pickup_address_full.strip().replace('  ', ' ')[:255]
                final_dropoff_address = dropoff_address_full.strip().replace('  ', ' ')[:255]
                
                # 3. Cities: Cannot reliably separate city from the full address with current logic. Setting to blank.
                final_pickup_city = "" 
                final_dropoff_city = "" 
                
                # Create the entry
                ScheduleTemplateEntry.objects.create(
                    template=template,
                    order=order,
                    start_time=time_obj,
                    client_name=final_client_name,
                    driver_name=driver_token.strip()[:100],
                    pickup_address=final_pickup_address,
                    pickup_city=final_pickup_city,
                    dropoff_address=final_dropoff_address,
                    dropoff_city=final_dropoff_city,
                    # Note: other fields like Notes, Client/Drive dropdowns are not populated here
                )
                entries_created += 1
                order += 1
                
        return entries_created
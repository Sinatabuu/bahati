from django.apps import apps
from django.utils.dateparse import parse_time, parse_date

Driver = apps.get_model('scheduler','Driver')
Client = apps.get_model('scheduler','Client')
DailyScheduleTemplate = apps.get_model('scheduler','DailyScheduleTemplate')
AutoSchedule = apps.get_model('scheduler','AutoSchedule')

# Rows from your 9/9 PDF (driver, time, client)
ROWS = [
    ("ERNEST", "08:00", "RYAN C"),
    ("ERNEST", "08:00", "RYAN K"),
    ("ERNEST", "14:00", "DUGAN DONALD"),
    ("ERNEST", "14:00", "JONATHAN THEOHARRIS"),
    ("ERNEST", "14:00", "RYAN C"),
    ("ERNEST", "14:00", "RYAN K"),

    ("GUDOYI", "07:30", "BARRY C"),
    ("GUDOYI", "08:00", "CHARLIE MARJOR"),
    ("GUDOYI", "13:30", "RAUL BARROS"),
    ("GUDOYI", "15:00", "BARRY C"),
    ("GUDOYI", "15:00", "CHARLIE MARJOR"),

    ("SAMMY", "08:00", "MARY CHRONOPOLOUS"),
    ("SAMMY", "09:00", "MARIO"),
    ("SAMMY", "09:30", "TYLER D"),
    ("SAMMY", "11:00", "PATRICIA C"),
    ("SAMMY", "12:30", "RAUL CRUZ"),
    ("SAMMY", "14:00", "MARY CHRONOPOLOUS"),
    ("SAMMY", "14:00", "WILLIAMS DOROTHY"),

    ("STEVE", "08:00", "JONATHAN THEOHARRIS"),
    ("STEVE", "11:00", "PATRICIA C"),
    ("STEVE", "14:30", "TYLER S"),
    ("STEVE", "15:00", "SANDRA C"),
    ("STEVE", "15:30", "PATRICIA C"),
    ("STEVE", "18:00", "TYLER S"),

    ("TONY", "08:00", "KHAW B"),
    ("TONY", "11:00", "ELIZABETH P"),
    ("TONY", "12:00", "KHAW B"),
    ("TONY", "15:45", "KRISTINE S"),
]

def upsert_tuesday_templates(rows):
    made = updated = skipped = 0
    missing_drivers = set()
    conflicts = []  # [(client, time, have_driver, want_driver)]

    for drv_name, tstr, client_name in rows:
        d = Driver.objects.filter(name__iexact=drv_name).first()
        if not d:
            # try a looser match (strip spaces)
            d = Driver.objects.filter(name__iregex=r'^%s$' % drv_name.replace(' ', '')).first()
        if not d:
            missing_drivers.add(drv_name)
            continue

        c, _ = Client.objects.get_or_create(
            name=client_name,
            defaults={"pickup_state":"MA", "dropoff_state":"MA"},
        )
        pt = parse_time(tstr)

        # Check only on the unique key: (day_of_week, client, pickup_time)
        existing = DailyScheduleTemplate.objects.filter(day_of_week='Tue', client=c, pickup_time=pt).first()
        if not existing:
            DailyScheduleTemplate.objects.create(day_of_week='Tue', client=c, pickup_time=pt, driver=d)
            made += 1
        else:
            # If existing has no driver, attach one; else skip/report if different
            if existing.driver_id is None and d:
                existing.driver = d
                existing.save(update_fields=["driver"])
                updated += 1
            elif existing.driver_id and d and existing.driver_id != d.id:
                conflicts.append((c.name, tstr, existing.driver.name if existing.driver else None, d.name))
                skipped += 1
            else:
                skipped += 1

    return made, updated, skipped, sorted(missing_drivers), conflicts

m,u,s,missing,conf = upsert_tuesday_templates(ROWS)
print("Templates: created", m, "| driver-updated", u, "| skipped", s)
print("Missing drivers:", missing)
if conf:
    print("Conflicts (client, time, existing_driver, wanted_driver):")
    for c,t,hd,wd in conf:
        print(" -", c, t, "have:", hd, "want:", wd)

# Now generate for 2025-09-09 from Tue templates
def generate_for(day_str):
    day = parse_date(day_str)
    idx = day.weekday()  # 0..6
    keys = [idx, ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][idx], ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][idx]]
    templates = (DailyScheduleTemplate.objects.filter(day_of_week__in=keys).select_related('client','driver').order_by('pickup_time'))
    fb = Driver.objects.order_by('id').first()
    created = skipped = 0
    for t in templates:
        if AutoSchedule.objects.filter(client=t.client, date=day, pickup_time=t.pickup_time).exists():
            skipped += 1
            continue
        AutoSchedule.objects.create(
            client=t.client,
            driver=t.driver or fb,
            date=day,
            pickup_time=t.pickup_time,
            status='scheduled',
            pickup_address   = t.client.pickup_address or '',
            pickup_city      = t.client.pickup_city or '',
            dropoff_address  = t.client.dropoff_address or '',
            dropoff_city     = t.client.dropoff_city or '',
            start_latitude   = getattr(t.client,'pickup_latitude',None),
            start_longitude  = getattr(t.client,'pickup_longitude',None),
            end_latitude     = getattr(t.client,'dropoff_latitude',None),
            end_longitude    = getattr(t.client,'dropoff_longitude',None),
        )
        created += 1
    return created, skipped

gc, gs = generate_for('2025-09-09')
print("Generated for 2025-09-09:", gc, "created;", gs, "skipped")
from django.utils.dateparse import parse_date as _pd
print("Total rows on 2025-09-09:", AutoSchedule.objects.filter(date=_pd('2025-09-09')).count())

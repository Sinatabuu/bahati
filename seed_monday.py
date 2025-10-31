from django.apps import apps
from django.utils import timezone
import datetime as dt

Driver = apps.get_model('scheduler', 'Driver')
Client = apps.get_model('scheduler', 'Client')
DailyScheduleTemplate = apps.get_model('scheduler', 'DailyScheduleTemplate')

def T(hm: str):
    return dt.datetime.strptime(hm, "%H:%M").time()

def upsert_client(name, home_addr, home_city, program_addr, program_city, notes=""):
    c, _ = Client.objects.get_or_create(name=name)
    # fill in any missing fields (won't overwrite existing non-empty values)
    if not (c.pickup_address or "").strip():  c.pickup_address = home_addr
    if not (c.pickup_city or "").strip():     c.pickup_city = home_city
    if not (c.dropoff_address or "").strip(): c.dropoff_address = program_addr
    if not (c.dropoff_city or "").strip():    c.dropoff_city = program_city
    if notes and not (c.notes or "").strip(): c.notes = notes
    c.save()
    return c

# Ensure these drivers exist
drivers = {name: Driver.objects.get_or_create(name=name)[0] for name in [
    "DAVID","ERNEST","GUDOYI","JOCK","KENNEDY","SAMMY","STEVE","TONY","WILLIAM"
]}

# Subset from today’s sheet — add more following the pattern
rows = [
    ("RAUL BARROS", "116 LEXINGTON STREET", "BILLERICA", "860 EAST STREET", "TEWKSBURY", "08:00", "14:00", "DAVID",   "DAVID",   ""),
    ("RYAN K",      "17 BAYBERRY ROAD",     "DANVERS",   "4 NOEL STREET",  "AMESBURY",   "07:30", "14:30", "ERNEST",  "ERNEST",  ""),
    ("ALLISON",     "789 ROWLEY BRIDGE RD", "TOPSFIELD", "4 NOEL STREET",  "AMESBURY",   "07:00", "14:30", "ERNEST",  "ERNEST",  ""),
    ("BARRY C",     "12 BUCKHILL ROAD",     "TYNGSBORO", "10 OPPORTUNITY WAY","NEWBURYPORT","07:30","14:00","GUDOYI","GUDOYI",""),
    ("CURTIS CALDWELL","116 LEXINGTON STREET","BILLERICA","10 OPPORTUNITY WAY","NEWBURYPORT","08:00","15:00","GUDOYI","GUDOYI",""),
    ("DOROTHY WILLIAMS","5 GARY ROAD","Chelmsford","150 INDUSTRIAL AVE","Lowell","08:30","14:00","SAMMY","TONY",""),
    ("MARY CHRONOPOLOUS","5 GARY ROAD","Chelmsford","150 INDUSTRIAL AVE","Lowell","08:30","14:00","SAMMY","TONY",""),
    ("MICHAEL HARRINGTON","40 Parkhurst Rd","Chelmsford","1 Hospital Dr","Lowell","11:00","14:00","SAMMY","SAMMY","CALL ON ARRIVAL / 4WHLS"),
    ("JULIO C",     "87 HILL STREET",       "LEXINGTON", "24 LYMAN STREET","WESTBOROUGH","08:00","12:00","TONY","TONY",""),
    ("ELIZABETHY P","60 MARSHALL STREET",   "PAXTON",    "25 PLEASANT STREET","WORCESTER","11:00","15:45","TONY","TONY",""),
    ("SANDRA COUCH","6 CAMPONELLI DRIVE","ANDOVER","95 OLD FERRY ROAD","HAVERHILL","15:00","08:50","STEVE","WILLIAM",""),
    ("MATEO S",     "49 TENADEL AVE",       "HAVERHILL", "671 KENOZA STREET","HAVERHILL","11:00","14:00","WILLIAM","WILLIAM",""),
]

def ensure_template(day_value, client, driver, pickup_time):
    DailyScheduleTemplate.objects.get_or_create(
        client=client, driver=driver, day_of_week=day_value, pickup_time=pickup_time
    )

for name, home_a, home_c, prog_a, prog_c, am, pm, d_am, d_pm, notes in rows:
    c = upsert_client(name, home_a, home_c, prog_a, prog_c, notes)
    ensure_template("Mon", c, drivers[d_am], T(am))  # AM
    ensure_template("Mon", c, drivers[d_pm], T(pm))  # PM

print("Done. Mon templates:",
      DailyScheduleTemplate.objects.filter(day_of_week__in=[0,"Mon","Monday"]).count())

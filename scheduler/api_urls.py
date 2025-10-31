from django.urls import path
from . import views

app_name = "scheduler_api"

urlpatterns = [
    # Auth/session JSON
    path("auth/login/",   views.login_api,    name="login_api"),
    path("auth/logout/",  views.logout_api,   name="logout_api"),
    
    path("session/",      views.session_info, name="session"),
    path("me/",           views.me,           name="me"),
    path("whoami/",       views.whoami,       name="whoami"),
    path("service/api/client/<int:pk>/mini/", views.client_mini, name="client_mini"),
    path("service/api/schedule/", views.schedule_api, name="schedule_api"),
    path("service/api/schedule-entries/", views.schedule_api, name="schedule_api"),
    path("service/api/my-schedule", views.my_schedule_api, name="my_schedule_api"),
    path("service/api/my-schedule/", views.my_schedule_api),  # accept with slash too

    # Schedule generation / publish
    path("generate/schedule/",   views.generate_schedule,                  name="generate_schedule_api"),
    path("regenerate/",          views.regenerate_schedule_from_template,  name="regenerate_schedule_from_template"),
    path("schedule/set-status/", views.set_schedule_status,                name="set_schedule_status_api"),

    # Data feeds used by React
    path("schedule-entries/",          views.schedule_entries_json,  name="schedule_entries_json"),   # GET ?date=
    path("schedule-entries.geojson",   views.schedule_entries_geojson, name="schedule_entries_geojson"),
    path("all-schedules.json",         views.all_schedules_json,     name="all_schedules_json"),     # staff
    path("my-schedule.json",           views.my_schedule_json,       name="my_schedule_json"),       # driver

    # Lookups
    path("drivers.json",               views.drivers_json,           name="drivers_json"),
    path("clients.json",               views.clients_json,           name="clients_json"),
    path("daily-templates.json",       views.daily_templates_json,   name="daily_templates_json"),
    path("admin/drivers.json",         views.admin_driver_list,      name="admin_driver_list"),

    # Actions on entries
    path("schedule-entry/",                        views.create_schedule_entry,         name="create_schedule_entry"),  # POST
    path("schedule-entry/<int:entry_id>/fields/",  views.update_schedule_entry_fields,  name="update_schedule_entry_fields"),  # PATCH/POST
    path("schedule-entry/<int:entry_id>/cancel/",  views.cancel_schedule_entry,         name="cancel_schedule_entry"),
    path("schedule-entry/<int:pk>/start/",         views.schedule_entry_start,          name="schedule_entry_start"),
    path("schedule-entry/<int:pk>/set-status/",    views.schedule_entry_set_status,     name="schedule_entry_set_status"),
    path("schedule-entry/reassign/",               views.reassign_schedule_entry_v2,    name="reassign_schedule"),
    path("api/schedule/reassign/",views.reassign_schedule_entry_v2,name="schedule_reassign_v2",),
    path("api/schedule/reassign/", views.reassign_schedule_entry_v2, name="schedule_reassign_v2"),
    path("api/schedule/cancel/", views.cancel_schedule_entry_v2, name="schedule_cancel_v2"),
    # Driver location
    path("driver/ping-location/",     views.driver_ping_location,    name="driver_ping_location"),
    path("driver/locations-latest/",  views.driver_locations_latest, name="driver_locations_latest"),
    path("api/schedule/status/", views.update_schedule_status_api, name="schedule_status_api"),


    # Utilities
    path("rebalance-day/", views.rebalance_day, name="rebalance_day"),
    path("health/",        views.health,        name="health"),
    path("probe/",         views.public_probe,  name="public_probe"),

    
]

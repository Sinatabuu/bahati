from django.urls import path
from . import views

app_name = "scheduler"

urlpatterns = [
    # Auth (HTML screens)
    path("", views.home, name="home"),
    #path("", views.root, name="home"),
    path("login/",  views.user_login,  name="user_login"),
    path("logout/", views.user_logout, name="user_logout"),
    path("home/", views.home, name="home_index"),
    path("admin/ajax/client/<int:pk>/defaults/", views.admin_client_defaults, name="admin_client_defaults"),
    path("schedule/today/", views.schedule_today_page, name="schedule_today_page"),
    path("api/client/<int:pk>/mini/", views.client_mini, name="client_mini"),
    path("api/clients/search/", views.clients_search, name="clients_search"),
    path("api/recommend/driver/", views.recommend_driver, name="recommend_driver"),
    path("api/schedule/reassign/",views.reassign_schedule_entry_v2,name="schedule_reassign_v2",),


    
    
    

    # Screens
    path("driver-dashboard/",   views.driver_dashboard,        name="driver_dashboard"),
    path("generate/",           views.generate_schedule_view,  name="generate"),
    path("schedule-list/",      views.schedule_list,           name="schedule_list"),
    path("daily_schedule/",     views.daily_schedule_sheet,    name="daily_schedule_sheet"),
    path("cancelled-schedules/",views.cancelled_schedule,      name="cancelled_schedule"),
    path("reassign_schedule/", views.reassign_schedule,     name="reassign_schedule"),
    path("driver/ping-location/",     views.driver_ping_location,    name="driver_ping_location"),
    # CRUD pages
    path("add_schedule/", views.add_schedule, name="add_schedule"),
    path("add_driver/",   views.add_driver,   name="add_driver"),
    path("add_client/",   views.add_client,   name="add_client"),
    path("client_list/",  views.client_list,  name="client_list"),
    path("driver_list/",  views.driver_list,  name="driver_list"),

    # Tools / reports (HTML)
    path("suspects/",                           views.suspects_report,       name="suspects_report"),
    path("entry/<int:entry_id>/swap/",          views.entry_swap_endpoints,  name="entry_swap_endpoints"),
    path("entry/<int:entry_id>/mark-reviewed/", views.entry_mark_reviewed,   name="entry_mark_reviewed"),
    path("tools/bulk-swap/",                    views.bulk_swap_coords,      name="bulk_swap_coords"),
    path("generate/schedule/", views.generate_schedule, name="generate_schedule"),
    path("api/schedule/status/", views.update_schedule_status_api, name="schedule_status_api"),

    # Dev/test HTML helpers
    path("dev/status-tester/",   views.dev_status_tester,   name="dev_status_tester"),
    path("dev/reassign-tester/", views.dev_reassign_tester, name="dev_reassign_tester"),
    path("dev/three-day/",       views.dev_three_day,       name="dev_three_day"),
    path("dev/schedule-viewer/", views.dev_schedule_viewer, name="dev_schedule_viewer"),

    # Misc page
    path("map-test/", views.map_test, name="map_test"),


    path("service/session-info/", views.session_info),
    path("service/set-session-probe/", views.set_session_probe),
    path("service/whoami/", views.whoami),
    path("service/driver-dashboard/", views.driver_dashboard, name="driver_dashboard"),
    
    path("csrf/", views.csrf_probe, name="csrf_probe"),
    path("schedule-entries/", views.schedule_entries_json, name="schedule_entries_json"),
    path("set-schedule-status/", views.set_schedule_status, name="set_schedule_status"),

  
    path("api/driver/<int:driver_id>/entries/", views.driver_entries_today, name="driver_entries_today"),
    path("api/entry/<int:entry_id>/cancel/", views.entry_cancel, name="entry_cancel"),
    path("api/entry/<int:entry_id>/reassign/", views.entry_reassign, name="entry_reassign"),
    path("api/schedule/", views.schedule_entries_json, name="api_schedule"),
    path("api/schedule/reassign/", views.reassign_schedule_entry_v2, name="schedule_reassign_v2"),
    path("api/schedule/cancel/", views.cancel_schedule_entry_v2, name="schedule_cancel_v2"),
]








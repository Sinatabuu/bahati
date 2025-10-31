from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from scheduler import views as sviews
from scheduler import views as sched_views


urlpatterns = [
    path("admin/", admin.site.urls),

    # HTML pages (namespace MUST be "scheduler" to satisfy LOGIN_URL/redirects)
    path("service/", include(("scheduler.urls_pages", "scheduler"), namespace="scheduler")),
    

    # JSON API (namespace "scheduler_api")
    path("service/api/", include(("scheduler.api_urls", "scheduler_api"), namespace="scheduler_api")),

    # Optional SPA mount
    path("driver/", TemplateView.as_view(template_name="driver/index.html")),
    re_path(r"^driver/.*$", TemplateView.as_view(template_name="driver/index.html")),

    # Root
    path("", sviews.home, name="root_home"),
    #path("", sched_views.root, name="root_home"),
]

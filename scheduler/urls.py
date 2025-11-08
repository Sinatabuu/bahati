from django.urls import path
from . import views

app_name = "scheduler"

urlpatterns = [
    path("", views.home, name="home"),                      # /service/
    path("login/", views.user_login, name="user_login"),    # /service/login/
    path("dashboard/", views.dashboard, name="dashboard"),  # /service/dashboard/
]

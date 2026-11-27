from django.urls import path
from . import views

app_name = "intake"
urlpatterns = [
    path("", views.apply, name="apply"),
    path("success/", views.success, name="success"),
]

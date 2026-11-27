from django.urls import path
from . import views

app_name = "intake"
urlpatterns = [
    path("apply/", views.apply, name="apply"),
    path("apply/success/", views.success, name="success"),
    path("callback/", views.callback, name="callback"),
    path("callback/success/", views.callback_success, name="callback_success"),
]

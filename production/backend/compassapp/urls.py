"""Strict public routes. Internal admin is blocked at the public reverse proxy."""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include

def health(request):
    return JsonResponse({"ok": True, "service": "compass-backend-v1"})

urlpatterns = [
    path("healthz", health, name="health"),
    path("apply/", include("intake.urls")),
    path("admin/", admin.site.urls),  # SSH tunnel / private ingress ONLY
]

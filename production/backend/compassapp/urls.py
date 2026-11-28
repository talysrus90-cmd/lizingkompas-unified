"""Strict public routes. Internal admin is blocked at the public reverse proxy."""
from django.contrib import admin
from django.http import JsonResponse
from django.db import connection
from django.urls import path, include
from intake.workspace import workspace

def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"ok":False},status=503)
    return JsonResponse({"ok": True, "service": "compass-backend-v1"})

urlpatterns = [
    path("healthz", health, name="health"),
    path("", include("intake.urls")),
    path("admin/workspace/", workspace, name="broker-workspace"),
    path("admin/workspace/<str:section>/", workspace, name="broker-workspace-section"),
    path("admin/", admin.site.urls),  # SSH tunnel / private ingress ONLY
]

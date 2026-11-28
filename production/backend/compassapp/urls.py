"""Strict public routes. Internal admin is blocked at the public reverse proxy."""
from django.contrib import admin
from django.conf import settings
from django.http import JsonResponse
from django.db import connection
from django.urls import path, include
from intake.document_views import original_document
from intake.connect_views import connect_case
from intake.task_views import task_case
from intake.legal_views import legal_case
from intake.schedule_views import quote_schedule
from intake.client_portal import client_status, client_login, client_home, client_logout
from intake.workspace import workspace, create_financial_case, case_workspace, export_financial_cases

def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"ok":False},status=503)
    payload = {"ok": True, "service": "compass-backend-v1"}
    if getattr(settings,"WORKSTATION_MODE",None):
        payload["workspace_mode"] = settings.WORKSTATION_MODE
    return JsonResponse(payload)

urlpatterns = [
    path("healthz", health, name="health"),
    path("", include("intake.urls")),
    path("client/status/",client_status,name="client-status"),
    path("client/login/",client_login,name="client-login"),
    path("client/logout/",client_logout,name="client-logout"),
    path("client/",client_home,name="client-home"),
    path("admin/workspace/", workspace, name="broker-workspace"),
    path("admin/workspace/new/", create_financial_case, name="broker-workspace-new"),
    path("admin/workspace/v/<str:layout>/", workspace, {"section":"home"}, name="broker-variant-home"),
    path("admin/workspace/v/<str:layout>/export/", export_financial_cases, name="broker-variant-export"),
    path("admin/workspace/v/<str:layout>/new/", create_financial_case, name="broker-variant-new"),
    path("admin/workspace/v/<str:layout>/case/<uuid:case_id>/quote/<uuid:quote_id>/original/", original_document, name="broker-original-document"),
    path("admin/workspace/v/<str:layout>/case/<uuid:case_id>/connect/", connect_case, name="broker-connect-case"),
    path("admin/workspace/v/<str:layout>/case/<uuid:case_id>/tasks/", task_case, name="broker-task-case"),
    path("admin/workspace/v/<str:layout>/case/<uuid:case_id>/legal/", legal_case, name="broker-legal-case"),
    path("admin/workspace/v/<str:layout>/case/<uuid:case_id>/quote/<uuid:quote_id>/schedule/", quote_schedule, name="broker-quote-schedule"),
    path("admin/workspace/v/<str:layout>/case/<uuid:case_id>/", case_workspace, name="broker-variant-case"),
    path("admin/workspace/v/<str:layout>/<str:section>/", workspace, name="broker-variant-section"),
    path("admin/workspace/<str:section>/", workspace, name="broker-workspace-section"),
    path("admin/", admin.site.urls),  # SSH tunnel / private ingress ONLY
]

"""Private server-rendered broker workspace. No synthetic rows or client-side API.

All routes are under /admin/, independently blocked by the public process and
Caddy. Existing Django admin implements editing, assignment and quote input.
"""
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache
from .models import Lead, Quote, AuditEvent, CallbackRequest


def allowed(user, permission):
    return user.is_superuser or user.has_perm("intake." + permission)


def scoped_leads(user):
    if not allowed(user, "view_lead") and not allowed(user, "change_lead"):
        return Lead.objects.none()
    qs = Lead.objects.all()
    return qs if user.is_superuser else qs.filter(assigned_to=user)


@admin.site.admin_view
@never_cache
@require_GET
def workspace(request, section="deals"):
    user = request.user
    if not (allowed(user, "view_lead") or allowed(user, "change_lead")):
        raise PermissionDenied
    quote_allowed = allowed(user, "view_quote") or allowed(user, "change_quote")
    audit_allowed = user.is_superuser or allowed(user, "view_auditevent")
    tabs = [
        ("deals", "Сделки"),
        ("analytics", "Аналитика"),
    ]
    if quote_allowed:
        tabs[1:1] = [("offers", "Сравнение КП"), ("documents", "Реестр документов КП")]
    if audit_allowed:
        tabs.append(("security", "Журнал безопасности"))
    if user.is_superuser:
        tabs.append(("callbacks", "Обратные звонки"))
    if section not in {key for key, _ in tabs}:
        raise Http404
    leads = scoped_leads(user)
    quotes = Quote.objects.filter(lead__in=leads) if quote_allowed else Quote.objects.none()
    totals = {
        "leads": leads.count(),
        "active": leads.exclude(stage=Lead.Stage.CLOSED).count(),
        "quotes": quotes.count(),
        "verified": quotes.filter(verified_by_broker=True).count(),
    }
    context = {
        "tabs": tabs, "section": section, "totals": totals,
        "quote_allowed": quote_allowed, "operator": user.is_superuser,
    }
    if section == "deals":
        stage = request.GET.get("stage", "")
        if stage and stage not in Lead.Stage.values:
            raise Http404
        visible = leads.filter(stage=stage) if stage else leads
        context.update(
            stages=Lead.Stage.choices, selected_stage=stage,
            leads=visible.select_related("assigned_to").order_by("-created_at")[:100],
        )
    elif section == "offers":
        context["leads"] = leads.annotate(quote_count=Count("quotes")).order_by("-created_at")[:100]
    elif section == "documents":
        # This is a real source register. Binary originals are not yet stored.
        context["quotes"] = quotes.select_related("lead").order_by("-received_on")[:100]
    elif section == "analytics":
        counts = {x["stage"]: x["n"] for x in leads.values("stage").annotate(n=Count("id"))}
        context["stage_counts"] = [(label, counts.get(key, 0)) for key, label in Lead.Stage.choices]
    elif section == "security":
        context["events"] = AuditEvent.objects.filter(lead__in=leads).select_related("lead").order_by("-at")[:100]
    elif section == "callbacks":
        context["callbacks"] = CallbackRequest.objects.order_by("-created_at")[:100]
    return render(request, "intake/workspace.html", context)

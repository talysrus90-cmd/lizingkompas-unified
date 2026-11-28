"""Private server-rendered broker workspace. No synthetic rows or client-side API.

All routes are under /admin/, independently blocked by the public process and
Caddy. Existing Django admin implements editing, assignment and quote input.
"""
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import Http404
from django.shortcuts import render, redirect
from django import forms
from django.db import transaction
import uuid
from .forms import ASSET_TYPES, VAT_BASES
from django.views.decorators.http import require_GET, require_http_methods
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


class FinancialCaseForm(forms.Form):
    asset_type = forms.ChoiceField(label="Имущество", choices=ASSET_TYPES)
    asset_price = forms.DecimalField(label="Стоимость, ₽", max_digits=14, decimal_places=2, min_value=1)
    advance = forms.DecimalField(label="Аванс, ₽", max_digits=14, decimal_places=2, min_value=0)
    term_months = forms.IntegerField(label="Срок, месяцев", min_value=12, max_value=84)
    vat_basis = forms.ChoiceField(label="НДС", choices=VAT_BASES)

    def clean(self):
        data = super().clean()
        price, advance = data.get("asset_price"), data.get("advance")
        if price is not None and advance is not None and advance >= price:
            self.add_error("advance", "Аванс должен быть меньше стоимости имущества.")
        return data


@admin.site.admin_view
@never_cache
@require_http_methods(["GET", "POST"])
def create_financial_case(request):
    # Internal calculations never assert consent or accept customer contacts.
    if not (allowed(request.user, "add_lead") and
            (allowed(request.user, "view_lead") or allowed(request.user, "change_lead"))):
        raise PermissionDenied
    form = FinancialCaseForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            lead = Lead.objects.create(
                request_key=uuid.uuid4(), source="broker_internal",
                assigned_to=request.user, client_name="", phone="", email="",
                company="", inn="", message="", consent_version="",
                consent_text_sha256="", source_ip_digest="", **form.cleaned_data)
            AuditEvent.objects.create(lead=lead,action="lead.internal_created",
                actor=str(request.user.pk),details="financial_only")
        return redirect("admin:intake_lead_change", lead.pk)
    return render(request,"intake/financial_case.html",{"form":form})

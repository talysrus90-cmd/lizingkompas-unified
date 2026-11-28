"""Private server-rendered broker workspace. No synthetic rows or client-side API.

All routes are under /admin/, independently blocked by the public process and
Caddy. Existing Django admin implements editing, assignment and quote input.
"""
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
import re
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
        ("actions", "Рабочий день"),
        ("deals", "Сделки"),
        ("analytics", "Аналитика"),
    ]
    if quote_allowed:
        tabs[2:2] = [("offers", "Сравнение КП"), ("documents", "Реестр документов КП")]
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
    # Derived work queue, always scoped to authorized, unfinished cases.
    active = leads.exclude(stage=Lead.Stage.CLOSED)
    active_quotes = quotes.filter(lead__in=active)
    today = timezone.localdate()
    deadline = today + timedelta(days=7)
    quote_filters = {
        "expired": active_quotes.filter(valid_until__lt=today),
        "expiring": active_quotes.filter(valid_until__gte=today, valid_until__lte=deadline),
        "unverified": active_quotes.filter(verified_by_broker=False),
    }
    new = active.filter(stage=Lead.Stage.NEW)
    no_quotes = active.annotate(n_quotes=Count("quotes")).filter(n_quotes=0) if quote_allowed else active.none()
    context.update(
        new_count=new.count(), quote_allowed=quote_allowed, today=today,
        no_quotes_count=no_quotes.count() if quote_allowed else 0,
        expiring_count=quote_filters["expiring"].count(),
        expired_count=quote_filters["expired"].count(),
        unverified_count=quote_filters["unverified"].count(),
        callback_count=CallbackRequest.objects.filter(stage=CallbackRequest.Stage.NEW).count() if user.is_superuser else 0,
    )
    if section == "actions":
        context.update(
            new_cases=new.order_by("-created_at")[:20],
            urgent_quotes=active_quotes.filter(valid_until__lte=deadline).select_related("lead").order_by("valid_until","pk")[:30],
        )
    elif section == "deals":
        stage = request.GET.get("stage", "")
        asset = request.GET.get("asset", "")
        number = request.GET.get("number", "").strip()
        work = request.GET.get("work", "")
        if stage and stage not in Lead.Stage.values:
            raise Http404
        if asset and asset not in dict(ASSET_TYPES):
            raise Http404
        if number and not re.fullmatch(r"[0-9a-fA-F]{8}|[0-9a-fA-F-]{36}", number):
            number = ""
        if work not in ("", "no_quotes") or (work and not quote_allowed):
            raise Http404
        visible = no_quotes if work == "no_quotes" else leads
        if stage:
            visible = visible.filter(stage=stage)
        if asset:
            visible = visible.filter(asset_type=asset)
        if number:
            if len(number) == 8:
                visible = visible.filter(id__istartswith=number)
            else:
                try:
                    visible = visible.filter(pk=uuid.UUID(number))
                except ValueError:
                    visible = visible.none()
        page = Paginator(visible.select_related("assigned_to").order_by("-created_at","pk"), 40).get_page(request.GET.get("page"))
        context.update(
            stages=Lead.Stage.choices, selected_stage=stage, asset_types=ASSET_TYPES,
            selected_asset=asset, selected_number=number, selected_work=work,
            leads=page.object_list, page=page,
        )
    elif section == "offers":
        context["leads"] = leads.annotate(quote_count=Count("quotes")).order_by("-created_at")[:100]
    elif section == "documents":
        # This is a real source register. Binary originals are not yet stored.
        state = request.GET.get("state", "")
        if state and state not in quote_filters:
            raise Http404
        context["quote_state"] = state
        context["quotes"] = (quote_filters[state] if state else quotes).select_related("lead").order_by("valid_until","pk")[:100]
    elif section == "analytics":
        counts = {x["stage"]: x["n"] for x in leads.values("stage").annotate(n=Count("id"))}
        context["stage_counts"] = [(label, counts.get(key, 0)) for key, label in Lead.Stage.choices]
    elif section == "security":
        context["events"] = AuditEvent.objects.filter(lead__in=leads).select_related("lead").order_by("-at")[:100]
    elif section == "callbacks":
        callback_state = request.GET.get("state", "")
        if callback_state and callback_state not in CallbackRequest.Stage.values:
            raise Http404
        callbacks = CallbackRequest.objects.all()
        if callback_state:
            callbacks = callbacks.filter(stage=callback_state)
        context["callback_state"] = callback_state
        context["callbacks"] = callbacks.order_by("-created_at","pk")[:100]
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

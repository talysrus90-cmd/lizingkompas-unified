"""Private server-rendered broker workspace. No synthetic rows or client-side API.

All routes are under /admin/, independently blocked by the public process and
Caddy. Existing Django admin implements editing, assignment and quote input.
"""
from django.contrib import admin
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum, Q
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
import re
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import IntegrityError
from .quote_analysis import analyse_quotes
from django import forms
from django.db import transaction
import uuid
import csv
from .forms import ASSET_TYPES, VAT_BASES
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.cache import never_cache
from .models import Lead, Quote, AuditEvent, CallbackRequest, LenderRequest, BrokerTask, DeliveryConfirmation


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
def workspace(request, section="deals", layout=None):
    design = layout_context(layout)
    if section == "home":
        section = {"classic":"deals", "focus":"actions", "route":"deals"}[design["layout"]]
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
    if design["layout"] == "route" and quote_allowed:
        tabs.insert(4, ("partners", "Лизингодатели"))
    connect_allowed=allowed(user,"view_lenderrequest") or allowed(user,"change_lenderrequest")
    if connect_allowed and design["explicit_layout"]:
        tabs.append(("connect","Запросы лизингодателям"))
    task_allowed=(allowed(user,"view_brokertask") or allowed(user,"change_brokertask")) and design["explicit_layout"]
    if task_allowed:
        tabs.append(("tasks","Задачи"))
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
        "active": leads.exclude(stage=Lead.Stage.CLOSED).filter(delivery_confirmation__isnull=True).count(),
        "delivered": leads.filter(source="site",delivery_confirmation__isnull=False).count(),
        "delivered_internal": leads.filter(source="broker_internal",delivery_confirmation__isnull=False).count(),
        "quotes": quotes.count(),
        "verified": quotes.filter(verified_by_broker=True).count(),
    }
    context = {
        **design, "tabs": tabs, "section": section, "totals": totals,
        "quote_allowed": quote_allowed, "operator": user.is_superuser,
    }
    # Derived work queue, always scoped to authorized, unfinished cases.
    active = leads.exclude(stage=Lead.Stage.CLOSED).filter(delivery_confirmation__isnull=True)
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
    pending_requests=LenderRequest.objects.filter(lead__in=active,state__in=["sent","review"]) if connect_allowed else LenderRequest.objects.none()
    overdue_requests=pending_requests.filter(due_on__lt=today)
    context.update(connect_allowed=connect_allowed and design["explicit_layout"],overdue_request_count=overdue_requests.count())
    open_tasks=BrokerTask.objects.filter(lead__in=leads,state="open") if task_allowed else BrokerTask.objects.none()
    context.update(task_allowed=task_allowed,task_overdue=open_tasks.filter(due_on__lt=today).count(),task_today=open_tasks.filter(due_on=today).count())
    if section == "tasks":
        selected=request.GET.get("state","")
        if selected not in ("","overdue","today",*BrokerTask.State.values): raise Http404
        items=BrokerTask.objects.filter(lead__in=leads)
        if selected=="overdue": items=open_tasks.filter(due_on__lt=today)
        elif selected=="today": items=open_tasks.filter(due_on=today)
        elif selected: items=items.filter(state=selected)
        context.update(task_page=Paginator(items.select_related("lead__assigned_to").order_by("due_on","priority","pk"),40).get_page(request.GET.get("page")),task_state=selected)
    elif section == "connect":
        selected=request.GET.get("state","")
        if selected not in ("","overdue",*LenderRequest.State.values): raise Http404
        items=LenderRequest.objects.filter(lead__in=leads)
        if selected=="overdue": items=overdue_requests
        elif selected: items=items.filter(state=selected)
        context.update(request_states=LenderRequest.State.choices,selected_request_state=selected,request_page=Paginator(items.select_related("lead").order_by("-created_at","pk"),40).get_page(request.GET.get("page")))
    elif section == "actions":
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
        invalid_number = bool(number and not re.fullmatch(r"[0-9a-fA-F]{8}|[0-9a-fA-F-]{36}", number))
        if work not in ("", "no_quotes") or (work and not quote_allowed):
            raise Http404
        visible = no_quotes if work == "no_quotes" else leads
        if stage:
            visible = visible.filter(stage=stage)
        if asset:
            visible = visible.filter(asset_type=asset)
        if invalid_number:
            visible = visible.none()
        elif number:
            if len(number) == 8:
                visible = visible.filter(id__istartswith=number)
            else:
                try:
                    visible = visible.filter(pk=uuid.UUID(number))
                except ValueError:
                    visible = visible.none()
        page = Paginator(visible.select_related("assigned_to").order_by("-created_at","pk"), 40).get_page(request.GET.get("page"))
        if design["layout"] == "route":
            page_items = list(page.object_list)
            context["lanes"] = [(key,label,[item for item in page_items if item.stage == key]) for key,label in Lead.Stage.choices]
        context.update(
            stages=Lead.Stage.choices, selected_stage=stage, asset_types=ASSET_TYPES,
            selected_asset=asset, selected_number=number[:36], selected_work=work,
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
    elif section == "partners":
        context["partners"] = quotes.values("lessor_name").annotate(
            offer_count=Count("id"), deal_count=Count("lead",distinct=True),
            verified_count=Count("id",filter=Q(verified_by_broker=True)),
            expired_count=Count("id",filter=Q(valid_until__lt=today)),
        ).order_by("-offer_count","lessor_name")[:100]
    elif section == "analytics":
        context["stage_amounts"] = [(label, leads.filter(stage=key).aggregate(total=Sum("asset_price"))["total"] or 0) for key,label in Lead.Stage.choices]
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
    if section == "deals" and design["layout"] == "route":
        context["portfolio_amount"] = visible.aggregate(total=Sum("asset_price"))["total"] or 0
        context["stage_totals"] = {row["stage"]:row["n"] for row in visible.values("stage").annotate(n=Count("id"))}
        context["lanes"] = [(key,label,items,context["stage_totals"].get(key,0)) for key,label,items in context["lanes"]]
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
def create_financial_case(request, layout=None):
    design = layout_context(layout)
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
        if layout is not None:
            return redirect("broker-variant-case", layout=layout, case_id=lead.pk)
        return redirect("admin:intake_lead_change", lead.pk)
    return render(request,"intake/financial_case.html",{"form":form, **design})


LAYOUTS = (("classic", "A · Классика"), ("focus", "B · Рабочий центр"), ("route", "C · Максимум"))


def layout_context(layout):
    if layout is not None and layout not in dict(LAYOUTS):
        raise Http404
    selected = layout or "classic"
    prefix = reverse("broker-variant-home", kwargs={"layout":selected}) if layout else reverse("broker-workspace")
    return {"layout":selected,"layouts":LAYOUTS,"layout_name":dict(LAYOUTS)[selected],
            "workspace_prefix":prefix,"explicit_layout":layout is not None}


class WorkspaceQuoteForm(forms.ModelForm):
    scenario_confirmed = forms.BooleanField(label="Условия сверены с оригиналом КП")
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for key in ("quoted_asset_price","quoted_advance","quoted_term_months","quoted_vat_basis"):
            self.fields[key].required=True
    class Meta:
        model = Quote
        fields = ("lessor_name","offer_id","source_document_id","received_on","valid_until",
                  "quoted_asset_price","quoted_advance","quoted_term_months","quoted_vat_basis",
                  "monthly_payment","buyout","upfront_fee","recurring_monthly_fee","insurance_total",
                  "other_costs","verified_by_broker")
        widgets = {"received_on":forms.DateInput(attrs={"type":"date"}),
                   "valid_until":forms.DateInput(attrs={"type":"date"})}
        labels = {"lessor_name":"Лизингодатель","offer_id":"Номер КП","source_document_id":"Идентификатор источника",
                  "received_on":"Получено","valid_until":"Действует до","monthly_payment":"Платёж в месяц, ₽",
                  "buyout":"Выкуп, ₽","upfront_fee":"Разовая комиссия, ₽","recurring_monthly_fee":"Комиссия в месяц, ₽",
                  "insurance_total":"Страхование за срок, ₽","other_costs":"Прочие расходы, ₽",
                  "verified_by_broker":"Оригинал проверен брокером"}

    def clean(self):
        values=super().clean()
        start,end=values.get("received_on"),values.get("valid_until")
        if start and end and end < start:
            self.add_error("valid_until","Срок действия не может быть раньше даты получения.")
        if start and start > timezone.localdate():
            self.add_error("received_on","Дата получения не может быть в будущем.")
        for key in ("monthly_payment","buyout","upfront_fee","recurring_monthly_fee","insurance_total","other_costs"):
            value=values.get(key)
            if value is not None and value < 0:
                self.add_error(key,"Сумма не может быть отрицательной.")
        return values


class DeliveryForm(forms.Form):
    delivered_on=forms.DateField(label="Дата фактической выдачи имущества",widget=forms.DateInput(attrs={"type":"date"}))
    evidence_sha256=forms.RegexField(regex=r"\\A[0-9a-f]{64}\\Z",max_length=64,label="SHA-256 подтверждающего документа")
    confirmed=forms.BooleanField(label="Подтверждаю фактическую передачу имущества по оригиналу документа")
    def clean_delivered_on(self):
        value=self.cleaned_data["delivered_on"]
        if value>timezone.localdate():
            raise forms.ValidationError("Дата выдачи не может быть в будущем.")
        return value


class StageForm(forms.Form):
    stage = forms.ChoiceField(label="Этап сделки",choices=Lead.Stage.choices)
    previous_stage = forms.ChoiceField(choices=Lead.Stage.choices,widget=forms.HiddenInput)


@admin.site.admin_view
@never_cache
@require_http_methods(["GET","POST"])
def case_workspace(request, layout, case_id):
    design=layout_context(layout)
    user=request.user
    lead=get_object_or_404(scoped_leads(user),pk=case_id)
    quote_allowed=allowed(user,"view_quote") or allowed(user,"change_quote")
    can_add=quote_allowed and allowed(user,"add_quote")
    can_stage=allowed(user,"change_lead")
    quote_form=WorkspaceQuoteForm()
    stage_form=StageForm(initial={"stage":lead.stage,"previous_stage":lead.stage})
    delivery=DeliveryConfirmation.objects.filter(lead=lead).first()
    can_deliver=can_stage and allowed(user,"add_deliveryconfirmation") and delivery is None
    delivery_form=DeliveryForm(initial={"delivered_on":timezone.localdate()})
    status=200
    if request.method=="POST":
        action=request.POST.get("action")
        if action=="delivery":
            if not (can_stage and allowed(user,"add_deliveryconfirmation")): raise PermissionDenied
            delivery_form=DeliveryForm(request.POST)
            if delivery_form.is_valid():
                with transaction.atomic():
                    locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=lead.pk)
                    if DeliveryConfirmation.objects.filter(lead=locked).exists():
                        delivery_form.add_error(None,"Выдача уже зарегистрирована. Обновите страницу.")
                        status=409
                    else:
                        data=delivery_form.cleaned_data
                        record=DeliveryConfirmation.objects.create(lead=locked,delivered_on=data["delivered_on"],evidence_sha256=data["evidence_sha256"],confirmed_by=user)
                        old=locked.stage
                        locked.stage=Lead.Stage.CLOSED
                        locked.save(update_fields=["stage","updated_at"])
                        AuditEvent.objects.create(lead=locked,action="lead.delivery_confirmed",actor=str(user.pk),details=str(record.pk)+" "+str(record.delivered_on))
                        if old!=locked.stage:
                            AuditEvent.objects.create(lead=locked,action="lead.stage_changed",actor=str(user.pk),details=old+" -> "+locked.stage)
                        return redirect("broker-variant-case",layout=layout,case_id=lead.pk)
        elif action=="stage":
            if not can_stage: raise PermissionDenied
            stage_form=StageForm(request.POST)
            if stage_form.is_valid():
                with transaction.atomic():
                    locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=case_id)
                    if locked.stage!=stage_form.cleaned_data["previous_stage"]:
                        stage_form.add_error(None,"Этап уже изменился. Обновите карточку.")
                        status=409
                    elif DeliveryConfirmation.objects.filter(lead=locked).exists() and stage_form.cleaned_data["stage"]!=Lead.Stage.CLOSED:
                        stage_form.add_error(None,"После подтверждения выдачи этап нельзя менять здесь.")
                        status=409
                    elif locked.stage!=stage_form.cleaned_data["stage"]:
                        old=locked.stage
                        locked.stage=stage_form.cleaned_data["stage"]
                        locked.save(update_fields=["stage","updated_at"])
                        AuditEvent.objects.create(lead=locked,action="lead.stage_changed",actor=str(user.pk),details=old+" -> "+locked.stage)
                if status==200:
                    return redirect("broker-variant-case",layout=layout,case_id=case_id)
        elif action=="quote":
            if not can_add: raise PermissionDenied
            quote_form=WorkspaceQuoteForm(request.POST)
            if quote_form.is_valid():
                try:
                    with transaction.atomic():
                        locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=case_id)
                        if locked.stage==Lead.Stage.CLOSED or locked.quotes.count()>=20:
                            quote_form.add_error(None,"Сделка закрыта или достигнут лимит 20 КП.")
                        elif locked.quotes.filter(offer_id=quote_form.cleaned_data["offer_id"]).exists() or locked.quotes.filter(source_document_id=quote_form.cleaned_data["source_document_id"]).exists():
                            quote_form.add_error(None,"Номер или источник КП уже зарегистрирован.")
                        else:
                            q=quote_form.save(commit=False)
                            q.lead=locked
                            q.save()
                            AuditEvent.objects.create(lead=locked,action="offer.added",actor=str(user.pk),details=q.offer_id[:64])
                            return redirect("broker-variant-case",layout=layout,case_id=case_id)
                except IntegrityError:
                    quote_form.add_error(None,"Не удалось сохранить: проверьте уникальность номера и источника.")
        else:
            raise Http404
    quotes=list(lead.quotes.all()) if quote_allowed else []
    rows=[]
    message=""
    if quote_allowed:
        if not quotes:
            message="Предложений пока нет."
        else:
            try:
                rows, count=analyse_quotes(lead,quotes,timezone.localdate())
                if count<2: message="Недостаточно проверенных сопоставимых КП для общего рейтинга."
            except ValueError:
                message="Условия предложений требуют проверки."
    events=lead.audit_events.order_by("-at")[:30] if allowed(user,"view_auditevent") else []
    from .case_control import case_signals
    signals=case_signals(lead,layout,timezone.localdate(),quotes=quotes,rows=rows,quote_allowed=quote_allowed,
        tasks_allowed=allowed(user,"view_brokertask") or allowed(user,"change_brokertask"),
        connect_allowed=allowed(user,"view_lenderrequest") or allowed(user,"change_lenderrequest"),
        legal_allowed=allowed(user,"view_contractreview") or allowed(user,"change_contractreview"))
    return render(request,"intake/case_workspace.html",{**design,"lead":lead,
        "asset_label":dict(ASSET_TYPES).get(lead.asset_type,lead.asset_type),
        "signals":signals,"delivery":delivery,"can_deliver":can_deliver,"delivery_form":delivery_form,
        "stages":Lead.Stage.choices,"quotes":quotes,"rows":rows,"message":message,
        "can_add":can_add and lead.stage!=Lead.Stage.CLOSED,"can_stage":can_stage and delivery is None,
        "quote_allowed":quote_allowed,"quote_form":quote_form,"stage_form":stage_form,"events":events,
        "legal_allowed":allowed(user,"view_contractreview") or allowed(user,"change_contractreview"),
        "task_allowed":allowed(user,"view_brokertask") or allowed(user,"change_brokertask"),
        "connect_allowed":allowed(user,"view_lenderrequest") or allowed(user,"change_lenderrequest"),
        "vault_enabled":settings.DOCUMENT_VAULT_ENABLED and lead.source!="broker_internal" and allowed(user,"view_originaldocument")},status=status)


@admin.site.admin_view
@never_cache
@require_GET
def export_financial_cases(request, layout):
    if layout != "route":
        raise Http404
    if not (allowed(request.user,"view_lead") or allowed(request.user,"change_lead")):
        raise PermissionDenied
    # Deliberately omit contact fields, usernames and free text. Only financial
    # cases created internally, never public client applications.
    qs=scoped_leads(request.user).filter(source="broker_internal").order_by("created_at","pk")
    response=HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"]='attachment; filename="compass-financial-cases.csv"'
    response.write("\ufeff")
    writer=csv.writer(response,delimiter=";")
    writer.writerow(["Номер","Имущество","Стоимость, руб.","Аванс, руб.","Срок, мес.","НДС","Этап"])
    for lead in qs.iterator():
        writer.writerow([str(lead.pk),dict(ASSET_TYPES).get(lead.asset_type,"Другое имущество"),
            lead.asset_price,lead.advance,lead.term_months,dict(VAT_BASES).get(lead.vat_basis,"Не указан"),
            lead.get_stage_display()])
    return response

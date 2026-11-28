"""Explicit cashflow entry, confirmation and scoped review in all layouts."""
import hashlib
import json
from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from broker.payment_schedule import parse_schedule, schedule_total, format_schedule, quote_fingerprint, checked_schedule
from .models import Lead, Quote, AuditEvent
from .workspace import allowed, scoped_leads, layout_context

def revision(quote):
    return hashlib.sha256(json.dumps(quote.payment_schedule,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class ScheduleForm(forms.Form):
    schedule=forms.CharField(label="График платежей",max_length=32000,widget=forms.Textarea(attrs={"rows":12,"spellcheck":"false"}))
    complete=forms.BooleanField(label="Сверено с оригиналом: перечислены все выплаты, без повторного учёта аванса, выкупа, комиссий и иных расходов")
    fingerprint=forms.CharField(widget=forms.HiddenInput,max_length=64)
    revision=forms.CharField(widget=forms.HiddenInput,max_length=64)

@admin.site.admin_view
@never_cache
@require_http_methods(["GET","POST"])
def quote_schedule(request,layout,case_id,quote_id):
    design=layout_context(layout)
    user=request.user
    if not (allowed(user,"view_quote") or allowed(user,"change_quote")):
        raise PermissionDenied
    lead=get_object_or_404(scoped_leads(user),pk=case_id)
    quote=get_object_or_404(Quote,pk=quote_id,lead=lead)
    can_edit=allowed(user,"change_quote") and allowed(user,"change_lead") and lead.stage!=Lead.Stage.CLOSED
    raw=quote.payment_schedule if isinstance(quote.payment_schedule,dict) else {}
    initial={"schedule":raw.get("text",""),"fingerprint":quote_fingerprint(quote),"revision":revision(quote)}
    form=ScheduleForm(initial=initial)
    status=200
    if request.method=="POST":
        if not can_edit: raise PermissionDenied
        form=ScheduleForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=lead.pk)
                q=get_object_or_404(Quote.objects.select_for_update(),pk=quote.pk,lead=locked)
                if locked.stage==Lead.Stage.CLOSED: raise PermissionDenied
                if form.cleaned_data["fingerprint"]!=quote_fingerprint(q) or form.cleaned_data["revision"]!=revision(q):
                    form.add_error(None,"КП или график изменились. Обновите страницу.")
                    status=409
                else:
                    try:
                        if q.source_scenario() is None or not q.verified_by_broker:
                            raise ValueError("Сначала подтвердите исходные условия и оригинал КП.")
                        entries=parse_schedule(form.cleaned_data["schedule"])
                        schedule_total(entries,q.quoted_advance)
                    except ValueError as exc:
                        form.add_error("schedule",str(exc))
                    else:
                        q.payment_schedule={"text":format_schedule(entries),"fingerprint":quote_fingerprint(q)}
                        q.save(update_fields=["payment_schedule"])
                        AuditEvent.objects.create(lead=locked,action="quote.schedule_confirmed",actor=str(user.pk),details=str(q.pk))
                        return redirect("broker-quote-schedule",layout=layout,case_id=lead.pk,quote_id=q.pk)
    total=None
    warning=""
    if quote.payment_schedule:
        try:
            total=checked_schedule(quote)
        except (ValueError,TypeError,KeyError):
            warning="График требует повторной сверки."
    return render(request,"intake/quote_schedule.html",{**design,"lead":lead,"quote":quote,"form":form,"can_edit":can_edit,"total":total,"warning":warning},status=status)

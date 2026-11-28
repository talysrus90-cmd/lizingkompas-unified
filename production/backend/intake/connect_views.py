"""Private lender request tracking. Never sends an application externally."""
import unicodedata
from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import Lead, Quote, AuditEvent, LenderRequest
from .workspace import allowed, scoped_leads, layout_context

S = LenderRequest.State
TRANSITIONS = {
    S.DRAFT: (S.SENT,S.CANCELLED),
    S.SENT: (S.REVIEW,S.OFFER,S.DECLINED,S.CANCELLED),
    S.REVIEW: (S.OFFER,S.DECLINED,S.CANCELLED),
    S.OFFER: (), S.DECLINED: (), S.CANCELLED: (),
}


def lender_key(name):
    return " ".join(unicodedata.normalize("NFKC",name).casefold().split())


class CreateRequestForm(forms.Form):
    lessor_name = forms.CharField(label="Лизинговая компания",max_length=160)
    due_on = forms.DateField(label="Ожидаемый ответ до",required=False,widget=forms.DateInput(attrs={"type":"date"}))
    def clean_lessor_name(self):
        name=self.cleaned_data["lessor_name"].strip()
        key=lender_key(name)
        if not key or len(key)>320 or any(unicodedata.category(c).startswith("C") for c in name):
            raise forms.ValidationError("Некорректное название.")
        return name
    def clean_due_on(self):
        value=self.cleaned_data["due_on"]
        if value and value < timezone.localdate():
            raise forms.ValidationError("Укажите сегодняшнюю или будущую дату.")
        return value


class UpdateRequestForm(forms.Form):
    state = forms.ChoiceField(label="Следующий статус")
    version = forms.IntegerField(min_value=0,widget=forms.HiddenInput)
    quote = forms.ModelChoiceField(label="Полученное КП",queryset=Quote.objects.none(),required=False)
    sent_confirmed = forms.BooleanField(label="Подтверждаю фактическую отправку вне Компаса",required=False)
    def __init__(self,*args,item,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["state"].choices=[(x,x.label) for x in TRANSITIONS[S(item.state)]]
        self.fields["quote"].queryset=Quote.objects.filter(lead=item.lead,lender_request__isnull=True)
    def clean(self):
        data=super().clean()
        state=data.get("state")
        quote=data.get("quote")
        if state==S.SENT and not data.get("sent_confirmed"):
            self.add_error("sent_confirmed","Подтвердите отправку, выполненную самостоятельно.")
        if state==S.OFFER and not quote:
            self.add_error("quote","Выберите зарегистрированное КП.")
        elif state!=S.OFFER and quote:
            self.add_error("quote","КП указывается только при получении предложения.")
        return data


def can_read(user):
    return allowed(user,"view_lenderrequest") or allowed(user,"change_lenderrequest")


@admin.site.admin_view
@never_cache
@require_http_methods(["GET","POST"])
def connect_case(request,layout,case_id):
    design=layout_context(layout)
    user=request.user
    if not can_read(user):
        raise PermissionDenied
    lead=get_object_or_404(scoped_leads(user),pk=case_id)
    can_create=allowed(user,"add_lenderrequest") and allowed(user,"change_lead") and lead.stage!=Lead.Stage.CLOSED
    can_update=allowed(user,"change_lenderrequest") and allowed(user,"change_lead") and lead.stage!=Lead.Stage.CLOSED
    create=CreateRequestForm()
    bound=None
    bound_id=None
    status=200
    if request.method=="POST":
        action=request.POST.get("action")
        if action=="create":
            if not can_create: raise PermissionDenied
            create=CreateRequestForm(request.POST)
            if create.is_valid():
                try:
                    with transaction.atomic():
                        locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=lead.pk)
                        if locked.stage==Lead.Stage.CLOSED: raise PermissionDenied
                        if locked.lender_requests.count()>=50:
                            create.add_error(None,"Достигнут лимит 50 запросов по сделке.")
                        else:
                            item=LenderRequest.objects.create(lead=locked,lessor_key=lender_key(create.cleaned_data["lessor_name"]),**create.cleaned_data)
                            AuditEvent.objects.create(lead=locked,action="lender_request.created",actor=str(user.pk),details=str(item.pk))
                            return redirect("broker-connect-case",layout=layout,case_id=lead.pk)
                except IntegrityError:
                    create.add_error("lessor_name","Запрос этому лизингодателю уже существует.")
        elif action=="update":
            if not can_update: raise PermissionDenied
            import uuid
            try: bound_id=uuid.UUID(request.POST.get("request_id",""))
            except ValueError: raise Http404
            with transaction.atomic():
                locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=lead.pk)
                if locked.stage==Lead.Stage.CLOSED: raise PermissionDenied
                item=get_object_or_404(LenderRequest.objects.select_for_update(),pk=bound_id,lead=locked)
                bound=UpdateRequestForm(request.POST,item=item)
                if request.POST.get("version")!=str(item.version):
                    bound.is_valid()
                    bound.add_error(None,"Запись изменилась. Обновите страницу.")
                    status=409
                elif bound.is_valid():
                    state=bound.cleaned_data["state"]
                    quote=bound.cleaned_data["quote"]
                    if quote and not (allowed(user,"view_quote") or allowed(user,"change_quote")):
                        raise PermissionDenied
                    if quote and lender_key(quote.lessor_name)!=item.lessor_key:
                        bound.add_error("quote","Лизингодатель в КП не совпадает.")
                    else:
                        old=item.state
                        item.state=state
                        item.version+=1
                        if state==S.SENT: item.sent_at=timezone.now()
                        if state in (S.OFFER,S.DECLINED): item.responded_at=timezone.now()
                        if quote: item.quote=quote
                        item.save()
                        AuditEvent.objects.create(lead=locked,action="lender_request.changed",actor=str(user.pk),details=str(item.pk)+" "+old+" -> "+state)
                        return redirect("broker-connect-case",layout=layout,case_id=lead.pk)
        else:
            raise Http404
    items=list(lead.lender_requests.select_related("quote"))
    rows=[]
    for item in items:
        form=None
        if can_update and TRANSITIONS[S(item.state)]:
            form=bound if item.pk==bound_id else UpdateRequestForm(item=item,initial={"version":item.version})
            if not (allowed(user,"view_quote") or allowed(user,"change_quote")):
                form.fields["quote"].queryset=Quote.objects.none()
                form.fields["state"].choices=[(v,l) for v,l in form.fields["state"].choices if v!=S.OFFER]
        rows.append((item,form))
    return render(request,"intake/connect_case.html",{**design,"lead":lead,"rows":rows,"create":create,
        "can_create":can_create,"today":timezone.localdate()},status=status)

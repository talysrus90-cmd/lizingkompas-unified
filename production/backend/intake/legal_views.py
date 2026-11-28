"""Manual evidence-oriented contract checklist. No automated legal opinion."""
import re
import uuid
from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction, IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import ContractReview, ContractReviewItem, Lead, AuditEvent
from .workspace import allowed, scoped_leads, layout_context

# Stable identifiers: never change the meaning of an existing version.
TOPICS = (
    ("asset","Предмет лизинга и идентификация имущества"),
    ("price","Стоимость, аванс, платежи и выкуп"),
    ("schedule","График, даты и порядок зачёта платежей"),
    ("changes","Одностороннее изменение платежей и условий"),
    ("fees","Дополнительные комиссии и расходы"),
    ("delivery","Передача имущества и риск случайной гибели"),
    ("insurance","Страхование, исключения и страховое возмещение"),
    ("maintenance","Обслуживание, эксплуатация и ограничения"),
    ("default","Просрочка, неустойки и основания нарушения"),
    ("termination","Расторжение, возврат и изъятие имущества"),
    ("settlement","Расчёты при досрочном прекращении"),
    ("buyout","Досрочный выкуп и переход собственности"),
    ("disputes","Уведомления, претензии и разрешение споров"),
    ("annexes","Приложения, общие условия и приоритет документов"),
)
class CreateReviewForm(forms.Form):
    source_sha256=forms.CharField(label="SHA-256 проверяемой редакции",min_length=64,max_length=64)
    def clean_source_sha256(self):
        value=self.cleaned_data["source_sha256"].lower()
        if not re.fullmatch(r"[0-9a-f]{64}",value):
            raise forms.ValidationError("Нужен SHA-256 оригинального файла (64 шестнадцатеричных символа).")
        return value

class FindingForm(forms.Form):
    state=forms.ChoiceField(label="Результат проверки",choices=ContractReviewItem.State.choices)
    page=forms.IntegerField(label="Страница оригинала (для найденного условия)",min_value=1,max_value=10000,required=False)
    version=forms.IntegerField(min_value=0,widget=forms.HiddenInput)
    def clean(self):
        data=super().clean()
        state=data.get("state")
        page=data.get("page")
        if state in ("ok","risk") and page is None:
            self.add_error("page","Укажите страницу проверенного условия.")
        if state in ("unknown","missing") and page is not None:
            self.add_error("page","Не указывайте страницу, если условие не проверено или не найдено.")
        return data

def can_read(user):
    return allowed(user,"view_contractreview") or allowed(user,"change_contractreview")

@admin.site.admin_view
@never_cache
@require_http_methods(["GET","POST"])
def legal_case(request,layout,case_id):
    design=layout_context(layout)
    user=request.user
    if not can_read(user): raise PermissionDenied
    lead=get_object_or_404(scoped_leads(user),pk=case_id)
    can_create=allowed(user,"add_contractreview") and allowed(user,"add_contractreviewitem") and allowed(user,"change_lead")
    can_edit=allowed(user,"change_contractreviewitem") and allowed(user,"change_lead")
    create=CreateReviewForm()
    bound=None
    bound_id=None
    status=200
    chosen=request.GET.get("review")
    reviews=lead.contract_reviews.all()
    review=reviews.first()
    if chosen:
        try: selected=uuid.UUID(chosen)
        except ValueError: raise Http404
        review=get_object_or_404(reviews,pk=selected)
    def back(r):
        from django.urls import reverse
        return redirect(reverse("broker-legal-case",args=[layout,lead.pk])+"?review="+str(r.pk))
    if request.method=="POST":
        action=request.POST.get("action")
        if action=="create":
            if not can_create: raise PermissionDenied
            create=CreateReviewForm(request.POST)
            if create.is_valid():
                try:
                    with transaction.atomic():
                        locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=lead.pk)
                        if locked.contract_reviews.count()>=50:
                            create.add_error(None,"Достигнут лимит 50 редакций по сделке.")
                        else:
                            r=ContractReview.objects.create(lead=locked,source_sha256=create.cleaned_data["source_sha256"])
                            ContractReviewItem.objects.bulk_create([ContractReviewItem(review=r,topic=key) for key,_ in TOPICS])
                            AuditEvent.objects.create(lead=locked,action="legal.review_created",actor=str(user.pk),details=str(r.pk))
                            return back(r)
                except IntegrityError:
                    create.add_error("source_sha256","Эта редакция уже зарегистрирована.")
        elif action=="update":
            if not can_edit: raise PermissionDenied
            if review is None: raise Http404
            try: bound_id=int(request.POST.get("item_id",""))
            except ValueError: raise Http404
            if not 0<bound_id<2**63: raise Http404
            bound=FindingForm(request.POST)
            with transaction.atomic():
                locked=get_object_or_404(scoped_leads(user).select_for_update(),pk=lead.pk)
                item=get_object_or_404(ContractReviewItem.objects.select_for_update(),pk=bound_id,review=review,review__lead=locked)
                if request.POST.get("version")!=str(item.version):
                    bound.is_valid()
                    bound.add_error(None,"Запись изменилась. Обновите страницу.")
                    status=409
                elif bound.is_valid():
                    item.state=bound.cleaned_data["state"]
                    item.page=bound.cleaned_data["page"]
                    item.reviewed_by=user if item.state!="unknown" else None
                    item.reviewed_at=timezone.now() if item.state!="unknown" else None
                    item.version+=1
                    item.save()
                    AuditEvent.objects.create(lead=locked,action="legal.finding_changed",actor=str(user.pk),details=str(review.pk)+" "+item.topic+" "+item.state)
                    return back(review)
        else: raise Http404
    rows=[]
    counts={key:0 for key in ContractReviewItem.State.values}
    if review:
        items={item.topic:item for item in review.items.all()}
        for key,label in TOPICS:
            item=items.get(key)
            if item is None:
                counts["unknown"]+=1
                rows.append((label,None,None))
                continue
            counts[item.state]+=1
            form=(bound if item.pk==bound_id else FindingForm(initial={"state":item.state,"page":item.page,"version":item.version})) if can_edit else None
            rows.append((label,item,form))
    return render(request,"intake/legal_case.html",{**design,"lead":lead,"reviews":reviews,"review":review,"rows":rows,"counts":counts,"create":create,"can_create":can_create},status=status)

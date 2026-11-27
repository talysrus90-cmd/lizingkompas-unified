"""Back-office workflow, reachable via SSH tunnel ONLY (public /admin is 404)."""
import uuid
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from broker.offer_comparison import Scenario, Offer, compare_offers
from datetime import date
from .models import Lead, Quote, AuditEvent, CallbackRequest

class QuoteInline(admin.TabularInline):
    model = Quote
    extra = 0
    max_num = 20
    fields = (
        "offer_id", "lessor_name", "source_document_id", "received_on", "valid_until",
        "verified_by_broker", "monthly_payment", "buyout", "upfront_fee",
        "recurring_monthly_fee", "insurance_total", "other_costs",
    )

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("created_at","short_id","asset_type","asset_price","stage","comparison_link")
    list_filter = ("stage","asset_type")
    list_per_page = 40
    ordering = ("-created_at",)
    readonly_fields = (
        "id", "request_key","created_at","updated_at","consent_version",
        "consent_text_sha256","consent_at","source_ip_digest","source",
    )
    fieldsets = [
        ("Карточка", {"fields":("id","stage","asset_type","asset_price","advance",
                                  "term_months","vat_basis","created_at")}),
        ("Контакты — персональные данные", {"fields":("client_name","phone","email",
                                                      "company","inn","message")}),
        ("Доказательство согласия", {"fields":("consent_version","consent_text_sha256",
                "consent_at","source_ip_digest","request_key","source","updated_at")}),
    ]
    inlines = [QuoteInline]

    def short_id(self,obj):
        return str(obj.pk)[:8]
    short_id.short_description = "№ заявки"

    def comparison_link(self,obj):
        uri=reverse("admin:intake_lead_compare",args=(obj.pk,))
        return format_html('<a href="{}">Сравнить КП</a>',uri)
    comparison_link.short_description = "КП"

    def has_add_permission(self,request):
        # Contacts only via consented applicant flow, not typed directly by staff.
        return False

    def has_delete_permission(self,request,obj=None):
        # Deletion by controlled retention/erasure workflow, not casual admin click.
        return False

    def save_model(self,request,obj,form,change):
        previous = Lead.objects.get(pk=obj.pk).stage if change else ""
        super().save_model(request,obj,form,change)
        if change and previous != obj.stage:
            AuditEvent.objects.create(
                lead=obj,action="lead.stage_changed",actor=str(request.user.pk),
                details=previous+" -> "+obj.stage
            )

    def save_formset(self,request,form,formset,change):
        """Audit every quote added, updated or removed in the private CRM.

        No source PDF or customer contact is inserted into the audit details.
        The Django admin change transaction wraps this action atomically.
        """
        if formset.model is Quote:
            quotes=formset.save(commit=False)
            for item in formset.deleted_objects:
                offer_id=item.offer_id
                item.delete()
                AuditEvent.objects.create(
                    lead=form.instance,action="offer.deleted",
                    actor=str(request.user.pk),details=offer_id[:64]
                )
            for item in quotes:
                was_new=item._state.adding
                item.save()
                AuditEvent.objects.create(
                    lead=form.instance,
                    action="offer.added" if was_new else "offer.changed",
                    actor=str(request.user.pk),details=item.offer_id[:64],
                )
            formset.save_m2m()
        else:
            super().save_formset(request,form,formset,change)

    def get_urls(self):
        urls=super().get_urls()
        custom=[path("<uuid:object_id>/compare/",self.admin_site.admin_view(self.compare_view),
                     name="intake_lead_compare")]
        return custom+urls

    def compare_view(self,request,object_id):
        if not self.has_view_permission(request):
            raise PermissionDenied
        lead=get_object_or_404(Lead,pk=object_id)
        sources=list(lead.quotes.all())
        rows=[]
        message=None
        if not 2<=len(sources)<=20:
            message="Для сравнения необходимо от 2 до 20 исходных КП."
        else:
            try:
                scenario=Scenario(
                    lead.asset_price,lead.advance,lead.term_months,lead.vat_basis
                )
                quotes=[
                    Offer(
                        offer_id=o.offer_id,lessor=o.lessor_name,
                        source_document_id=o.source_document_id,
                        received_on=o.received_on,valid_until=o.valid_until,
                        scenario=scenario,verified_by_broker=o.verified_by_broker,
                        monthly_payment=o.monthly_payment,buyout=o.buyout,
                        upfront_fee=o.upfront_fee,recurring_monthly_fee=o.recurring_monthly_fee,
                        insurance_total=o.insurance_total,other_costs=o.other_costs,
                    ) for o in sources
                ]
                results=compare_offers(scenario,quotes,as_of=date.today())
                rows=results.rows
                if results.comparable_count<2:
                    message="Недостаточно двух сопоставимых проверенных КП; рейтинг скрыт."
            except ValueError:
                message="Условия хотя бы одного КП недопустимы. Исправьте источник и суммы."
        return render(request,"intake/compare.html",{
            **self.admin_site.each_context(request),
            "lead":lead,"rows":rows,"message":message,
            "title":"Сравнение КП по заявке "+str(lead.pk)[:8],
            "opts":self.model._meta,
        })

@admin.register(AuditEvent)
class AuditAdmin(admin.ModelAdmin):
    list_display=("at","lead","action","actor","details")
    readonly_fields=("lead","at","action","actor","details")
    list_filter=("action",)
    def has_add_permission(self,request):
        return False
    def has_change_permission(self,request,obj=None):
        return False
    def has_delete_permission(self,request,obj=None):
        return False

admin.site.site_header="Лизинг Компас — закрытая CRM"
admin.site.site_title="Лизинг Компас"
admin.site.index_title="Операторские заявки"

@admin.register(CallbackRequest)
class CallbackRequestAdmin(admin.ModelAdmin):
    """Restricted operator follow-up view. No public access."""
    list_display=("created_at","short_id","stage")
    list_filter=("stage",)
    ordering=("-created_at",)
    readonly_fields=("id","request_key","created_at","consent_version",
                     "consent_text_sha256","consent_at","source_ip_digest","name","phone")
    fields=("id","stage","created_at","name","phone","consent_version",
            "consent_text_sha256","consent_at","source_ip_digest","request_key")
    list_per_page=40
    def short_id(self,obj):
        return str(obj.pk)[:8]
    short_id.short_description="Номер обращения"
    def has_add_permission(self,request):
        return False
    def has_delete_permission(self,request,obj=None):
        return False

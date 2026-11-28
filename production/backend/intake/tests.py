"""Integration tests for production intake gates, encrypted storage and staff CRM.

Uses synthetic leads ONLY and the test database. Does not send anything by email.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import User, Permission
from django.db import connection
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .forms import ApplicationForm
from .models import Lead, Quote, SubmissionAttempt, AuditEvent, CallbackRequest

CIPHER_KEY = Fernet.generate_key().decode("ascii")
APPROVED = {
    "LIVE_INTAKE": True,
    "OPERATOR_NAME": "ИП Лизинг Компас (синтетический тест)",
    "OPERATOR_INN": "231207234403",
    "CONSENT_VERSION": "qa-consent-v1",
    "DATA_ENCRYPTION_KEYS": [CIPHER_KEY],
    "THROTTLE_SECRET": "test-only-random-hmac-key-no-personal-data",
}
F = {
    "client_name":"Тестовый Контакт",
    "phone":"8 900 123-45-67",
    "email":"synthetic@example.test",
    "company":"Синтетический покупатель",
    "inn":"",
    "asset_type":"equipment",
    "asset_price":"4500000.00",
    "advance":"900000.00",
    "term_months":"36",
    "vat_basis":"included",
    "message":"Только синтетические параметры.",
    "consent":"on",
    "website":"",
}

@override_settings(SSH_OPERATOR=True, **APPROVED)
class IntakeTests(TestCase):
    def setUp(self):
        self.client=Client(enforce_csrf_checks=True)

    def form_payload(self):
        response=self.client.get("/apply/")
        self.assertEqual(response.status_code,200)
        self.assertIn("default-src 'none'",response["Content-Security-Policy"])
        self.assertIn("no-store",response["Cache-Control"])
        payload={**F,"request_key":str(self.client.session["apply_nonce"])}
        csrf=self.client.cookies["csrftoken"].value
        return payload, {"HTTP_X_CSRFTOKEN":csrf}

    def test_public_process_blocks_admin_even_for_authenticated_staff(self):
        operator = User.objects.create_superuser(
            "public-test-operator", "operator@example.test", "synthetic-test-secret-2026"
        )
        self.client.force_login(operator)
        with override_settings(SSH_OPERATOR=False):
            for url in ("/admin", "/admin/", "/admin/login/",
                        "/admin/intake/lead/", "/admin/intake/callbackrequest/"):
                with self.subTest(url=url):
                    response = self.client.get(url, HTTP_X_FORWARDED_FOR="127.0.0.1",
                                               HTTP_X_COMPASS_SSH_OPERATOR="1")
                    self.assertEqual(response.status_code, 404)
                    self.assertIn("no-store", response["Cache-Control"])
                    self.assertEqual(self.client.post(url, {}).status_code, 404)
            self.assertEqual(self.client.get("/apply/").status_code, 200)
            response = self.client.get("/callback/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_disabled_intake_returns_503_without_form(self):
        with override_settings(LIVE_INTAKE=False):
            response=self.client.get("/apply/")
            self.assertEqual(response.status_code,503)
            self.assertNotIn("client_name",response.content.decode())

    def test_requires_csrf_and_separate_consent(self):
        data,headers=self.form_payload()
        response=self.client.post("/apply/",data)
        self.assertEqual(response.status_code,403)
        data["consent"]=""
        response=self.client.post("/apply/",data,**headers)
        self.assertEqual(response.status_code,400)
        self.assertEqual(Lead.objects.count(),0)

    def test_encrypted_customer_data_and_consent_evidence(self):
        data,headers=self.form_payload()
        response=self.client.post("/apply/",data,**headers)
        self.assertEqual(response.status_code,302)
        self.assertEqual(response["Location"],"/apply/success/")
        self.assertEqual(Lead.objects.count(),1)
        lead=Lead.objects.get()
        self.assertEqual(lead.phone,"+79001234567")
        self.assertEqual(lead.client_name,"Тестовый Контакт")
        self.assertEqual(lead.consent_version,"qa-consent-v1")
        self.assertEqual(len(lead.consent_text_sha256),64)
        self.assertEqual(len(lead.source_ip_digest),64)
        self.assertEqual(AuditEvent.objects.count(),1)
        with connection.cursor() as cursor:
            cursor.execute("SELECT client_name,phone,message FROM intake_lead LIMIT 1")
            raw=cursor.fetchone()
        self.assertTrue(all(v.startswith("enc:v1:") for v in raw))
        self.assertNotIn("Контакт",str(raw))
        self.assertNotIn("79001234567",str(raw))
        response=self.client.get("/apply/success/")
        self.assertEqual(response.status_code,200)
        response=self.client.get("/apply/success/")
        self.assertEqual(response.status_code,302)

    def test_invalid_money_inn_and_honeypot_are_rejected(self):
        for changes in [
            {"advance":"99999999"}, {"term_months":"1"},
            {"inn":"123x456"}, {"website":"spam.example"},
            {"phone":"12121"}, {"asset_price":"NaN"},
        ]:
            with self.subTest(changes=changes):
                payload,headers=self.form_payload()
                response=self.client.post("/apply/",{**payload,**changes},**headers)
                self.assertEqual(response.status_code,400)
                self.assertEqual(Lead.objects.count(),0)
                SubmissionAttempt.objects.all().delete()

    def test_rate_limit_applies_to_invalid_attempts(self):
        for n in range(5):
            data,headers=self.form_payload()
            data["consent"]=""
            self.assertEqual(self.client.post("/apply/",data,**headers).status_code,400)
        data,headers=self.form_payload()
        self.assertEqual(self.client.post("/apply/",data,**headers).status_code,429)
        self.assertEqual(Lead.objects.count(),0)

    def test_callback_phone_encrypted_with_independent_consent(self):
        response=self.client.get("/callback/")
        self.assertEqual(response.status_code,200)
        nonce=str(self.client.session["callback_nonce"])
        csrf=self.client.cookies["csrftoken"].value
        record={
            "request_key":nonce,
            "name":"Условный посетитель",
            "phone":"+7 (900) 123-45-67",
            "consent":"on",
            "website":"",
        }
        self.assertEqual(self.client.post("/callback/",record).status_code,403)
        response=self.client.post("/callback/",record,HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code,302)
        self.assertEqual(response["Location"],"/callback/success/")
        self.assertEqual(CallbackRequest.objects.count(),1)
        cb=CallbackRequest.objects.get()
        self.assertEqual(cb.phone,"+79001234567")
        self.assertEqual(cb.consent_version,"qa-consent-v1")
        self.assertEqual(len(cb.consent_text_sha256),64)
        self.assertEqual(len(cb.source_ip_digest),64)
        with connection.cursor() as cursor:
            cursor.execute("SELECT name,phone FROM intake_callbackrequest LIMIT 1")
            values=cursor.fetchone()
        self.assertTrue(all(v.startswith("enc:v1:") for v in values))
        self.assertNotIn("Условный посетитель",str(values))
        self.assertNotIn("79001234567",str(values))
        self.assertEqual(self.client.get("/callback/success/").status_code,200)
        self.assertEqual(self.client.get("/callback/success/").status_code,302)

    def test_callback_consent_required_and_starts_disabled(self):
        with override_settings(LIVE_INTAKE=False):
            self.assertEqual(self.client.get("/callback/").status_code,503)
        self.assertEqual(CallbackRequest.objects.count(),0)
        self.client.get("/callback/")
        nonce=str(self.client.session["callback_nonce"])
        csrf=self.client.cookies["csrftoken"].value
        invalid={"request_key":nonce,"name":"Тест","phone":"9001234567",
                 "consent":"","website":""}
        self.assertEqual(
            self.client.post("/callback/",invalid,HTTP_X_CSRFTOKEN=csrf).status_code,400
        )
        self.assertEqual(CallbackRequest.objects.count(),0)

    def test_broker_must_be_assigned_to_access_lead_even_with_model_permission(self):
        payload,headers=self.form_payload()
        self.assertEqual(self.client.post("/apply/",payload,**headers).status_code,302)
        owned=Lead.objects.get()
        # Create a second synthetic case without any real name or contact.
        other=Lead.objects.get(pk=owned.pk)
        other.pk=uuid.uuid4()
        other.request_key=uuid.uuid4()
        other.save(force_insert=True)
        broker=User.objects.create_user(
            username="broker-synthetic",password="test-only-not-a-real-secret",
            is_staff=True,
        )
        broker.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="intake",
            codename__in=("view_lead","change_lead","view_quote","change_quote",
                          "view_callbackrequest"),
        ))
        owned.assigned_to=broker
        owned.save(update_fields=["assigned_to"])
        self.client.force_login(broker)
        listing=self.client.get("/admin/intake/lead/")
        self.assertEqual(listing.status_code,200)
        self.assertContains(listing,str(owned.pk)[:8])
        # Staff should not be able to enumerate unrelated case objects.
        other_url=reverse("admin:intake_lead_compare",args=[other.pk])
        own_url=reverse("admin:intake_lead_compare",args=[owned.pk])
        self.assertEqual(self.client.get(other_url).status_code,404)
        own_result=self.client.get(own_url)
        self.assertEqual(own_result.status_code,200)
        self.assertNotContains(listing,str(other.pk)[:8],status_code=200)
        self.assertNotEqual(
            self.client.get("/admin/intake/callbackrequest/").status_code,200
        )

    def test_staff_only_comparison_and_metadata_audit(self):
        payload,headers=self.form_payload()
        self.client.post("/apply/",payload,**headers)
        lead=Lead.objects.get()
        today=date.today()
        for i,monthly in ((1,"120000"),(2,"110000")):
            Quote.objects.create(
                lead=lead,offer_id=f"offer-{i:03d}",
                source_document_id=f"doc-{i:03d}",
                lessor_name=f"Синтетическая компания {i}",
                received_on=today,valid_until=today+timedelta(days=20),
                verified_by_broker=True,
                quoted_asset_price=lead.asset_price,quoted_advance=lead.advance,
                quoted_term_months=lead.term_months,quoted_vat_basis=lead.vat_basis,
                monthly_payment=Decimal(monthly),buyout=Decimal(1000),
                upfront_fee=Decimal(5000),recurring_monthly_fee=Decimal(500),
                insurance_total=Decimal(30000),other_costs=Decimal(0),
            )
        endpoint=reverse("admin:intake_lead_compare",args=[lead.pk])
        self.assertEqual(self.client.get(endpoint).status_code,302)
        user=User.objects.create_superuser(
            "test-operator","operator@example.test","synthetic-test-operator-secret-2026"
        )
        self.client.force_login(user)
        response=self.client.get(endpoint)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"Синтетическая компания 2")
        self.assertContains(response,"4914000")
        self.assertEqual(AuditEvent.objects.count(),1)


    def test_real_workspace_navigation_and_empty_database(self):
        endpoint="/admin/workspace/"
        self.assertEqual(self.client.get(endpoint).status_code,302)
        user=User.objects.create_superuser(
            "workspace-test", "workspace@example.test", "synthetic-test-password-2026")
        self.client.force_login(user)
        for section in ("deals","offers","documents","analytics","security","callbacks"):
            url=endpoint+section+"/"
            response=self.client.get(url)
            self.assertEqual(response.status_code,200,section)
            self.assertContains(response,'aria-current="page"')
            self.assertNotContains(response,"DEMO-001")
            self.assertEqual(response.context["totals"]["leads"],0)
            with override_settings(SSH_OPERATOR=False):
                self.assertEqual(self.client.get(url).status_code,404)

    def test_real_workspace_uses_database_and_isolates_other_brokers(self):
        payload,headers=self.form_payload()
        self.assertEqual(self.client.post("/apply/",payload,**headers).status_code,302)
        lead=Lead.objects.get()
        user=User.objects.create_user("workspace-broker",password="synthetic-test-password-2026",is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="intake",
            codename__in=("view_lead","view_quote","view_auditevent")))
        lead.assigned_to=user
        lead.save(update_fields=["assigned_to"])
        other=Lead.objects.get(pk=lead.pk)
        other.pk=uuid.uuid4()
        other.request_key=uuid.uuid4()
        other.assigned_to=None
        other.save(force_insert=True)
        today=date.today()
        for case,source in ((lead,"OWN-SOURCE-1"),(other,"OTHER-SOURCE-2")):
            Quote.objects.create(lead=case,offer_id="offer-1",source_document_id=source,
                lessor_name="QA company",received_on=today,valid_until=today+timedelta(days=5),
                verified_by_broker=True,monthly_payment=Decimal(1000),buyout=Decimal(0),
                upfront_fee=Decimal(0),recurring_monthly_fee=Decimal(0),
                insurance_total=Decimal(0),other_costs=Decimal(0))
        AuditEvent.objects.create(lead=other,action="other.hidden",actor="qa")
        self.client.force_login(user)
        root="/admin/workspace/"
        for section in ("deals","offers","documents","analytics","security"):
            response=self.client.get(root+section+"/")
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.context["totals"],{"leads":1,"active":1,"quotes":1,"verified":1})
        docs=self.client.get(root+"documents/")
        self.assertContains(docs,"OWN-SOURCE-1")
        self.assertNotContains(docs,"OTHER-SOURCE-2")
        audit=self.client.get(root+"security/")
        self.assertNotContains(audit,"other.hidden")
        self.assertEqual(self.client.get(root+"callbacks/").status_code,404)
        self.assertNotContains(self.client.get("/admin/intake/auditevent/"),"other.hidden")
        user.user_permissions.remove(*Permission.objects.filter(
            content_type__app_label="intake",codename="view_quote"))
        self.assertEqual(self.client.get(root+"documents/").status_code,404)
        self.assertEqual(self.client.get(reverse("admin:intake_lead_compare",args=[lead.pk])).status_code,403)


    def test_financial_case_is_persisted_without_personal_data_or_consent_claim(self):
        user=User.objects.create_superuser(
            "financial-test", "financial@example.test", "synthetic-test-password-2026")
        self.client.force_login(user)
        url="/admin/workspace/new/"
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        csrf=self.client.cookies["csrftoken"].value
        data={"asset_type":"equipment","asset_price":"1000000","advance":"200000",
              "term_months":"36","vat_basis":"included","client_name":"must-not-be-saved"}
        self.assertEqual(self.client.post(url,data).status_code,403)
        response=self.client.post(url,data,HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code,302)
        lead=Lead.objects.get()
        self.assertEqual(lead.source,"broker_internal")
        self.assertEqual(lead.assigned_to,user)
        self.assertEqual(lead.client_name,"")
        self.assertEqual(lead.phone,"")
        self.assertEqual(lead.consent_version,"")
        self.assertEqual(lead.consent_text_sha256,"")
        self.assertEqual(AuditEvent.objects.get().action,"lead.internal_created")
        self.assertContains(self.client.get("/admin/workspace/deals/"),"Внутренний расчёт")
        self.assertEqual(self.client.get(response["Location"]).status_code,200)
        with override_settings(SSH_OPERATOR=False):
            self.assertEqual(self.client.get(url).status_code,404)
        invalid={**data,"advance":"1000000"}
        self.assertEqual(self.client.post(url,invalid,HTTP_X_CSRFTOKEN=csrf).status_code,200)
        self.assertEqual(Lead.objects.count(),1)


    def test_action_center_deadlines_scope_filters_and_pagination(self):
        from django.utils import timezone
        user=User.objects.create_superuser("daily-test","daily@example.test","synthetic-test-password-2026")
        self.client.force_login(user)
        url="/admin/workspace/new/"
        self.client.get(url)
        csrf=self.client.cookies["csrftoken"].value
        data={"asset_type":"equipment","asset_price":"1000000","advance":"200000","term_months":"36","vat_basis":"included"}
        for _ in range(3):
            self.assertEqual(self.client.post(url,data,HTTP_X_CSRFTOKEN=csrf).status_code,302)
        a,b,closed=list(Lead.objects.order_by("created_at"))
        closed.stage=Lead.Stage.CLOSED
        closed.save(update_fields=["stage"])
        today=timezone.localdate()
        for case,key,offset,verified in ((a,"expired",-1,True),(a,"soon",7,False),(a,"later",8,True),(closed,"closed-expired",-3,False)):
            Quote.objects.create(lead=case,offer_id=key,source_document_id=key,
                lessor_name="QA company",received_on=today-timedelta(days=10),
                valid_until=today+timedelta(days=offset),verified_by_broker=verified)
        root="/admin/workspace/"
        r=self.client.get(root+"actions/")
        self.assertEqual(r.status_code,200)
        for key,value in (("new_count",2),("no_quotes_count",1),("expired_count",1),("expiring_count",1),("unverified_count",1)):
            self.assertEqual(r.context[key],value,key)
        self.assertNotContains(r,"closed-expired")
        self.assertContains(r,"soon")
        r=self.client.get(root+"deals/",{"work":"no_quotes"})
        self.assertEqual(list(r.context["leads"]),[b])
        r=self.client.get(root+"deals/",{"number":str(a.pk)[:8],"asset":"equipment"})
        self.assertEqual(list(r.context["leads"]),[a])
        self.assertEqual(self.client.get(root+"deals/",{"number":"bad"}).context["page"].paginator.count,0)
        Lead.objects.bulk_create([Lead(request_key=uuid.uuid4(),source="broker_internal",assigned_to=user,client_name="",phone="",email="",company="",inn="",message="",consent_version="",consent_text_sha256="",source_ip_digest="",asset_type="equipment",asset_price=1000000,advance=200000,term_months=36,vat_basis="included") for _ in range(41)])
        r=self.client.get(root+"deals/",{"page":2,"asset":"equipment"})
        self.assertEqual(r.context["page"].number,2)
        self.assertEqual(r.context["page"].paginator.count,44)
        self.assertEqual(len(r.context["leads"]),4)
        r=self.client.get(root+"documents/",{"state":"expired"})
        self.assertEqual([q.offer_id for q in r.context["quotes"]],["expired"])
        self.assertEqual(self.client.get(root+"documents/",{"state":"unknown"}).status_code,404)
        broker=User.objects.create_user("daily-broker",password="synthetic-test-password-2026",is_staff=True)
        broker.user_permissions.add(*Permission.objects.filter(content_type__app_label="intake",codename__in=("view_lead","view_quote")))
        b.assigned_to=broker
        b.save(update_fields=["assigned_to"])
        self.client.force_login(broker)
        r=self.client.get(root+"actions/")
        self.assertEqual(r.context["new_count"],1)
        self.assertEqual(r.context["expired_count"],0)
        self.assertEqual(r.context["no_quotes_count"],1)
        self.assertNotContains(r,"QA company")
        self.assertEqual(self.client.get(root+"callbacks/").status_code,404)
        with override_settings(SSH_OPERATOR=False):
            self.assertEqual(self.client.get(root+"actions/").status_code,404)


    def test_three_variants_share_real_case_and_quote_operations(self):
        from django.utils import timezone
        user=User.objects.create_superuser("variant-test","variant@example.test","synthetic-test-password-2026")
        self.client.force_login(user)
        root="/admin/workspace/v/"
        for layout in ("classic","focus","route"):
            for section in ("","deals/","actions/","offers/","documents/","analytics/","security/","callbacks/"):
                response=self.client.get(root+layout+"/"+section)
                self.assertEqual(response.status_code,200,(layout,section))
                self.assertContains(response,"design-"+layout)
            self.assertEqual(self.client.get(root+layout+"/new/").status_code,200)
        self.assertEqual(self.client.get(root+"bad/").status_code,404)
        self.client.get(root+"classic/new/")
        csrf=self.client.cookies["csrftoken"].value
        data={"asset_type":"equipment","asset_price":"1000000","advance":"200000","term_months":"36","vat_basis":"included"}
        r=self.client.post(root+"classic/new/",data,HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(r.status_code,302)
        lead=Lead.objects.get()
        today=timezone.localdate()
        quote={"action":"quote","lessor_name":"QA company","offer_id":"QA-1","source_document_id":"source-1","received_on":str(today),"valid_until":str(today+timedelta(days=7)),"monthly_payment":"30000","buyout":"1000","upfront_fee":"0","recurring_monthly_fee":"0","insurance_total":"0","other_costs":"0","verified_by_broker":"on","scenario_confirmed":"on","quoted_asset_price":"1000000","quoted_advance":"200000","quoted_term_months":"36","quoted_vat_basis":"included"}
        def case(layout):
            return root+layout+"/case/"+str(lead.pk)+"/"
        self.assertEqual(self.client.post(case("focus"),quote,HTTP_X_CSRFTOKEN=csrf).status_code,302)
        self.assertEqual(self.client.post(case("route"),{**quote,"offer_id":"QA-2","source_document_id":"source-2","monthly_payment":"31000"},HTTP_X_CSRFTOKEN=csrf).status_code,302)
        self.assertEqual(Quote.objects.count(),2)
        for layout in ("classic","focus","route"):
            response=self.client.get(case(layout))
            self.assertEqual(response.status_code,200)
            self.assertEqual(len(response.context["rows"]),2)
            self.assertContains(response,"QA company")
        self.assertEqual(self.client.post(case("route"),{"action":"stage","stage":"quotes","previous_stage":"new"},HTTP_X_CSRFTOKEN=csrf).status_code,302)
        lead.refresh_from_db()
        self.assertEqual(lead.stage,"quotes")
        self.assertEqual(self.client.post(case("classic"),{"action":"stage","stage":"review","previous_stage":"new"},HTTP_X_CSRFTOKEN=csrf).status_code,409)
        self.assertEqual(self.client.get(root+"route/partners/").context["partners"][0]["offer_count"],2)
        self.assertContains(self.client.get(root+"route/export/"),str(lead.pk))
        self.assertEqual(self.client.get(root+"focus/export/").status_code,404)
        self.assertEqual(self.client.post(case("focus"),quote,HTTP_X_CSRFTOKEN=csrf).status_code,200)
        self.assertEqual(Quote.objects.count(),2)
        self.assertEqual(self.client.post(case("focus"),{**quote,"offer_id":"QA-3","source_document_id":"source-3","scenario_confirmed":""},HTTP_X_CSRFTOKEN=csrf).status_code,200)
        self.assertEqual(Quote.objects.count(),2)
        stranger=User.objects.create_user("variant-stranger",password="synthetic-test-password-2026",is_staff=True)
        stranger.user_permissions.add(*Permission.objects.filter(content_type__app_label="intake",codename__in=("view_lead","view_quote")))
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(case("route")).status_code,404)
        self.assertNotContains(self.client.get(root+"route/export/"),str(lead.pk))
        self.assertEqual(len(self.client.get(root+"route/partners/").context["partners"]),0)
        with override_settings(SSH_OPERATOR=False):
            self.assertEqual(self.client.get(root+"route/").status_code,404)


    def test_original_quote_terms_and_different_scenarios_never_share_rank(self):
        from django.utils import timezone
        from .quote_analysis import analyse_quotes
        user=User.objects.create_superuser("quote-terms-test","terms@example.test","synthetic-test-password-2026")
        self.client.force_login(user)
        root="/admin/workspace/v/"
        self.client.get(root+"route/new/")
        csrf=self.client.cookies["csrftoken"].value
        self.assertEqual(self.client.post(root+"route/new/",{"asset_type":"equipment","asset_price":"1000000","advance":"200000","term_months":"36","vat_basis":"included"},HTTP_X_CSRFTOKEN=csrf).status_code,302)
        lead=Lead.objects.get()
        today=timezone.localdate()
        url=root+"route/case/"+str(lead.pk)+"/"
        base={"action":"quote","lessor_name":"QA Finance","offer_id":"QA-001","source_document_id":"DOC-001","received_on":str(today),"valid_until":str(today+timedelta(days=7)),"monthly_payment":"30000","buyout":"1000","upfront_fee":"0","recurring_monthly_fee":"0","insurance_total":"0","other_costs":"0","verified_by_broker":"on","scenario_confirmed":"on","quoted_asset_price":"1000000","quoted_advance":"200000","quoted_term_months":"36","quoted_vat_basis":"included"}
        for changes in ({},{"offer_id":"QA-002","source_document_id":"DOC-002","monthly_payment":"31000"},{"offer_id":"QA-003","source_document_id":"DOC-003","quoted_advance":"100000","quoted_term_months":"24"}):
            self.assertEqual(self.client.post(url,{**base,**changes},HTTP_X_CSRFTOKEN=csrf).status_code,302)
        Quote.objects.create(lead=lead,offer_id="LEGACY-004",source_document_id="DOC-004",lessor_name="QA Legacy",received_on=today,valid_until=today+timedelta(days=7),verified_by_broker=True,monthly_payment=1,buyout=0,upfront_fee=0,recurring_monthly_fee=0,insurance_total=0,other_costs=0)
        rows,count=analyse_quotes(lead,lead.quotes.all(),today)
        by_id={r.offer_id:r for r in rows}
        self.assertEqual(count,2)
        self.assertEqual(by_id["QA-001"].rank,1)
        self.assertEqual(by_id["QA-001"].total_cash_outflow,Decimal("1281000.00"))
        self.assertEqual(by_id["QA-002"].rank,2)
        self.assertEqual(by_id["QA-003"].total_cash_outflow,Decimal("821000.00"))
        self.assertIsNone(by_id["QA-003"].rank)
        self.assertIsNone(by_id["LEGACY-004"].total_cash_outflow)
        self.assertIsNone(by_id["LEGACY-004"].rank)
        for layout in ("classic","focus","route"):
            r=self.client.get(root+layout+"/case/"+str(lead.pk)+"/")
            self.assertEqual(r.status_code,200)
            self.assertContains(r,"Другие условия")
            self.assertContains(r,"Условия оригинала не подтверждены")
            self.assertEqual(r.context["rows"],rows)
        r=self.client.get(reverse("admin:intake_lead_compare",args=[lead.pk]))
        self.assertEqual(r.context["rows"],rows)
        invalid={**base,"offer_id":"QA-005","source_document_id":"DOC-005","quoted_term_months":""}
        self.assertEqual(self.client.post(url,invalid,HTTP_X_CSRFTOKEN=csrf).status_code,200)
        self.assertEqual(Quote.objects.count(),4)
        self.assertEqual(self.client.post(url,{**invalid,"quoted_term_months":"36","quoted_advance":"1000000"},HTTP_X_CSRFTOKEN=csrf).status_code,200)
        self.assertEqual(Quote.objects.count(),4)


    @override_settings(DOCUMENT_VAULT_ENABLED=True)
    def test_document_vault_encrypted_roundtrip_and_access_denial(self):
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import OriginalDocument
        data,headers=self.form_payload()
        self.assertEqual(self.client.post("/apply/",data,**headers).status_code,302)
        lead=Lead.objects.get()
        today=date.today()
        quote=Quote.objects.create(lead=lead,offer_id="PDF-001",source_document_id="PDF-SOURCE-1",
            lessor_name="Synthetic finance",received_on=today,valid_until=today+timedelta(days=7))
        user=User.objects.create_superuser("document-qa","qa@example.test","synthetic-test-password-2026")
        url=reverse("broker-original-document",args=["route",lead.pk,quote.pk])
        self.assertEqual(self.client.get(url).status_code,302)
        self.client.force_login(user)
        self.assertEqual(self.client.get(url).status_code,200)
        csrf=self.client.cookies["csrftoken"].value
        payload=b"%PDF-1.4\nsynthetic-only-original\n%%EOF\n"
        def file(data=payload,name="synthetic.pdf"):
            return SimpleUploadedFile(name,data,content_type="application/pdf")
        def upload(data=payload):
            return self.client.post(url,{"action":"upload","original":file(data)},HTTP_X_CSRFTOKEN=csrf)
        def download():
            return self.client.post(url,{"action":"download"},HTTP_X_CSRFTOKEN=csrf)
        with override_settings(DOCUMENT_VAULT_ENABLED=False):
            self.assertEqual(self.client.get(url).status_code,404)
        with override_settings(SSH_OPERATOR=False):
            self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.post(url,{"action":"upload","original":file()}).status_code,403)
        with patch("intake.document_views.scan_pdf",return_value=False):
            self.assertEqual(upload().status_code,503)
        self.assertEqual(OriginalDocument.objects.count(),0)
        with patch("intake.document_views.scan_pdf",return_value=True) as scanner:
            self.assertEqual(upload(b"not a PDF").status_code,400)
            scanner.assert_not_called()
            self.assertEqual(self.client.post(url,{"action":"upload","original":[file(),file()]},HTTP_X_CSRFTOKEN=csrf).status_code,400)
            self.assertEqual(OriginalDocument.objects.count(),0)
            self.assertEqual(upload().status_code,302)
            doc=OriginalDocument.objects.get()
            self.assertNotIn(payload,bytes(doc.ciphertext))
            self.assertEqual(doc.byte_count,len(payload))
            self.assertEqual(upload().status_code,409)
            r=download()
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.content,payload)
            self.assertIn("attachment;",r["Content-Disposition"])
            self.assertIn("no-store",r["Cache-Control"])
            self.assertNotIn("synthetic.pdf",r["Content-Disposition"])
            self.assertTrue(AuditEvent.objects.filter(action="document.downloaded",lead=lead).exists())
            # No access for an unassigned broker even with both model permissions.
            other=User.objects.create_user("document-other",password="synthetic-test-password-2026",is_staff=True)
            other.user_permissions.add(*Permission.objects.filter(content_type__app_label="intake",
                codename__in=("view_lead","view_quote","view_originaldocument")))
            self.client.force_login(other)
            self.assertEqual(self.client.get(url).status_code,404)
            self.client.force_login(user)
            self.client.get(url)
            csrf=self.client.cookies["csrftoken"].value
            OriginalDocument.objects.filter(pk=doc.pk).update(ciphertext=b"damaged")
            self.assertEqual(download().status_code,503)
            OriginalDocument.objects.filter(pk=doc.pk).update(ciphertext=doc.ciphertext)
        with patch("intake.document_views.scan_pdf",return_value=False):
            self.assertEqual(download().status_code,503)
        self.assertEqual(AuditEvent.objects.filter(action="document.downloaded").count(),1)

    def test_scanner_fails_closed_without_socket(self):
        from .document_security import scan_pdf,looks_like_pdf
        payload=b"%PDF-1.4\nsynthetic\n%%EOF"
        self.assertTrue(looks_like_pdf(payload))
        self.assertFalse(looks_like_pdf(b"not a PDF"))
        with override_settings(DOCUMENT_SCANNER_SOCKET=""):
            self.assertFalse(scan_pdf(payload))


    def test_connect_tracks_real_manual_requests_across_layouts(self):
        from .models import LenderRequest
        from django.utils import timezone
        u=User.objects.create_superuser("connect-qa","qa@example.test","synthetic-test-password-2026")
        self.client.force_login(u)
        base="/admin/workspace/v/"
        self.client.get(base+"classic/new/")
        csrf=self.client.cookies["csrftoken"].value
        headers={"HTTP_X_CSRFTOKEN":csrf}
        self.assertEqual(self.client.post(base+"classic/new/",{"asset_type":"equipment","asset_price":"1000000","advance":"200000","term_months":"36","vat_basis":"included"},**headers).status_code,302)
        lead=Lead.objects.get()
        def url(layout):
            return reverse("broker-connect-case",args=[layout,lead.pk])
        today=timezone.localdate()
        create={"action":"create","lessor_name":"QA Finance","due_on":str(today)}
        self.assertEqual(self.client.post(url("classic"),create,**headers).status_code,302)
        self.assertEqual(self.client.post(url("focus"),{**create,"lessor_name":"qa   FINANCE"},**headers).status_code,200)
        self.assertEqual(LenderRequest.objects.count(),1)
        item=LenderRequest.objects.get()
        self.assertIsNone(item.sent_at)
        def change(state,version,**extra):
            return self.client.post(url("route"),{"action":"update","request_id":str(item.pk),"state":state,"version":str(version),**extra},**headers)
        self.assertEqual(change("sent",0).status_code,200)
        self.assertEqual(change("offer",0).status_code,200)
        self.assertEqual(change("sent",0,sent_confirmed="on").status_code,302)
        item.refresh_from_db()
        self.assertEqual(item.state,"sent")
        self.assertIsNotNone(item.sent_at)
        self.assertEqual(change("review",0).status_code,409)
        self.assertEqual(change("review",1).status_code,302)
        LenderRequest.objects.filter(pk=item.pk).update(due_on=today-timedelta(days=1))
        self.assertEqual(self.client.get(base+"focus/actions/").context["overdue_request_count"],1)
        self.assertEqual(self.client.get(base+"route/connect/?state=overdue").context["request_page"].paginator.count,1)
        self.assertEqual(change("offer",2).status_code,200)
        wrong=Quote.objects.create(lead=lead,offer_id="WRONG-01",source_document_id="WRONG-DOC",lessor_name="Different lender",received_on=today,valid_until=today+timedelta(days=3))
        right=Quote.objects.create(lead=lead,offer_id="RIGHT-01",source_document_id="RIGHT-DOC",lessor_name="qa finance",received_on=today,valid_until=today+timedelta(days=3))
        self.assertEqual(change("offer",2,quote=str(wrong.pk)).status_code,200)
        self.assertEqual(change("offer",2,quote=str(right.pk)).status_code,302)
        item.refresh_from_db()
        self.assertEqual(item.quote_id,right.pk)
        self.assertIsNotNone(item.responded_at)
        self.assertEqual(self.client.get(base+"focus/actions/").context["overdue_request_count"],0)
        for layout in ("classic","focus","route"):
            self.assertContains(self.client.get(url(layout)),"RIGHT-01")
            self.assertContains(self.client.get(base+layout+"/connect/"),"QA Finance")
        stranger=User.objects.create_user("connect-stranger",password="synthetic-test-password-2026",is_staff=True)
        stranger.user_permissions.add(*Permission.objects.filter(content_type__app_label="intake",codename__in=("view_lead","view_lenderrequest")))
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(url("route")).status_code,404)
        self.assertNotContains(self.client.get(base+"route/connect/"),"QA Finance")
        with override_settings(SSH_OPERATOR=False):
            self.assertEqual(self.client.get(base+"route/connect/").status_code,404)


    def test_task_center_shared_queue_and_version_control(self):
        from .models import BrokerTask
        from django.utils import timezone
        user=User.objects.create_superuser("tasks-qa","qa@example.test","synthetic-test-password-2026")
        self.client.force_login(user)
        root="/admin/workspace/v/"
        self.client.get(root+"classic/new/")
        csrf=self.client.cookies["csrftoken"].value
        headers={"HTTP_X_CSRFTOKEN":csrf}
        self.assertEqual(self.client.post(root+"classic/new/",{"asset_type":"equipment","asset_price":"1000000","advance":"200000","term_months":"36","vat_basis":"included"},**headers).status_code,302)
        lead=Lead.objects.get()
        today=timezone.localdate()
        def url(layout):
            return reverse("broker-task-case",args=[layout,lead.pk])
        data={"action":"create","kind":"collect","priority":"1","due_on":str(today-timedelta(days=1))}
        self.assertEqual(self.client.post(url("classic"),data,**headers).status_code,302)
        self.assertEqual(self.client.post(url("focus"),data,**headers).status_code,200)
        self.assertEqual(BrokerTask.objects.count(),1)
        task=BrokerTask.objects.get()
        self.assertEqual(self.client.get(root+"focus/actions/").context["task_overdue"],1)
        self.assertEqual(self.client.get(root+"route/tasks/?state=overdue").context["task_page"].paginator.count,1)
        for layout in ("classic","focus","route"):
            self.assertContains(self.client.get(url(layout)),"Собрать КП")
        def change(state,version,**extra):
            return self.client.post(url("route"),{"action":"update","task_id":str(task.pk),"state":state,"version":str(version),**extra},**headers)
        self.assertEqual(change("open",0).status_code,200)
        self.assertEqual(change("open",0,due_on=str(today)).status_code,302)
        self.assertEqual(change("done",0).status_code,409)
        self.assertEqual(self.client.get(root+"focus/actions/").context["task_today"],1)
        self.assertEqual(change("done",1).status_code,302)
        task.refresh_from_db()
        self.assertEqual(task.state,"done")
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(self.client.get(root+"focus/actions/").context["task_today"],0)
        self.assertEqual(self.client.post(url("classic"),data,**headers).status_code,302)
        stranger=User.objects.create_user("tasks-other",password="synthetic-test-password-2026",is_staff=True)
        stranger.user_permissions.add(*Permission.objects.filter(content_type__app_label="intake",codename__in=("view_lead","view_brokertask")))
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(url("route")).status_code,404)
        self.assertEqual(self.client.get(root+"route/tasks/").context["task_page"].paginator.count,0)
        with override_settings(SSH_OPERATOR=False):
            self.assertEqual(self.client.get(root+"route/tasks/").status_code,404)


    def test_optional_client_portal_switch_and_isolation(self):
        from .models import ClientPortalControl, ClientCaseAccess
        data,headers=self.form_payload()
        self.assertEqual(self.client.post("/apply/",data,**headers).status_code,302)
        owned=Lead.objects.get()
        other=Lead.objects.get(pk=owned.pk)
        other.pk=uuid.uuid4()
        other.request_key=uuid.uuid4()
        other.save(force_insert=True)
        operator=User.objects.create_superuser("portal-operator","operator@example.test","synthetic-operator-password-2026")
        customer=User.objects.create_user("portal-customer",password="synthetic-client-password-2026")
        stranger=User.objects.create_user("portal-stranger",password="synthetic-client-password-2026")
        ClientCaseAccess.objects.create(user=customer,lead=owned)
        self.client.force_login(operator)
        switch=reverse("admin:intake_clientportalcontrol_change",args=[1])
        self.assertEqual(self.client.get(switch).status_code,200)
        csrf=self.client.cookies["csrftoken"].value
        headers={"HTTP_X_CSRFTOKEN":csrf}
        with override_settings(CLIENT_PORTAL_READY=False):
            self.assertEqual(self.client.post(switch,{"enabled":"on","_save":"Save"},**headers).status_code,200)
            self.assertFalse(ClientPortalControl.objects.get(pk=1).enabled)
        with override_settings(CLIENT_PORTAL_READY=True):
            self.assertEqual(self.client.post(switch,{"enabled":"on","_save":"Save"},**headers).status_code,302)
            self.assertTrue(ClientPortalControl.objects.get(pk=1).enabled)
            public=Client(enforce_csrf_checks=True)
            with override_settings(SSH_OPERATOR=False):
                self.assertEqual(public.get("/client/status/").json(),{"enabled":True})
                self.assertEqual(public.get("/client/").status_code,302)
                self.assertEqual(public.get("/client/login/").status_code,200)
                token=public.cookies["csrftoken"].value
                self.assertEqual(public.post("/client/login/",{"username":customer.username,"password":"synthetic-client-password-2026"}).status_code,403)
                self.assertEqual(public.post("/client/login/",{"username":customer.username,"password":"synthetic-client-password-2026"},HTTP_X_CSRFTOKEN=token).status_code,302)
                page=public.get("/client/")
                self.assertEqual(page.status_code,200)
                self.assertContains(page,str(owned.pk)[:8])
                self.assertNotContains(page,str(other.pk)[:8])
                self.assertNotContains(page,owned.phone)
                self.assertIn("no-store",page["Cache-Control"])
                self.assertEqual(page["X-Robots-Tag"],"noindex, nofollow")
                self.assertEqual(public.get("/admin/").status_code,404)
                unauthorized=Client()
                unauthorized.force_login(stranger)
                self.assertEqual(unauthorized.get("/client/").status_code,302)
            self.assertEqual(self.client.post(switch,{"_save":"Save"},**headers).status_code,302)
            with override_settings(SSH_OPERATOR=False):
                self.assertEqual(public.get("/client/status/").json(),{"enabled":False})
                self.assertEqual(public.get("/client/").status_code,404)
                self.assertEqual(public.get("/client/login/").status_code,404)
            self.assertEqual(self.client.post(switch,{"enabled":"on","_save":"Save"},**headers).status_code,302)
            with override_settings(SSH_OPERATOR=False):
                self.assertEqual(public.get("/client/").status_code,302)
                self.assertEqual(public.get("/client/status/").json(),{"enabled":True})


    def test_legal_review_revision_evidence_and_access(self):
        from .models import ContractReview, ContractReviewItem
        from .legal_views import TOPICS
        user=User.objects.create_superuser("legal-qa","qa@example.test","synthetic-test-password-2026")
        self.client.force_login(user)
        root="/admin/workspace/v/"
        self.client.get(root+"classic/new/")
        csrf=self.client.cookies["csrftoken"].value
        headers={"HTTP_X_CSRFTOKEN":csrf}
        self.assertEqual(self.client.post(root+"classic/new/",{"asset_type":"equipment","asset_price":"1000000","advance":"200000","term_months":"36","vat_basis":"included"},**headers).status_code,302)
        lead=Lead.objects.get()
        def url(layout):
            return reverse("broker-legal-case",args=[layout,lead.pk])
        self.assertEqual(self.client.post(url("classic"),{"action":"create","source_sha256":"not-a-hash"},**headers).status_code,200)
        self.assertEqual(self.client.post(url("classic"),{"action":"create","source_sha256":"a"*64},**headers).status_code,302)
        review=ContractReview.objects.get()
        self.assertEqual(review.items.count(),len(TOPICS))
        self.assertEqual(self.client.post(url("focus"),{"action":"create","source_sha256":"A"*64},**headers).status_code,200)
        item=review.items.get(topic="insurance")
        def update(state,version,page=""):
            return self.client.post(url("route")+"?review="+str(review.pk),{"action":"update","item_id":item.pk,"state":state,"version":version,"page":page},**headers)
        self.assertEqual(update("risk",0).status_code,200)
        self.assertEqual(update("missing",0,"3").status_code,200)
        self.assertEqual(update("risk",0,"3").status_code,302)
        item.refresh_from_db()
        self.assertEqual(item.state,"risk")
        self.assertEqual(item.page,3)
        self.assertEqual(item.reviewed_by,user)
        self.assertEqual(update("ok",0,"4").status_code,409)
        for layout in ("classic","focus","route"):
            page=self.client.get(url(layout)+"?review="+str(review.pk))
            self.assertContains(page,"Страница: 3")
            self.assertEqual(page.context["counts"]["risk"],1)
        self.assertEqual(self.client.post(url("route"),{"action":"create","source_sha256":"b"*64},**headers).status_code,302)
        new=ContractReview.objects.get(source_sha256="b"*64)
        self.assertEqual(new.items.filter(state="unknown").count(),len(TOPICS))
        self.assertEqual(self.client.get(url("route")+"?review="+str(new.pk)).context["counts"]["risk"],0)
        self.assertEqual(self.client.post(url("route")+"?review="+str(new.pk),{"action":"update","item_id":item.pk,"state":"ok","version":1,"page":2},**headers).status_code,404)
        stranger=User.objects.create_user("legal-stranger",password="synthetic-test-password-2026",is_staff=True)
        stranger.user_permissions.add(*Permission.objects.filter(content_type__app_label="intake",codename__in=("view_lead","view_contractreview")))
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(url("route")).status_code,404)
        with override_settings(SSH_OPERATOR=False):
            self.assertEqual(self.client.get(url("route")).status_code,404)


    def test_explicit_schedule_ranking_and_stale_confirmation(self):
        from .quote_analysis import analyse_quotes
        from django.utils import timezone
        user=User.objects.create_superuser("schedule-qa","qa@example.test","synthetic-test-password-2026")
        self.client.force_login(user)
        root="/admin/workspace/v/"
        self.client.get(root+"classic/new/")
        csrf=self.client.cookies["csrftoken"].value
        headers={"HTTP_X_CSRFTOKEN":csrf}
        self.assertEqual(self.client.post(root+"classic/new/",{"asset_type":"equipment","asset_price":"1000000","advance":"200000","term_months":"36","vat_basis":"included"},**headers).status_code,302)
        lead=Lead.objects.get()
        today=timezone.localdate()
        for i in range(1,4):
            Quote.objects.create(lead=lead,offer_id=f"QA-SCH-{i}",source_document_id=f"QA-DOC-{i}",lessor_name=f"QA Finance {i}",received_on=today,valid_until=today+timedelta(days=7),
                quoted_asset_price=Decimal("1000000"),quoted_advance=Decimal("200000"),quoted_term_months=36,quoted_vat_basis="included",verified_by_broker=True,
                monthly_payment=Decimal("30000"),buyout=Decimal("1000"),upfront_fee=0,recurring_monthly_fee=0,insurance_total=0,other_costs=0)
        a,b,c=list(lead.quotes.all())
        def url(q,layout="route"):
            return reverse("broker-quote-schedule",args=[layout,lead.pk,q.pk])
        def payload(q,text):
            form=self.client.get(url(q)).context["form"]
            return {**form.initial,"schedule":text,"complete":"on"}
        first="2027-01-01;advance;200000\n2027-12-31;lease;400000\n2028-12-31;lease;500000\n2029-12-31;buyout;1000"
        second=first.replace("400000","450000")
        data=payload(a,first)
        self.assertEqual(self.client.post(url(a),{**data,"complete":""},**headers).status_code,200)
        self.assertEqual(self.client.post(url(a),{**data,"schedule":first.replace("advance;200000","advance;199999")},**headers).status_code,200)
        self.assertEqual(self.client.post(url(a),data,**headers).status_code,302)
        self.assertEqual(self.client.post(url(a),data,**headers).status_code,409)
        rows,count=analyse_quotes(lead,lead.quotes.all(),today)
        self.assertEqual(count,1)
        self.assertTrue(all(r.rank is None for r in rows))
        self.assertEqual(self.client.post(url(b),payload(b,second),**headers).status_code,302)
        rows,count=analyse_quotes(lead,lead.quotes.all(),today)
        found={r.offer_id:r for r in rows}
        self.assertEqual(count,2)
        self.assertEqual(found[a.offer_id].total_cash_outflow,Decimal("1101000.00"))
        self.assertEqual(found[b.offer_id].total_cash_outflow,Decimal("1151000.00"))
        self.assertEqual(found[a.offer_id].rank,1)
        self.assertEqual(found[b.offer_id].rank,2)
        self.assertIsNone(found[c.offer_id].rank)
        for layout in ("classic","focus","route"):
            self.assertEqual(self.client.get(url(a,layout)).context["total"],Decimal("1101000.00"))
            page=self.client.get(reverse("broker-variant-case",args=[layout,lead.pk]))
            self.assertEqual(page.context["rows"],rows)
        self.assertEqual(self.client.get(reverse("admin:intake_lead_compare",args=[lead.pk])).context["rows"],rows)
        Quote.objects.filter(pk=a.pk).update(monthly_payment=Decimal("31000"))
        rows,count=analyse_quotes(lead,lead.quotes.all(),today)
        self.assertEqual(count,1)
        self.assertIsNone(rows[0].total_cash_outflow)
        self.assertTrue(all(r.rank is None for r in rows))
        stranger=User.objects.create_user("schedule-stranger",password="synthetic-test-password-2026",is_staff=True)
        stranger.user_permissions.add(*Permission.objects.filter(content_type__app_label="intake",codename__in=("view_lead","view_quote")))
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(url(a)).status_code,404)
        with override_settings(SSH_OPERATOR=False):
            self.assertEqual(self.client.get(url(a)).status_code,404)

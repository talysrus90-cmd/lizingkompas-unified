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

"""Integration tests for production intake gates, encrypted storage and staff CRM.

Uses synthetic leads ONLY and the test database. Does not send anything by email.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .forms import ApplicationForm
from .models import Lead, Quote, SubmissionAttempt, AuditEvent

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

@override_settings(**APPROVED)
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

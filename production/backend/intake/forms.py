"""Strict customer application form; no passports, uploads or bureau requests."""
import re
import uuid
from django import forms
from django.core.exceptions import ValidationError

ASSET_TYPES = [
    ("vehicle", "Автомобили"),
    ("trucks", "Грузовой транспорт"),
    ("machinery", "Спецтехника"),
    ("equipment", "Оборудование"),
    ("property", "Недвижимость"),
    ("other", "Другое имущество"),
]
VAT_BASES = [
    ("included", "НДС включён"),
    ("excluded", "Без НДС"),
    ("not_applicable", "Не применяется"),
]

class ApplicationForm(forms.Form):
    request_key = forms.UUIDField(widget=forms.HiddenInput)
    client_name = forms.CharField(label="ФИО", min_length=2, max_length=120)
    phone = forms.CharField(label="Телефон", max_length=20)
    email = forms.EmailField(label="Электронная почта (необязательно)", required=False, max_length=254)
    company = forms.CharField(label="Организация (необязательно)", required=False, max_length=160)
    inn = forms.CharField(label="ИНН (необязательно)", required=False, max_length=12)
    asset_type = forms.ChoiceField(label="Тип имущества", choices=ASSET_TYPES)
    asset_price = forms.DecimalField(label="Стоимость имущества, ₽",
                                     max_digits=14, decimal_places=2, min_value=1)
    advance = forms.DecimalField(label="Аванс, ₽",
                                 max_digits=14, decimal_places=2, min_value=0)
    term_months = forms.IntegerField(label="Срок, месяцев", min_value=12, max_value=84)
    vat_basis = forms.ChoiceField(label="НДС", choices=VAT_BASES)
    message = forms.CharField(label="Комментарий (необязательно)",
                              required=False, max_length=500, widget=forms.Textarea(attrs={"rows":3}))
    consent = forms.BooleanField(
        label="Я даю отдельное согласие на обработку данных для рассмотрения заявки",
        required=True,
    )
    # Non-PII bot trap must always stay blank; never reveal whether it fired.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_phone(self):
        raw = self.cleaned_data["phone"]
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 11 and digits.startswith("8"):
            digits = "7" + digits[1:]
        if len(digits) != 11 or not digits.startswith("7"):
            raise ValidationError("Введите российский номер телефона.")
        return "+" + digits

    def clean_inn(self):
        inn = self.cleaned_data.get("inn", "").strip()
        if inn and (not inn.isascii() or not inn.isdigit() or len(inn) not in (10, 12)):
            raise ValidationError("ИНН должен содержать 10 или 12 цифр.")
        return inn

    def clean(self):
        data = super().clean()
        if data.get("asset_price") is not None and data.get("advance") is not None:
            if data["advance"] >= data["asset_price"]:
                self.add_error("advance", "Аванс должен быть меньше стоимости имущества.")
        if data.get("website"):
            raise ValidationError("Форма не прошла проверку.")
        return data

class CallbackForm(forms.Form):
    """Single-purpose callback form; no CRM/credit/document questions."""
    request_key = forms.UUIDField(widget=forms.HiddenInput)
    name = forms.CharField(label="Как к вам обращаться (необязательно)",
                           max_length=120,required=False)
    phone = forms.CharField(label="Ваш телефон",max_length=20)
    consent = forms.BooleanField(
        label="Даю отдельное согласие на обработку данных для обратного звонка",
        required=True
    )
    website = forms.CharField(required=False,widget=forms.HiddenInput)

    def clean_phone(self):
        digits=re.sub(r"\D","",self.cleaned_data["phone"])
        if len(digits)==11 and digits.startswith("8"):
            digits="7"+digits[1:]
        if len(digits)!=11 or not digits.startswith("7"):
            raise ValidationError("Введите российский номер телефона.")
        return "+"+digits

    def clean(self):
        values=super().clean()
        if values.get("website"):
            raise ValidationError("Форма не прошла проверку.")
        return values

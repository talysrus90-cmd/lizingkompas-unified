"""Explicit dated cash outflows: no assumed payment count or inferred tax.

Amounts are RUB on the stated VAT basis. All entries are individual cash
outflows; never add legacy monthly/fee fields to a complete schedule.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
import re

KINDS = ("advance", "lease", "buyout", "fee", "insurance", "other")
MAX_ROWS = 500
MONEY = re.compile(r"[0-9]{1,13}(?:\.[0-9]{1,2})?")

@dataclass(frozen=True)
class Payment:
    on: date
    kind: str
    amount: Decimal

def parse_schedule(text):
    """One ISO date;kind;amount per line, no header, no guessed values."""
    if not isinstance(text,str) or not 0<len(text)<=32000:
        raise ValueError("Укажите график (до 32 000 символов).")
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    if not 1<=len(lines)<=MAX_ROWS:
        raise ValueError("Допустимо от 1 до 500 платежей.")
    out=[]
    for i,line in enumerate(lines,1):
        parts=[p.strip() for p in line.split(";")]
        try:
            if len(parts)!=3 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",parts[0]):
                raise ValueError
            on=date.fromisoformat(parts[0])
            kind=parts[1]
            raw=parts[2].replace(",",".")
            if kind not in KINDS or not MONEY.fullmatch(raw):
                raise ValueError
            amount=Decimal(raw)
            if amount<=0 or amount>Decimal("1000000000000"):
                raise ValueError
            out.append(Payment(on,kind,amount))
        except ValueError as exc:
            raise ValueError(f"Строка {i}: неверная дата, вид или сумма платежа.") from exc
    if len(set(out))!=len(out):
        raise ValueError("Повторяющиеся строки: объедините одинаковые платежи одной даты и вида в одну сумму.")
    return tuple(sorted(out,key=lambda p:(p.on,p.kind,p.amount)))

def schedule_total(payments,advance):
    if not payments or not any(p.kind=="lease" for p in payments):
        raise ValueError("Нужен хотя бы один лизинговый платёж.")
    if advance is None or sum((p.amount for p in payments if p.kind=="advance"),Decimal(0))!=advance:
        raise ValueError("Аванс в графике не совпадает с исходными условиями КП.")
    return sum((p.amount for p in payments),Decimal(0)).quantize(Decimal("0.01"))

def format_schedule(payments):
    return "\n".join(f"{p.on.isoformat()};{p.kind};{p.amount:.2f}" for p in payments)

def quote_fingerprint(quote):
    fields=("id","source_document_id","offer_id","lessor_name","received_on","valid_until",
            "quoted_asset_price","quoted_advance","quoted_term_months","quoted_vat_basis",
            "monthly_payment","buyout","upfront_fee","recurring_monthly_fee","insurance_total","other_costs",
            "verified_by_broker")
    values={}
    for key in fields:
        v=getattr(quote,key)
        values[key]=format(v.quantize(Decimal("0.01")),"f") if isinstance(v,Decimal) else str(v)
    return hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def checked_schedule(quote):
    record=quote.payment_schedule
    if not isinstance(record,dict) or set(record)!={"text","fingerprint"}:
        raise ValueError("График не подтверждён.")
    if record["fingerprint"]!=quote_fingerprint(quote):
        raise ValueError("Условия КП изменились — повторно сверьте график.")
    payments=parse_schedule(record["text"])
    return schedule_total(payments,quote.quoted_advance)


def import_schedule(text):
    """Strict spreadsheet clipboard/CSV import. Never guess dates or currency."""
    import csv
    import io
    if not isinstance(text,str) or not 0<len(text)<=32000:
        raise ValueError("Вставьте до 32 000 символов.")
    text=text.lstrip("\ufeff")
    first=next((line for line in text.splitlines() if line.strip()),"")
    delimiter="\t" if "\t" in first else ";"
    aliases={"аванс":"advance","лизинговый платёж":"lease","лизинговый платеж":"lease",
             "выкуп":"buyout","комиссия":"fee","страхование":"insurance","прочее":"other"}
    headers={("дата","вид","сумма"),("date","kind","amount")}
    rows=[]
    try:
        for row in csv.reader(io.StringIO(text),delimiter=delimiter,strict=True):
            if not row or all(not cell.strip() for cell in row):
                continue
            row=[cell.strip() for cell in row]
            if not rows and tuple(cell.casefold() for cell in row) in headers:
                continue
            if len(row)!=3 or any("\n" in cell or "\r" in cell for cell in row):
                raise ValueError("Нужны три колонки: дата, вид, сумма.")
            on,kind,amount=row
            if re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}",on):
                day,month,year=on.split(".")
                on=f"{year}-{month}-{day}"
            kind=aliases.get(kind.casefold(),kind.casefold())
            # Only remove spaces if the grouping is unambiguous.
            if re.fullmatch(r"[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+(?:[.,][0-9]{1,2})?",amount):
                amount=re.sub(r"[ \u00a0\u202f]","",amount)
            rows.append(f"{on};{kind};{amount}")
            if len(rows)>MAX_ROWS:
                raise ValueError("Допустимо не более 500 платежей.")
    except csv.Error as exc:
        raise ValueError("Неверная структура CSV.") from exc
    return parse_schedule("\n".join(rows))


def present_value(payments, valuation_date, annual_rate_percent):
    """Actual/365 fixed; effective annual discount rate, explicit common date.

    This is a scenario-dependent present value of outflows, NOT an APR.
    No assumption about loan principal, asset delivery date, tax deduction or
    residual value. Historical payments before valuation date are rejected.
    """
    if type(valuation_date) is not date or not isinstance(annual_rate_percent,Decimal):
        raise ValueError("Укажите дату и годовую ставку дисконтирования.")
    if not annual_rate_percent.is_finite() or not Decimal("0")<=annual_rate_percent<=Decimal("100"):
        raise ValueError("Ставка дисконтирования: от 0 до 100% годовых.")
    if not payments or len(payments)>MAX_ROWS:
        raise ValueError("Нет допустимого графика.")
    if any(p.on<valuation_date for p in payments):
        raise ValueError("Дата оценки не может быть позже первого платежа.")
    with localcontext() as ctx:
        ctx.prec=40
        base=Decimal(1)+annual_rate_percent/100
        value=sum((p.amount/(base**(Decimal((p.on-valuation_date).days)/365)) for p in payments),Decimal(0))
        return value.quantize(Decimal("0.01"))

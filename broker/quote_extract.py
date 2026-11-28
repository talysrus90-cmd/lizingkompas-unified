"""Conservative local extraction of explicitly labelled quote terms.
Only exact labels and single RUB amounts/whole months are accepted.
Not a complete parser, approval, or AI-based financial recommendation.
"""
import re
from decimal import Decimal
from collections import defaultdict

LABELS={
"asset_price":("стоимость имущества","цена имущества","стоимость предмета лизинга","asset price"),
"advance":("аванс","авансовый платеж","авансовый платёж","advance"),
"term_months":("срок лизинга","срок договора лизинга","lease term"),
"monthly_payment":("ежемесячный платеж","ежемесячный платёж","лизинговый платеж в месяц","monthly payment"),
"buyout":("выкупной платеж","выкупной платёж","выкупная стоимость","buyout"),
"upfront_fee":("разовая комиссия","единовременная комиссия","upfront fee"),
"recurring_monthly_fee":("ежемесячная комиссия","monthly fee"),
"insurance_total":("страхование за весь срок","insurance total"),
"other_costs":("прочие расходы за весь срок","other costs total"),
}
NAMES={alias:field for field,aliases in LABELS.items() for alias in aliases}
MONEY=re.compile(r"([0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+|[0-9]+)(?:([.,][0-9]{1,2}))?\s*(?:руб(?:\.|лей|ля)?|₽|RUB)",re.I)
MONTHS=re.compile(r"([0-9]{1,2})\s*(?:мес\.?|месяц(?:а|ев)?|months?)",re.I)

def parse_value(field,raw):
    if field=="term_months":
        m=MONTHS.fullmatch(raw.strip())
        if m and 12<=int(m[1])<=84:return str(int(m[1]))
    else:
        m=MONEY.fullmatch(raw.strip())
        if m:
            whole=re.sub(r"[ \u00a0\u202f]","",m[1])
            if len(whole)<=13:
                value=Decimal(whole+(m[2] or "").replace(",","."))
                if value<=Decimal("1000000000000"):return format(value,".2f")
    return None

def extract_quote(document):
    """Accept normalized document blocks; preserve verbatim source evidence."""
    found=defaultdict(list)
    for block in document["blocks"]:
        if any(block.get(flag) for flag in ("formula_unresolved","sheet_hidden","needs_ocr","attachment_not_opened")):
            continue
        if block["location"].get("header"):continue
        for line in block["text"].splitlines():
            if len(line)>300 or ":" not in line:continue
            label,raw=line.split(":",1)
            field=NAMES.get(label.strip().casefold())
            if not field:continue
            value=parse_value(field,raw)
            if value is not None:
                found[field].append({"value":value,"evidence":line,"location":dict(block["location"])})
    candidates=[];conflicts=[]
    for field,items in found.items():
        if len({item["value"] for item in items})!=1:
            conflicts.append(field)
            continue
        candidates.append({"field":field,**items[0],"status":"unverified_candidate"})
    return {"source_sha256":document["source_sha256"],"candidates":candidates,
            "conflicting_fields":sorted(conflicts),"missing_fields":[f for f in LABELS if f not in found],
            "requires_human_review":True}

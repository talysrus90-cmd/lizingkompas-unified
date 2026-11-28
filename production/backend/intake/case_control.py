"""Read-only, permission-scoped operational signals, not an approval gate."""
from django.db.models import Count, Q
from django.urls import reverse

def case_signals(lead, layout, today, *, quotes, rows, quote_allowed,
                 tasks_allowed, connect_allowed, legal_allowed):
    signals=[]
    def add(label,status,detail,url=None):
        signals.append({"label":label,"status":status,"detail":detail,"url":url})
    def link(name):
        return reverse(name,args=[layout,lead.pk])
    if quote_allowed:
        if not quotes:
            add("Коммерческие предложения","attention","Нет зарегистрированных КП.","#comparison")
        else:
            comparable=sum(r.rank is not None for r in rows)
            expired=sum(q.valid_until<today for q in quotes)
            unverified=sum(not q.verified_by_broker for q in quotes)
            detail=f"КП: {len(quotes)}; в рейтинге: {comparable}; истекли: {expired}; без проверки оригинала: {unverified}."
            add("Коммерческие предложения","attention" if comparable<2 or expired or unverified else "recorded",detail,"#comparison")
    if tasks_allowed:
        stats=lead.broker_tasks.aggregate(open=Count("pk",filter=Q(state="open")),
                overdue=Count("pk",filter=Q(state="open",due_on__lt=today)),
                today=Count("pk",filter=Q(state="open",due_on=today)))
        add("Задачи","attention" if stats["overdue"] else "recorded",
            f"Открыто: {stats['open']}; сегодня: {stats['today']}; просрочено: {stats['overdue']}.",
            link("broker-task-case"))
    if connect_allowed:
        active=Q(state__in=("sent","review"))
        stats=lead.lender_requests.aggregate(total=Count("pk"),pending=Count("pk",filter=active),
                    overdue=Count("pk",filter=active & Q(due_on__lt=today)))
        add("Запросы лизингодателям","attention" if stats["overdue"] or not stats["total"] else "recorded",
            f"Запросов: {stats['total']}; ожидаются ответы: {stats['pending']}; просрочено: {stats['overdue']}.",
            link("broker-connect-case"))
    if legal_allowed:
        latest=lead.contract_reviews.order_by("-created_at","id").first()
        if latest is None:
            add("Проверка договора","attention","Редакции договора не зарегистрированы.",link("broker-legal-case"))
        else:
            # Import at call time; legal_views imports workspace for shared permissions.
            from .legal_views import TOPICS
            expected={key for key,_ in TOPICS}
            items={x["topic"]:x for x in latest.items.values("topic","state","page","reviewed_at","reviewed_by_id")}
            checked=sum(1 for k in expected if k in items and items[k]["state"] in ("ok","risk")
                        and items[k]["page"] and items[k]["reviewed_at"] and items[k]["reviewed_by_id"])
            missing=sum(1 for k in expected if k in items and items[k]["state"]=="missing"
                        and items[k]["reviewed_at"] and items[k]["reviewed_by_id"])
            risks=sum(1 for k in expected if k in items and items[k]["state"]=="risk")
            unknown=len(expected)-checked-missing
            detail=f"Последняя зарегистрированная редакция: {latest.source_sha256[:12]}; проверено: {checked}/{len(expected)}; риски: {risks}; не найдено: {missing}; не подтверждено: {unknown}."
            add("Проверка договора","attention" if risks or missing or unknown else "recorded",detail,
                link("broker-legal-case")+"?review="+str(latest.pk))
    return signals
